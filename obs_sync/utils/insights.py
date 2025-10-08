"""
Shared insight formatting utilities for CLI and daily note output.

Provides consistent markdown and terminal rendering for sync insights,
streak analytics, and hygiene reports.
"""

from typing import Dict, List, Any, Optional
from datetime import date, datetime


# Section markers for deterministic replacement in daily notes
INSIGHT_SECTION_START = "## Task Insights"
INSIGHT_SECTION_END = "<!-- END TASK INSIGHTS -->"


def format_insight_snapshot_markdown(
    insights: Dict[str, Any],
    streaks: Optional[Dict[str, Any]] = None,
    date_str: Optional[str] = None
) -> str:
    """
    Format insight data as markdown for daily note injection.
    
    Args:
        insights: Aggregated sync insights with keys:
            - completions: int
            - overdue: int
            - new_tasks: int
            - by_list: Dict[list_name, counts]
            - by_tag: Dict[tag, counts]
        streaks: Optional streak data keyed by tag/list
        date_str: Optional date string for the snapshot
    
    Returns:
        Markdown string with deterministic section markers
    """
    lines = [INSIGHT_SECTION_START, ""]
    
    if date_str:
        lines.append(f"*Snapshot for {date_str}*\n")
    
    # Summary stats
    total_completed = insights.get("completions", 0)
    total_overdue = insights.get("overdue", 0)
    total_new = insights.get("new_tasks", 0)
    
    lines.append("### Summary")
    lines.append(f"- **Completed**: {total_completed}")
    lines.append(f"- **Overdue**: {total_overdue}")
    lines.append(f"- **New**: {total_new}")
    lines.append("")
    
    # By list breakdown
    by_list = insights.get("by_list", {})
    if by_list:
        lines.append("### By List")
        for list_name, counts in sorted(by_list.items()):
            completed = counts.get("completions", 0)
            overdue = counts.get("overdue", 0)
            new = counts.get("new_tasks", 0)
            lines.append(f"- **{list_name}**: {completed} done, {overdue} overdue, {new} new")
        lines.append("")
    
    # By tag breakdown
    by_tag = insights.get("by_tag", {})
    if by_tag:
        lines.append("### By Tag")
        for tag, counts in sorted(by_tag.items()):
            completed = counts.get("completions", 0)
            overdue = counts.get("overdue", 0)
            new = counts.get("new_tasks", 0)
            lines.append(f"- **#{tag}**: {completed} done, {overdue} overdue, {new} new")
        lines.append("")
    
    # Streaks
    if streaks:
        lines.append("### Momentum Streaks")
        for key, streak_info in sorted(streaks.items()):
            current = streak_info.get("current", 0)
            best = streak_info.get("best", 0)
            if current > 0:
                emoji = "🔥" if current >= 3 else "⚡"
                lines.append(f"- {emoji} **{key}**: {current} days (best: {best})")
        lines.append("")
    
    lines.append(INSIGHT_SECTION_END)
    return "\n".join(lines)


def format_insight_cli_summary(
    insights: Dict[str, Any],
    vault_name: Optional[str] = None
) -> str:
    """
    Format insight data for terminal display.
    
    Args:
        insights: Aggregated sync insights
        vault_name: Optional vault name for header
    
    Returns:
        Terminal-formatted string with box drawing
    """
    lines = []
    
    header = "TASK INSIGHTS"
    if vault_name:
        header += f" - {vault_name}"
    
    lines.append("=" * 60)
    lines.append(f"  {header}")
    lines.append("=" * 60)
    
    total_completed = insights.get("completions", 0)
    total_overdue = insights.get("overdue", 0)
    total_new = insights.get("new_tasks", 0)
    
    lines.append(f"  Completed: {total_completed:>3}  |  Overdue: {total_overdue:>3}  |  New: {total_new:>3}")
    
    by_list = insights.get("by_list", {})
    if by_list:
        lines.append("-" * 60)
        lines.append("  By List:")
        for list_name, counts in sorted(by_list.items()):
            c = counts.get("completions", 0)
            o = counts.get("overdue", 0)
            n = counts.get("new_tasks", 0)
            lines.append(f"    {list_name:<30} {c:>2}✓ {o:>2}⚠ {n:>2}➕")
    
    by_tag = insights.get("by_tag", {})
    if by_tag:
        lines.append("-" * 60)
        lines.append("  By Tag:")
        for tag, counts in sorted(by_tag.items()):
            c = counts.get("completions", 0)
            o = counts.get("overdue", 0)
            n = counts.get("new_tasks", 0)
            lines.append(f"    #{tag:<29} {c:>2}✓ {o:>2}⚠ {n:>2}➕")
    
    lines.append("=" * 60)
    return "\n".join(lines)


