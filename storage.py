import json
import os
from typing import Any

REDIS_URL = (
    os.environ.get("REDIS_URL")
    or os.environ.get("KV_URL")
    or os.environ.get("UPSTASH_REDIS_URL")
    or ""
).strip()

KEY_PREFIX = "qp:"
IDS_KEY = f"{KEY_PREFIX}submission_ids"
COUNTER_KEY = f"{KEY_PREFIX}next_id"

_redis = None
_memory_store: dict[int, dict[str, Any]] = {}
_memory_ids: list[int] = []
_memory_counter = 0


def _use_redis() -> bool:
    return bool(REDIS_URL)


def _get_redis():
    global _redis
    if _redis is None:
        import redis

        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def init_db():
    """No schema setup needed for Redis; kept for app startup compatibility."""
    if _use_redis():
        client = _get_redis()
        client.ping()


def _submission_key(submission_id: int) -> str:
    return f"{KEY_PREFIX}submission:{submission_id}"


def insert_submission(name: str, responses: list, submitted_at: str) -> int:
    if _use_redis():
        client = _get_redis()
        submission_id = client.incr(COUNTER_KEY)
        payload = {
            "id": submission_id,
            "name": name,
            "responses": responses,
            "submitted_at": submitted_at,
        }
        client.set(_submission_key(submission_id), json.dumps(payload))
        client.lpush(IDS_KEY, submission_id)
        return submission_id

    global _memory_counter
    _memory_counter += 1
    submission_id = _memory_counter
    _memory_store[submission_id] = {
        "id": submission_id,
        "name": name,
        "responses": responses,
        "submitted_at": submitted_at,
    }
    _memory_ids.insert(0, submission_id)
    return submission_id


def list_submissions() -> list[dict]:
    if _use_redis():
        client = _get_redis()
        ids = client.lrange(IDS_KEY, 0, -1)
        submissions = []
        for raw_id in ids:
            data = client.get(_submission_key(int(raw_id)))
            if data:
                submissions.append(json.loads(data))
        return submissions

    return [_memory_store[i] for i in _memory_ids if i in _memory_store]


def get_submission(submission_id: int) -> dict | None:
    if _use_redis():
        client = _get_redis()
        data = client.get(_submission_key(submission_id))
        return json.loads(data) if data else None

    return _memory_store.get(submission_id)


def storage_backend_name() -> str:
    if _use_redis():
        return "redis"
    return "memory"
