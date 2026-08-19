"""Session state in Redis. Survives restarts, shared across instances."""
import os
import redis

_r = redis.Redis.from_url(
    os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True,
)

WINDOW_SECONDS = 60
SESSION_TTL = 3600


def _rate_key(session_id: str, tool: str) -> str:
    return f"waf:rate:{session_id}:{tool}"


def _seq_key(session_id: str) -> str:
    return f"waf:seq:{session_id}"


def record_call(session_id: str, tool: str) -> None:
    pipe = _r.pipeline()
    pipe.incr(_rate_key(session_id, tool))
    pipe.expire(_rate_key(session_id, tool), WINDOW_SECONDS)
    pipe.rpush(_seq_key(session_id), tool)
    pipe.expire(_seq_key(session_id), SESSION_TTL)
    pipe.execute()


def counts_last_minute(session_id: str) -> dict:
    keys = _r.keys(f"waf:rate:{session_id}:*")
    if not keys:
        return {}
    values = _r.mget(keys)
    return {k.rsplit(":", 1)[1]: int(v) for k, v in zip(keys, values) if v}


def tools_called(session_id: str) -> list:
    return _r.lrange(_seq_key(session_id), 0, -1)


def ping() -> bool:
    try:
        return _r.ping()
    except redis.RedisError:
        return False


def reset(session_id: str) -> None:
    keys = _r.keys(f"waf:*:{session_id}*")
    if keys:
        _r.delete(*keys)
