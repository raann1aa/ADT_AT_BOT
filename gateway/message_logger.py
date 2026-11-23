"""
Message Audit Logger and Activity Tracker for Admin Dashboard.
Persists interaction logs, category metrics, and human escalation alerts
to the relational database with in-memory caching.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import deque

from database.connection import get_db_session, init_db
from database.repositories import AuditRepository

logger = logging.getLogger("AuditLogger")


class MessageLogEntry:
    def __init__(
        self,
        id: str,
        timestamp: str,
        sender_name: str,
        sender_phone: str,
        district: str,
        group_id: str,
        group_name: str,
        incoming_text: str,
        category: str,
        action: str,
        bot_reply: Optional[str] = None,
        rag_sources: Optional[List[str]] = None,
        processing_time_ms: float = 0.0,
        is_escalated: bool = False,
        resolved: bool = False
    ):
        self.id = id
        self.timestamp = timestamp
        self.sender_name = sender_name
        self.sender_phone = sender_phone
        self.district = district
        self.group_id = group_id
        self.group_name = group_name
        self.incoming_text = incoming_text
        self.category = category
        self.action = action
        self.bot_reply = bot_reply
        self.rag_sources = rag_sources or []
        self.processing_time_ms = processing_time_ms
        self.is_escalated = is_escalated
        self.resolved = resolved

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "sender_name": self.sender_name,
            "sender_phone": self.sender_phone,
            "district": self.district,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "incoming_text": self.incoming_text,
            "category": self.category,
            "action": self.action,
            "bot_reply": self.bot_reply,
            "rag_sources": self.rag_sources,
            "processing_time_ms": self.processing_time_ms,
            "is_escalated": self.is_escalated,
            "resolved": self.resolved
        }


class AuditLogger:
    """
    Manages persistent audit logging for WhatsApp group and 1-to-1 interactions.
    Writes to database while maintaining recent in-memory cache for ultra-fast rendering.
    """

    def __init__(self, max_history: int = 500):
        self.logs: deque[MessageLogEntry] = deque(maxlen=max_history)
        init_db()
        self._sync_from_database()

    def _sync_from_database(self):
        """Loads recent logs from database if present, or initializes initial records."""
        try:
            with get_db_session() as session:
                repo = AuditRepository(session)
                recent = repo.get_recent(limit=50)
                if recent:
                    for r in reversed(recent):
                        entry = MessageLogEntry(
                            id=r["id"],
                            timestamp=r["timestamp"],
                            sender_name=r["sender_name"],
                            sender_phone=r["sender_phone"],
                            district=r["district"],
                            group_id=r["group_id"],
                            group_name=r["group_name"],
                            incoming_text=r["incoming_text"],
                            category=r["category"],
                            action=r["action"],
                            bot_reply=r["bot_reply"],
                            rag_sources=r["rag_sources"],
                            processing_time_ms=r["processing_time_ms"],
                            is_escalated=r["is_escalated"],
                            resolved=r["resolved"]
                        )
                        self.logs.appendleft(entry)
                else:
                    self._init_sample_history()
        except Exception as e:
            logger.error(f"Failed to sync audit logs from database: {e}")
            self._init_sample_history()

    def log(
        self,
        sender_name: str,
        sender_phone: str,
        district: str,
        group_id: str,
        group_name: str,
        incoming_text: str,
        category: str,
        action: str,
        bot_reply: Optional[str] = None,
        rag_sources: Optional[List[str]] = None,
        processing_time_ms: float = 0.0,
        is_escalated: bool = False
    ) -> MessageLogEntry:
        """Persists log to database and appends to in-memory deque."""
        log_id = f"log_{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Persist to database
        try:
            with get_db_session() as session:
                repo = AuditRepository(session)
                db_entry = repo.log(
                    sender_name=sender_name,
                    sender_phone=sender_phone,
                    district=district,
                    group_id=group_id,
                    group_name=group_name,
                    incoming_text=incoming_text,
                    category=category,
                    action=action,
                    bot_reply=bot_reply,
                    rag_sources=rag_sources,
                    processing_time_ms=processing_time_ms,
                    is_escalated=is_escalated
                )
                log_id = db_entry.log_id
        except Exception as e:
            logger.error(f"Failed to persist audit log to DB: {e}")

        # 2. Append to memory deque
        entry = MessageLogEntry(
            id=log_id,
            timestamp=timestamp_str,
            sender_name=sender_name,
            sender_phone=sender_phone,
            district=district,
            group_id=group_id,
            group_name=group_name,
            incoming_text=incoming_text,
            category=category,
            action=action,
            bot_reply=bot_reply,
            rag_sources=rag_sources or [],
            processing_time_ms=processing_time_ms,
            is_escalated=is_escalated
        )
        self.logs.appendleft(entry)
        return entry

    def get_recent(self, limit: int = 50, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves recent logs from DB if available, falling back to cache."""
        try:
            with get_db_session() as session:
                repo = AuditRepository(session)
                return repo.get_recent(limit=limit, category=category)
        except Exception as e:
            logger.error(f"DB error fetching recent logs, falling back to memory: {e}")
            results = []
            for item in self.logs:
                if category and item.category.lower() != category.lower():
                    continue
                results.append(item.to_dict())
                if len(results) >= limit:
                    break
            return results

    def get_escalations(self) -> List[Dict[str, Any]]:
        """Retrieves active escalations requiring attention."""
        try:
            with get_db_session() as session:
                repo = AuditRepository(session)
                return repo.get_escalations()
        except Exception as e:
            logger.error(f"DB error fetching escalations: {e}")
            return [item.to_dict() for item in self.logs if item.is_escalated and not item.resolved]

    def resolve_escalation(self, log_id: str) -> bool:
        """Marks escalation as resolved in database and in-memory cache."""
        resolved = False
        try:
            with get_db_session() as session:
                repo = AuditRepository(session)
                resolved = repo.resolve_escalation(log_id)
        except Exception as e:
            logger.error(f"DB error resolving escalation {log_id}: {e}")

        for item in self.logs:
            if item.id == log_id:
                item.resolved = True
                resolved = True
                break
        return resolved

    def get_stats(self) -> Dict[str, Any]:
        """Calculates system metrics from database."""
        try:
            with get_db_session() as session:
                repo = AuditRepository(session)
                return repo.get_stats()
        except Exception as e:
            logger.error(f"DB error fetching stats: {e}")
            total = len(self.logs)
            queries = sum(1 for l in self.logs if l.category == "FARMING_QUERY")
            greetings = sum(1 for l in self.logs if l.category == "GREETING_OR_CHATTER")
            spam = sum(1 for l in self.logs if l.category == "SPAM_OR_FORWARD")
            form_help = sum(1 for l in self.logs if l.category == "FORM_RELATED")
            escalations = sum(1 for l in self.logs if l.is_escalated and not l.resolved)
            
            district_counts: Dict[str, int] = {}
            for l in self.logs:
                d = l.district or "General"
                district_counts[d] = district_counts.get(d, 0) + 1

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

    def _init_sample_history(self):
        """Pre-populates a few realistic baseline events into the audit log."""
        samples = [
            ("Ramesh Patil", "9823011111", "Nashik", "group_nashik_01", "नाशिक जिल्हा शेतकरी गट", "Good morning all farmers 🙏", "GREETING_OR_CHATTER", "IGNORED", None, [], 0.42, False),
            ("Dnyaneshwar Shinde", "9823022222", "Nashik", "group_nashik_01", "नाशिक जिल्हा शेतकरी गट", "Kanda storage rot aur purple blotch dawai bataye", "FARMING_QUERY", "ANSWERED", "Carbendazim 50 WP @ 1g/L pre-harvest spray and 50% neck-fall curing.", ["Purple Blotch in Onion > Storage Rot"], 42.1, False),
            ("Vinod Gaikwad", "9823033333", "Nashik", "group_nashik_01", "नाशिक जिल्हा शेतकरी गट", "Forwarded: आज का सुविचार - धर्म की जय हो!", "SPAM_OR_FORWARD", "IGNORED", None, [], 0.35, False),
            ("Suresh Yadav", "9876533333", "Indore", "group_indore_02", "इंदौर मालवा किसान समूह", "Sir weekly farm details ka google form link bhejo", "FORM_RELATED", "FORM_HELP", "Form link: https://forms.gle/WeeklyFarmerSurvey", [], 0.15, False),
            ("Popat Rao", "9890066666", "Nashik", "group_nashik_01", "नाशिक जिल्हा शेतकरी गट", "Kapas me gulabi sundi ke liye trap kitne lagaye?", "FARMING_QUERY", "ANSWERED", "Install 4-5 Gossyplure pheromone traps per acre.", ["Pink Bollworm in Cotton > Trapping"], 44.5, False),
            ("Harpreet Singh", "9814044444", "Ludhiana", "group_ludhiana_03", "Ludhiana Progressive Farmers", "Wheat yellow rust symptoms and tilt spray dosage", "FARMING_QUERY", "ANSWERED", "Propiconazole 25% EC (Tilt) @ 200 ml per acre in 200L water.", ["Yellow Rust in Wheat > Chemical Control"], 38.9, False),
            ("Baldev Singh", "9814055555", "Ludhiana", "group_ludhiana_03", "Ludhiana Progressive Farmers", "Sat Sri Akal ji saareyan nu 🙏", "GREETING_OR_CHATTER", "IGNORED", None, [], 0.31, False),
        ]
        for s in samples:
            self.log(s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9], s[10], s[11])
