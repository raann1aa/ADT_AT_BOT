"""
Audit Log Repository.
Provides persistent database logging and metrics reporting for all
incoming farmer queries, actions, RAG citations, and latencies.
"""

import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from database.models import AuditLog

logger = logging.getLogger("AuditRepository")


class AuditRepository:
    """Data access repository for message auditing and dashboard metrics."""

    def __init__(self, session: Session):
        self.session = session

    def log(
        self,
        sender_name: Optional[str],
        sender_phone: str,
        district: Optional[str],
        group_id: Optional[str],
        group_name: Optional[str],
        incoming_text: Optional[str],
        category: str,
        action: str,
        bot_reply: Optional[str] = None,
        rag_sources: Optional[List[str]] = None,
        processing_time_ms: float = 0.0,
        is_escalated: bool = False
    ) -> AuditLog:
        """Persists an interaction audit record."""
        log_id = f"log_{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"
        entry = AuditLog(
            log_id=log_id,
            sender_name=sender_name.strip() if sender_name else "किसान भाई",
            sender_phone=sender_phone.strip(),
            district=district.strip() if district else "General",
            group_id=group_id.strip() if group_id else "group_general",
            group_name=group_name.strip() if group_name else "General Farmer Group",
            incoming_text=incoming_text.strip() if incoming_text else "",
            category=category.strip(),
            action=action.strip(),
            bot_reply=bot_reply,
            rag_sources=json.dumps(rag_sources or [], ensure_ascii=False),
            processing_time_ms=processing_time_ms,
            is_escalated=is_escalated,
            resolved=False
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def get_recent(self, limit: int = 50, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves recent audit entries in reverse chronological order."""
        stmt = select(AuditLog)
        if category:
            stmt = stmt.where(AuditLog.category.ilike(category.strip()))
        stmt = stmt.order_by(desc(AuditLog.timestamp)).limit(limit)
        entries = self.session.scalars(stmt).all()

        results = []
        for e in entries:
            sources = []
            if e.rag_sources:
                try:
                    sources = json.loads(e.rag_sources)
                except Exception:
                    sources = [e.rag_sources]
            results.append({
                "id": e.log_id,
                "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else "",
                "sender_name": e.sender_name,
                "sender_phone": e.sender_phone,
                "district": e.district,
                "group_id": e.group_id,
                "group_name": e.group_name,
                "incoming_text": e.incoming_text,
                "category": e.category,
                "action": e.action,
                "bot_reply": e.bot_reply,
                "rag_sources": sources,
                "processing_time_ms": e.processing_time_ms,
                "is_escalated": e.is_escalated,
                "resolved": e.resolved
            })
        return results

    def get_escalations(self) -> List[Dict[str, Any]]:
        """Returns unresolved escalations requiring human attention."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.is_escalated.is_(True), AuditLog.resolved.is_(False))
            .order_by(desc(AuditLog.timestamp))
        )
        entries = self.session.scalars(stmt).all()
        results = []
        for e in entries:
            sources = []
            if e.rag_sources:
                try:
                    sources = json.loads(e.rag_sources)
                except Exception:
                    sources = [e.rag_sources]
            results.append({
                "id": e.log_id,
                "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else "",
                "sender_name": e.sender_name,
                "sender_phone": e.sender_phone,
                "district": e.district,
                "group_id": e.group_id,
                "group_name": e.group_name,
                "incoming_text": e.incoming_text,
                "category": e.category,
                "action": e.action,
                "bot_reply": e.bot_reply,
                "rag_sources": sources,
                "processing_time_ms": e.processing_time_ms,
                "is_escalated": e.is_escalated,
                "resolved": e.resolved
            })
        return results

    def resolve_escalation(self, log_id: str) -> bool:
        """Marks an escalated incident as resolved."""
        stmt = select(AuditLog).where(AuditLog.log_id == log_id)
        entry = self.session.scalars(stmt).first()
        if entry:
            entry.resolved = True
            self.session.flush()
            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Calculates system performance metrics and category distributions."""
        total = self.session.scalar(select(func.count(AuditLog.id))) or 0
        queries = self.session.scalar(select(func.count(AuditLog.id)).where(AuditLog.category == "FARMING_QUERY")) or 0
        greetings = self.session.scalar(select(func.count(AuditLog.id)).where(AuditLog.category == "GREETING_OR_CHATTER")) or 0
        spam = self.session.scalar(select(func.count(AuditLog.id)).where(AuditLog.category == "SPAM_OR_FORWARD")) or 0
        form_help = self.session.scalar(select(func.count(AuditLog.id)).where(AuditLog.category == "FORM_RELATED")) or 0
        escalations = self.session.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.is_escalated.is_(True), AuditLog.resolved.is_(False))
        ) or 0

        # District distribution
        district_counts: Dict[str, int] = {}
        district_stmt = select(AuditLog.district, func.count(AuditLog.id)).group_by(AuditLog.district)
        for d, count in self.session.execute(district_stmt).all():
            district_counts[d or "General"] = count

        return {
            "total_messages_received": total,
            "queries_answered": queries,
            "noise_filtered": greetings + spam,
            "greetings_ignored": greetings,
            "spam_ignored": spam,
            "form_requests_handled": form_help,
            "pending_escalations": escalations,
            "district_distribution": district_counts
        }
