"""
Command implementations for obs-sync.
"""

from .setup import SetupCommand
from .sync import SyncCommand
from .calendar import CalendarCommand
from .install_deps import InstallDepsCommand
from .migrate import MigrateCommand
from .insights import InsightsCommand
from .update import UpdateCommand
from .process import ProcessCommand
from .automation import AutomationCommand

__all__ = [
    'SetupCommand',
    'SyncCommand',
    'CalendarCommand',
    'InstallDepsCommand',
    'MigrateCommand',
    'InsightsCommand',
    'UpdateCommand',
    'ProcessCommand',
    'AutomationCommand',
]