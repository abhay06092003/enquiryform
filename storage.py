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

_rest_client = None
_redis = None
_memory_store: dict[int, dict[str, Any]] = {}
_memory_ids: list[int] = []
_memory_counter = 0


def _sync_rest_env_aliases() -> None:
    """Map Vercel KV env names to the ones upstash-redis expects."""
    if not os.environ.get("UPSTASH_REDIS_REST_URL", "").strip():
        kv_url = os.environ.get("KV_REST_API_URL", "").strip()
        if kv_url:
            os.environ["UPSTASH_REDIS_REST_URL"] = kv_url
    if not os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip():
        kv_token = os.environ.get("KV_REST_API_TOKEN", "").strip()
        if kv_token:
            os.environ["UPSTASH_REDIS_REST_TOKEN"] = kv_token


def _rest_credentials() -> tuple[str, str]:
    _sync_rest_env_aliases()
    url = (
        os.environ.get("UPSTASH_REDIS_REST_URL")
        or os.environ.get("KV_REST_API_URL")
        or ""
    ).strip()
    token = (
        os.environ.get("UPSTASH_REDIS_REST_TOKEN")
        or os.environ.get("KV_REST_API_TOKEN")
        or ""
    ).strip()
    return url, token


def _use_rest() -> bool:
    url, token = _rest_credentials()
    return bool(url and token)


def _use_redis_url() -> bool:
    return bool(REDIS_URL)


def is_persistent_storage() -> bool:
    return _use_rest() or _use_redis_url()


def _active_backend() -> str:
    if _use_rest():
        return "rest"
    if _use_redis_url():
        return "redis"
    return "memory"


def _get_rest():
    global _rest_client
    if _rest_client is None:
        from upstash_redis import Redis

        _sync_rest_env_aliases()
        _rest_client = Redis.from_env()
    return _rest_client


def _get_redis():
    global _redis
    if _redis is None:
        import redis

        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def init_db():
    """Verify connectivity to the configured persistent store."""
    backend = _active_backend()
    if backend == "rest":
        _get_rest().ping()
    elif backend == "redis":
        _get_redis().ping()


def _submission_key(submission_id: int) -> str:
    return f"{KEY_PREFIX}submission:{submission_id}"


def insert_submission(name: str, responses: list, submitted_at: str) -> int:
    backend = _active_backend()
    if backend == "rest":
        client = _get_rest()
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

    if backend == "redis":
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
    backend = _active_backend()
    if backend == "rest":
        client = _get_rest()
        ids = client.lrange(IDS_KEY, 0, -1)
        submissions = []
        for raw_id in ids:
            data = client.get(_submission_key(int(raw_id)))
            if data:
                submissions.append(json.loads(data))
        return submissions

    if backend == "redis":
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
    backend = _active_backend()
    if backend == "rest":
        client = _get_rest()
        data = client.get(_submission_key(submission_id))
        return json.loads(data) if data else None

    if backend == "redis":
        client = _get_redis()
        data = client.get(_submission_key(submission_id))
        return json.loads(data) if data else None

    return _memory_store.get(submission_id)


def storage_backend_name() -> str:
    backend = _active_backend()
    if backend in ("rest", "redis"):
        return "redis"
    return "memory"
