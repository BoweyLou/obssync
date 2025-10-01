#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PYTHON="python3"
PYTHON_EXEC="${PYTHON:-$DEFAULT_PYTHON}"
EXTRA_GROUPS=()

usage() {
  cat <<'USAGE'
Usage: ./install.sh [options]

Options:
  --python PATH       Python interpreter used to bootstrap the managed venv (default: python3)
  --extra NAME        Install a named optional dependency group (repeatable)
  --extras LIST       Comma-separated list of optional dependency groups
  -h, --help          Show this help message

Examples:
  ./install.sh
  ./install.sh --extras macos,optimization
  ./install.sh --python /usr/bin/python3 --extra dev
USAGE
}

abort() {
  echo "install.sh: $1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      shift || abort "--python expects a value"
      PYTHON_EXEC="$1"
      ;;
    --extra)
      shift || abort "--extra expects a value"
      EXTRA_GROUPS+=("$1")
      ;;
    --extras)
      shift || abort "--extras expects a value"
      IFS=',' read -r -a extras_from_list <<<"$1"
      for extra in "${extras_from_list[@]}"; do
        EXTRA_GROUPS+=("$extra")
      done
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      abort "unknown option: $1"
      ;;
  esac
  shift
done

if ! command -v "$PYTHON_EXEC" >/dev/null 2>&1; then
  abort "Python interpreter not found: $PYTHON_EXEC"
fi

export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON_EXEC" - <<'PY'
import platform
import sys

EXPECTED = (3, 8)
if sys.version_info < EXPECTED:
    version = platform.python_version()
    raise SystemExit(f"Python {EXPECTED[0]}.{EXPECTED[1]} or newer required, found {version}")
PY

venv_info="$("$PYTHON_EXEC" - <<'PY'
from obs_sync.utils import venv
venv_dir, python_bin = venv.venv_paths()
venv.ensure_venv(venv_dir)
print(venv_dir)
print(python_bin)
PY
)"

# Read two lines into two variables
{ read -r VENV_DIR; read -r PYTHON_BIN; } <<<"$venv_info"
if [[ -z "$VENV_DIR" || -z "$PYTHON_BIN" ]]; then
  abort "failed to resolve managed virtual environment paths"
fi

echo "Using managed virtual environment at $VENV_DIR"

echo "Upgrading pip/setuptools/wheel..."
"$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel >/dev/null

declare -a UNIQUE_EXTRAS=()
# Only process extras if any were provided (handles set -u with empty arrays)
for extra in "${EXTRA_GROUPS[@]+"${EXTRA_GROUPS[@]}"}"; do
  trimmed="$(printf '%s' "$extra" | tr -d ' \t')"
  [[ -z "$trimmed" ]] && continue
  normalized="$(printf '%s' "$trimmed" | tr '[:upper:]' '[:lower:]')"
  # Check for duplicates
  for existing in "${UNIQUE_EXTRAS[@]+"${UNIQUE_EXTRAS[@]}"}"; do
    if [[ "$existing" == "$normalized" ]]; then
      normalized=""
      break
    fi
  done
  [[ -n "$normalized" ]] && UNIQUE_EXTRAS+=("$normalized")
done

if ((${#UNIQUE_EXTRAS[@]} > 0)); then
  extras_spec="${UNIQUE_EXTRAS[0]}"
  for extra in "${UNIQUE_EXTRAS[@]:1}"; do
    extras_spec+=",$extra"
  done
  install_target=".[${extras_spec}]"
  echo "Installing project with extras: ${extras_spec}"
else
  install_target="."
  echo "Installing core project dependencies"
fi

(
  cd "$ROOT_DIR"
  "$PYTHON_BIN" -m pip install --upgrade -e "$install_target"
)

VENV_BIN_DIR="$(dirname "$PYTHON_BIN")"
CLI_ENTRY="$VENV_BIN_DIR/obs-sync"
LOCAL_BIN="$HOME/.local/bin"

if [[ -x "$CLI_ENTRY" ]]; then
  mkdir -p "$LOCAL_BIN"
  SYMLINK_PATH="$LOCAL_BIN/obs-sync"
  if [[ -L "$SYMLINK_PATH" ]]; then
    CURRENT_TARGET="$(readlink "$SYMLINK_PATH")"
    if [[ "$CURRENT_TARGET" == "$CLI_ENTRY" ]]; then
      echo "Symlink already in place at $SYMLINK_PATH"
    else
      echo "Skipping symlink: $SYMLINK_PATH points to $CURRENT_TARGET"
    fi
  elif [[ -e "$SYMLINK_PATH" ]]; then
    echo "Skipping symlink: $SYMLINK_PATH already exists"
  else
    if ln -s "$CLI_ENTRY" "$SYMLINK_PATH" 2>/dev/null; then
      echo "Linked $SYMLINK_PATH -> $CLI_ENTRY"
    else
      echo "Warning: failed to create symlink at $SYMLINK_PATH" >&2
    fi
  fi
else
  echo "Warning: obs-sync entry point not found at $CLI_ENTRY" >&2
fi

if [[ ":$PATH:" == *":$LOCAL_BIN:"* ]]; then
  echo "$LOCAL_BIN already present on PATH"
else
  SHELL_NAME="$(basename "${SHELL:-}")"
  case "$SHELL_NAME" in
    zsh) PROFILE="$HOME/.zshrc" ;;
    bash)
      if [[ -f "$HOME/.bash_profile" ]]; then
        PROFILE="$HOME/.bash_profile"
      else
        PROFILE="$HOME/.bashrc"
      fi
      ;;
    *) PROFILE="$HOME/.profile" ;;
  esac

  if [[ ! -f "$PROFILE" ]]; then
    touch "$PROFILE"
  fi

  if grep -qs "\.local/bin" "$PROFILE"; then
    echo "$PROFILE already contains a PATH entry for ~/.local/bin"
  else
    cat <<'EOF' >> "$PROFILE"

# Added by obs-sync install.sh - expose managed obs-sync CLI
export PATH="$HOME/.local/bin:$PATH"
EOF
    echo "Updated $PROFILE to include ~/.local/bin on PATH"
  fi
fi

echo "Installation complete."
echo "Managed Python interpreter: $PYTHON_BIN"
echo "obs-sync CLI location: $CLI_ENTRY"
echo "Run 'source ~/.zshrc' or equivalent to refresh your shell PATH."
