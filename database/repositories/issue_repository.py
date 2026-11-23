"""
Issue and Follow-Up Task Repository.
Manages agricultural incident tracking, CDO escalations, agronomist reviews,
and asynchronous reminder task generation.
"""

import logging
from typing import Optional, List
from datetime import datetime

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func

from database.models import Issue, FollowUpTask, Farmer, CDO, Agronomist
from database.enums import IssuePriority, IssueStatus, TaskTargetRole, TaskStatus

logger = logging.getLogger("IssueRepository")


class IssueRepository:
    """Data access repository for agricultural issues and coordination tasks."""

    def __init__(self, session: Session):
        self.session = session

    def generate_issue_code(self) -> str:
        """Generates a unique structured issue tracking code (e.g. 'ISS-202611-0001')."""
        now = datetime.now()
        prefix = f"ISS-{now.strftime('%Y%m')}-"
        stmt = select(func.count(Issue.id)).where(Issue.issue_code.like(f"{prefix}%"))
        count = (self.session.scalar(stmt) or 0) + 1
        return f"{prefix}{count:04d}"

    def create_issue(
        self,
        farmer_id: int,
        title: str,
        description: str,
        category: str = "GENERAL_QUERY",
        priority: IssuePriority = IssuePriority.MEDIUM,
        farm_plot_id: Optional[int] = None,
        media_urls: Optional[str] = None,
        assigned_cdo_id: Optional[int] = None,
        assigned_agronomist_id: Optional[int] = None
    ) -> Issue:
        """Logs a new agricultural issue or farmer complaint."""
        issue_code = self.generate_issue_code()
        issue = Issue(
            issue_code=issue_code,
            farmer_id=farmer_id,
            farm_plot_id=farm_plot_id,
            category=category,
            priority=priority,
            status=IssueStatus.OPEN,
            title=title.strip(),
            description=description.strip(),
            media_urls=media_urls,
            assigned_cdo_id=assigned_cdo_id,
            assigned_agronomist_id=assigned_agronomist_id
        )
        self.session.add(issue)
        self.session.flush()
        return issue

    def get_by_code(self, issue_code: str) -> Optional[Issue]:
        """Fetch issue by code with farmer and officer relationships."""
        stmt = (
            select(Issue)
            .options(
                joinedload(Issue.farmer),
                joinedload(Issue.assigned_cdo),
                joinedload(Issue.assigned_agronomist),
                joinedload(Issue.farm_plot),
            )
            .where(Issue.issue_code == issue_code)
        )
        return self.session.scalars(stmt).first()

    def escalate_to_cdo(self, issue_id: int, cdo_id: int, notes: Optional[str] = None) -> Issue:
        """Escalates an issue to a Cane Development Officer for ground inspection."""
        stmt = select(Issue).where(Issue.id == issue_id)
        issue = self.session.scalars(stmt).one()
        issue.assigned_cdo_id = cdo_id
        issue.status = IssueStatus.ESCALATED_CDO
        if notes:
            issue.resolution_notes = f"{issue.resolution_notes or ''}\n[CDO Escalation]: {notes}".strip()
        self.session.flush()
        return issue

    def escalate_to_agronomist(self, issue_id: int, agronomist_id: int, notes: Optional[str] = None) -> Issue:
        """Escalates a complex diagnostic issue to a Senior Agronomist."""
        stmt = select(Issue).where(Issue.id == issue_id)
        issue = self.session.scalars(stmt).one()
        issue.assigned_agronomist_id = agronomist_id
        issue.status = IssueStatus.ESCALATED_AGRONOMIST
        if notes:
            issue.resolution_notes = f"{issue.resolution_notes or ''}\n[Agronomist Escalation]: {notes}".strip()
        self.session.flush()
        return issue

    def resolve_issue(self, issue_id: int, resolution_notes: str) -> Issue:
        """Marks an issue as resolved and logs final resolution notes."""
        stmt = select(Issue).where(Issue.id == issue_id)
        issue = self.session.scalars(stmt).one()
        issue.status = IssueStatus.RESOLVED
        issue.resolution_notes = resolution_notes.strip()
        issue.resolved_at = datetime.now()
        self.session.flush()
        return issue

    def list_open_issues(self, limit: int = 50) -> List[Issue]:
        """Returns open and investigating issues."""
        stmt = (
            select(Issue)
            .options(joinedload(Issue.farmer), joinedload(Issue.assigned_cdo))
            .where(Issue.status.in_([IssueStatus.OPEN, IssueStatus.INVESTIGATING, IssueStatus.ESCALATED_CDO, IssueStatus.ESCALATED_AGRONOMIST]))
            .order_by(Issue.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    # -----------------------------------------------------------------------
    # Follow-Up Task Management
    # -----------------------------------------------------------------------

    def create_follow_up_task(
        self,
        issue_id: int,
        target_role: TaskTargetRole,
        description: str,
        target_phone: Optional[str] = None,
        due_date: Optional[datetime] = None
    ) -> FollowUpTask:
        """Creates an actionable follow-up task attached to an issue."""
        task_code = f"TSK-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"
        task = FollowUpTask(
            task_code=task_code,
            issue_id=issue_id,
            target_role=target_role,
            target_phone=target_phone,
            description=description.strip(),
            due_date=due_date,
            status=TaskStatus.PENDING,
            reminder_count=0
        )
        self.session.add(task)
        self.session.flush()
        return task

    def increment_task_reminder(self, task_id: int) -> FollowUpTask:
        """Records a reminder attempt on a pending task."""
        stmt = select(FollowUpTask).where(FollowUpTask.id == task_id)
        task = self.session.scalars(stmt).one()
        task.reminder_count += 1
        task.last_reminder_at = datetime.now()
        self.session.flush()
        return task

    def complete_task(self, task_id: int, notes: Optional[str] = None) -> FollowUpTask:
        """Marks a follow-up task as completed."""
        stmt = select(FollowUpTask).where(FollowUpTask.id == task_id)
        task = self.session.scalars(stmt).one()
        task.status = TaskStatus.COMPLETED
        if notes:
            task.notes = notes.strip()
        self.session.flush()
        return task

    def list_pending_tasks(self, target_role: Optional[TaskTargetRole] = None) -> List[FollowUpTask]:
        """Lists pending or overdue tasks, optionally filtered by target stakeholder."""
        stmt = select(FollowUpTask).where(FollowUpTask.status == TaskStatus.PENDING)
        if target_role:
            stmt = stmt.where(FollowUpTask.target_role == target_role)
        stmt = stmt.order_by(FollowUpTask.due_date.asc().nulls_last())
        return list(self.session.scalars(stmt).all())
