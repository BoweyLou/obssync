"""Insights command - analyze task hygiene and provide recommendations."""

import json
import logging
from typing import Optional

from ..core.config import SyncConfig
from ..reminders.tasks import RemindersTaskManager
from ..analytics.hygiene import HygieneAnalyzer
from ..utils.insights import format_hygiene_report_cli


class InsightsCommand:
    """Command for analyzing task hygiene and providing insights."""
    
    def __init__(self, config: SyncConfig, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        if verbose:
            self.logger.setLevel(logging.DEBUG)
    
    def run(self, export_json: Optional[str] = None) -> bool:
        """
        Run the insights command to analyze task hygiene.
        
        Args:
            export_json: Optional path to export JSON report
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.config.enable_hygiene_assistant:
                print("⚠️  Hygiene assistant is disabled in config.")
                print("Enable it in setup or set 'enable_hygiene_assistant: true' in your config.")
                return False
            
            # Get list of reminder lists to analyze
            list_ids = self.config.reminder_list_ids
            if not list_ids:
                print("⚠️  No Reminders lists configured. Run 'obs-sync setup' first.")
                return False
            
            print("\n🔍 Analyzing task hygiene across all configured Reminders lists...")
            print("=" * 60)
            
            # Fetch all tasks
            rem_manager = RemindersTaskManager(logger=self.logger)
            tasks = rem_manager.list_tasks(list_ids, include_completed=False)
            
            if not tasks:
                print("\n✓ No incomplete tasks found.")
                return True
            
            print(f"\n📋 Analyzing {len(tasks)} incomplete tasks...")
            
            # Run hygiene analysis
            threshold = self.config.hygiene_stagnant_threshold
            analyzer = HygieneAnalyzer(stagnant_threshold_days=threshold)
            analysis = analyzer.analyze(tasks)
            
            # Display report
            stagnant = analysis.get('stagnant', [])
            missing_due = analysis.get('missing_due', [])
            overdue = analysis.get('overdue', [])
            
            print(format_hygiene_report_cli(stagnant, missing_due, overdue))
            
            # Show actionable suggestions
            suggestions = analyzer.get_actionable_suggestions(analysis, max_suggestions=5)
            if suggestions:
                print("\n💡 Suggested Actions:")
                for i, suggestion in enumerate(suggestions, 1):
                    print(f"  {i}. {suggestion}")
                print("")
            
            # Export to JSON if requested
            if export_json:
                self._export_json(analysis, export_json)
                print(f"\n📄 Report exported to: {export_json}")
            
            return True
            
        except Exception as exc:
            self.logger.error("Insights command failed: %s", exc)
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    def _export_json(self, analysis: dict, output_path: str) -> None:
        """Export analysis results to JSON file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'stagnants': analysis.get('stagnant', []),
                'missing_due': analysis.get('missing_due', []),
                'overdue': analysis.get('overdue', []),
                'summary': {
                    'total_stagnant': len(analysis.get('stagnant', [])),
                    'total_missing_due': len(analysis.get('missing_due', [])),
                    'total_overdue': len(analysis.get('overdue', []))
                }
            }, f, indent=2)
