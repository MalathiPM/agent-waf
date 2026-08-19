"""Audit sink. Every evaluated call is persisted, allowed or blocked."""
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, String, DateTime, JSON, Integer, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://waf:waf@localhost:5432/waf"
)

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=2, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

REDACT_KEYS = {"password", "token", "secret", "api_key", "ssn"}


class AuditRecord(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    request_id = Column(String, index=True)
    timestamp = Column(DateTime(timezone=True), index=True)
    agent_id = Column(String, index=True)
    session_id = Column(String, index=True)
    tool = Column(String, index=True)
    params = Column(JSON)
    disposition = Column(String, index=True)
    matched_rule = Column(String, nullable=True)
    reason = Column(String, nullable=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


def sanitise(params: dict) -> dict:
    out = {}
    for k, v in params.items():
        if k.lower() in REDACT_KEYS:
            out[k] = "[REDACTED]"
        else:
            text_v = str(v)
            out[k] = text_v if len(text_v) <= 500 else text_v[:500] + "...[truncated]"
    return out


def record(*, request_id, agent_id, session_id, tool, params, verdict) -> None:
    with SessionLocal() as db:
        db.add(AuditRecord(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
            agent_id=agent_id,
            session_id=session_id,
            tool=tool,
            params=sanitise(params),
            disposition=verdict.disposition,
            matched_rule=verdict.matched_rule,
            reason=verdict.reason,
        ))
        db.commit()


def query(*, agent_id=None, disposition=None, limit=50) -> list:
    with SessionLocal() as db:
        q = db.query(AuditRecord)
        if agent_id:
            q = q.filter(AuditRecord.agent_id == agent_id)
        if disposition:
            q = q.filter(AuditRecord.disposition == disposition)
        rows = q.order_by(AuditRecord.timestamp.desc()).limit(limit).all()
        return [{
            "request_id": r.request_id,
            "timestamp": r.timestamp.isoformat(),
            "agent_id": r.agent_id,
            "session_id": r.session_id,
            "tool": r.tool,
            "params": r.params,
            "disposition": r.disposition,
            "matched_rule": r.matched_rule,
            "reason": r.reason,
        } for r in rows]


def ping() -> bool:
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
