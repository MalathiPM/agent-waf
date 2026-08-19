"""Session state in Postgres.

Redis is the better fit for hot counters in a high-throughput deployment; we
consolidated on Postgres here to reduce operational surface. At scale the rate
counter would move to Redis INCR, which this module''s interface allows without
touching callers.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.orm import declarative_base

from waf.audit import SessionLocal, engine

Base = declarative_base()

WINDOW_SECONDS = 60
SESSION_TTL_SECONDS = 3600


class CallEvent(Base):
    __tablename__ = "session_calls"

    id = Column(Integer, primary_key=True)
    session_id = Column(String, index=True, nullable=False)
    tool = Column(String, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), index=True, nullable=False)


def init_state() -> None:
    Base.metadata.create_all(engine)


def record_call(session_id: str, tool: str) -> None:
    with SessionLocal() as db:
        db.add(CallEvent(session_id=session_id, tool=tool,
                         created_at=datetime.now(timezone.utc)))
        db.commit()


def counts_last_minute(session_id: str) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=WINDOW_SECONDS)
    with SessionLocal() as db:
        rows = (db.query(CallEvent.tool, func.count(CallEvent.id))
                  .filter(CallEvent.session_id == session_id,
                          CallEvent.created_at >= cutoff)
                  .group_by(CallEvent.tool)
                  .all())
        return {tool: count for tool, count in rows}


def tools_called(session_id: str) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=SESSION_TTL_SECONDS)
    with SessionLocal() as db:
        rows = (db.query(CallEvent.tool)
                  .filter(CallEvent.session_id == session_id,
                          CallEvent.created_at >= cutoff)
                  .order_by(CallEvent.created_at)
                  .all())
        return [r[0] for r in rows]


def ping() -> bool:
    from waf.audit import ping as db_ping
    return db_ping()


def reset(session_id: str) -> None:
    with SessionLocal() as db:
        db.query(CallEvent).filter(CallEvent.session_id == session_id).delete()
        db.commit()
