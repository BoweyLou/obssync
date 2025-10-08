"""
Hygiene analysis for Apple Reminders tasks.

Identifies stagnant tasks, missing due dates, and overdue items
to help maintain a healthy task list.
"""

from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Any
from ..core.models import RemindersTask, TaskStatus


class HygieneAnalyzer:
    """
    Analyzes reminder tasks for hygiene issues.
    
    Identifies:
    - Stagnant tasks (incomplete for 14+ days)
    - Missing due dates
    - Overdue tasks
    """
    
    def __init__(self, stagnant_threshold_days: int = 14):
        """
        Initialize hygiene analyzer.
        
        Args:
            stagnant_threshold_days: Days before a task is considered stagnant
        """
        self.stagnant_threshold = stagnant_threshold_days
    
    def analyze(self, tasks: List[RemindersTask]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Analyze tasks for hygiene issues.
        
        Args:
            tasks: List of RemindersTask objects to analyze
        
        Returns:
            Dict with keys:
                - stagnant: Tasks incomplete for threshold+ days
                - missing_due: Tasks without due dates
                - overdue: Tasks past their due date
        """
        stagnant = []
        missing_due = []
        overdue = []
        
        today = date.today()
        threshold_date = today - timedelta(days=self.stagnant_threshold)
        
        for task in tasks:
            # Skip completed tasks
            if task.status == TaskStatus.DONE:
                continue
            
            # Check for missing due date
            if not task.due_date:
                missing_due.append({
                    "uuid": task.uuid,
                    "title": task.title,
                    "list_name": task.list_name,
                    "created_at": task.created_at.isoformat() if task.created_at else None
                })
                
                # Also check if stagnant (based on created_at)
                if task.created_at:
                    created_date = task.created_at.date() if isinstance(task.created_at, datetime) else task.created_at
                    if created_date <= threshold_date:
                        days_stagnant = (today - created_date).days
                        stagnant.append({
                            "uuid": task.uuid,
                            "title": task.title,
                            "list_name": task.list_name,
                            "days_stagnant": days_stagnant,
                            "created_at": task.created_at.isoformat() if task.created_at else None
                        })
            else:
                # Check if overdue
                if task.due_date < today:
                    days_overdue = (today - task.due_date).days
                    overdue.append({
                        "uuid": task.uuid,
                        "title": task.title,
                        "list_name": task.list_name,
                        "due_date": task.due_date.isoformat(),
                        "days_overdue": days_overdue
                    })
                
                # Check if stagnant (incomplete for threshold+ days)
                # Use modified_at if available, otherwise created_at
                check_date = task.modified_at or task.created_at
                if check_date:
                    check_date_val = check_date.date() if isinstance(check_date, datetime) else check_date
                    if check_date_val <= threshold_date:
                        days_stagnant = (today - check_date_val).days
                        # Avoid duplicating overdue tasks in stagnant
                        if task.due_date >= today or not task.due_date:
                            stagnant.append({
                                "uuid": task.uuid,
                                "title": task.title,
                                "list_name": task.list_name,
                                "days_stagnant": days_stagnant,
                                "last_modified": check_date.isoformat() if check_date else None
                            })
        
        # Sort by severity
        stagnant.sort(key=lambda x: x.get("days_stagnant", 0), reverse=True)
        overdue.sort(key=lambda x: x.get("days_overdue", 0), reverse=True)
        
        return {
            "stagnant": stagnant,
            "missing_due": missing_due,
            "overdue": overdue
        }
    
    def get_summary(self, analysis: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
        """
        Get summary counts from analysis.
        
        Args:
            analysis: Result from analyze()
        
        Returns:
            Dict with count for each category
        """
        return {
            "stagnant_count": len(analysis.get("stagnant", [])),
            "missing_due_count": len(analysis.get("missing_due", [])),
            "overdue_count": len(analysis.get("overdue", []))
        }
    
    def get_actionable_suggestions(
        self,
        analysis: Dict[str, List[Dict[str, Any]]],
        max_suggestions: int = 5
    ) -> List[str]:
        """
        Generate actionable suggestions based on analysis.
        
        Args:
            analysis: Result from analyze()
            max_suggestions: Maximum number of suggestions to return
        
        Returns:
            List of suggestion strings
        """
        suggestions = []
        
        stagnant = analysis.get("stagnant", [])
        missing_due = analysis.get("missing_due", [])
        overdue = analysis.get("overdue", [])
        
        if overdue:
            top_overdue = overdue[0]
            suggestions.append(
                f"Address overdue task: '{top_overdue['title']}' "
                f"({top_overdue['days_overdue']} days overdue)"
            )
        
        if stagnant:
            top_stagnant = stagnant[0]
            suggestions.append(
                f"Review stagnant task: '{top_stagnant['title']}' "
                f"({top_stagnant['days_stagnant']} days inactive)"
            )
        
        if missing_due and len(suggestions) < max_suggestions:
            suggestions.append(
                f"Add due dates to {len(missing_due)} task(s) for better planning"
            )
        
        if len(stagnant) > 3 and len(suggestions) < max_suggestions:
            suggestions.append(
                f"Consider archiving or deleting {len(stagnant)} stagnant tasks"
            )
        
        return suggestions[:max_suggestions]