def format_hygiene_report_cli(
    stagnant: List[Dict],
    missing_due: List[Dict],
    overdue: List[Dict]
) -> str:
    """
    Format hygiene report for terminal display.
    
    Args:
        stagnant: Tasks stagnant for 14+ days
        missing_due: Tasks without due dates
        overdue: Tasks past their due date
    
    Returns:
        Terminal-formatted report
    """
    lines = []
    lines.append("=" * 60)
    lines.append("  REMINDERS HYGIENE REPORT")
    lines.append("=" * 60)
    
    if stagnant:
        lines.append(f"\n  Stagnant (14+ days): {len(stagnant)}")
        for task in stagnant[:5]:  # Limit to top 5
            title = task.get("title", "Untitled")[:40]
            days = task.get("days_stagnant", 0)
            lines.append(f"    • {title} ({days} days)")
        if len(stagnant) > 5:
            lines.append(f"    ... and {len(stagnant) - 5} more")
    
    if missing_due:
        lines.append(f"\n  Missing Due Dates: {len(missing_due)}")
        for task in missing_due[:5]:
            title = task.get("title", "Untitled")[:40]
            lines.append(f"    • {title}")
        if len(missing_due) > 5:
            lines.append(f"    ... and {len(missing_due) - 5} more")
    
    if overdue:
        lines.append(f"\n  Overdue: {len(overdue)}")
        for task in overdue[:5]:
            title = task.get("title", "Untitled")[:40]
            days = task.get("days_overdue", 0)
            lines.append(f"    • {title} ({days} days overdue)")
        if len(overdue) > 5:
            lines.append(f"    ... and {len(overdue) - 5} more")
    
    if not (stagnant or missing_due or overdue):
        lines.append("\n  ✓ All reminders look healthy!")
    
    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def aggregate_insights(vault_insights: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate insights from multiple vaults.
    
    Args:
        vault_insights: List of insight dicts from different vaults
    
    Returns:
        Combined insight dict with totals and breakdowns
    """
    combined = {
        "completions": 0,
        "overdue": 0,
        "new_tasks": 0,
        "by_list": {},
        "by_tag": {}
    }
    
    for insights in vault_insights:
        combined["completions"] += insights.get("completions", 0)
        combined["overdue"] += insights.get("overdue", 0)
        combined["new_tasks"] += insights.get("new_tasks", 0)
        
        # Merge by_list
        for list_name, counts in insights.get("by_list", {}).items():
            if list_name not in combined["by_list"]:
                combined["by_list"][list_name] = {"completions": 0, "overdue": 0, "new_tasks": 0}
            combined["by_list"][list_name]["completions"] += counts.get("completions", 0)
            combined["by_list"][list_name]["overdue"] += counts.get("overdue", 0)
            combined["by_list"][list_name]["new_tasks"] += counts.get("new_tasks", 0)
        
        # Merge by_tag
        for tag, counts in insights.get("by_tag", {}).items():
            if tag not in combined["by_tag"]:
                combined["by_tag"][tag] = {"completions": 0, "overdue": 0, "new_tasks": 0}
            combined["by_tag"][tag]["completions"] += counts.get("completions", 0)
            combined["by_tag"][tag]["overdue"] += counts.get("overdue", 0)
            combined["by_tag"][tag]["new_tasks"] += counts.get("new_tasks", 0)
    
    return combined
