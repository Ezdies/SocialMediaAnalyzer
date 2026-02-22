#!/usr/bin/env python3
"""
backend/consumer.py  -- idempotent, robust consumer for events:stream

Behavior:
 - reads from Redis Stream events:stream as consumer group
 - extracts event_id from payload (preferred)
 - uses SET NX EX on processed:{event_id} to avoid double processing
 - updates global and windowed hashtag ZSETs
 - acknowledges processed messages (XACK)
 - periodically cleans up old windows

Usage:
  python3 backend/consumer.py
Environment:
  REDIS_HOST, REDIS_PORT, REDIS_DB, STREAM_KEY, GROUP_NAME, CONSUMER_NAME,
  BATCH_SIZE, BLOCK_MS, RETENTION_MINUTES, DEDUPE_TTL_SECONDS
"""
import redis
import json
import time
import logging
import os
from datetime import datetime, timezone

# CONFIG (can be overridden via env)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

STREAM = os.getenv("STREAM_KEY", "events:stream")
GROUP = os.getenv("GROUP_NAME", "events_group")
CONSUMER = os.getenv("CONSUMER_NAME", f"consumer-{os.getpid()}")

GLOBAL_RANKING = os.getenv("GLOBAL_RANKING", "hashtags:ranking")
WINDOW_INDEX = os.getenv("WINDOW_INDEX", "hashtags:windows")
WINDOW_PREFIX = os.getenv("WINDOW_PREFIX", "hashtags:ranking:")

BATCH_SIZE = int(os.getenv("BATCH_SIZE", 50))
BLOCK_MS = int(os.getenv("BLOCK_MS", 5000))
RETENTION_MINUTES = int(os.getenv("RETENTION_MINUTES", 60))
DEDUPE_TTL_SECONDS = int(os.getenv("DEDUPE_TTL_SECONDS", 7 * 24 * 3600))  # default 7 days

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("consumer")

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

def ensure_group():
    """Create consumer group if missing; start at '$' to avoid reprocessing by default."""
    try:
        r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
        log.info("Created consumer group %s on %s", GROUP, STREAM)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            log.debug("Consumer group %s already exists", GROUP)
        else:
            raise

def parse_hashtags_from_fields(fields):
    """
    Extract hashtags, event type, user_id, and timestamp robustly from stream message fields.
    Returns (tags_list, event_type, user_id, ts_ms, payload_obj)
    """
    tags = []
    event_type = None
    user_id = None
    ts_ms = None
    payload_obj = {}

    payload = fields.get("payload")
    if payload:
        try:
            payload_obj = json.loads(payload)
            ts_ms = payload_obj.get("ts") or payload_obj.get("time")
            event_type = payload_obj.get("type")
            user_id = payload_obj.get("user_id")
            h = payload_obj.get("hashtags") or payload_obj.get("tags") or []
            if isinstance(h, list):
                tags = [str(x) for x in h if x]
        except Exception:
            log.debug("Failed to parse payload JSON", exc_info=True)

    # Fallback for old format: try to get type and user from direct fields
    if not event_type:
        event_type = fields.get("type")
    if not user_id:
        user_id = fields.get("user_id") or fields.get("user")

    if not tags:
        hcsv = fields.get("hashtags")
        if hcsv:
            try:
                tags = [s.strip() for s in hcsv.split(",") if s.strip()]
            except Exception:
                log.debug("Failed to parse hashtags CSV", exc_info=True)

    if not tags:
        # heuristic: any field name that looks like 'tag' or 'hashtagX'
        for k, v in fields.items():
            if k.lower().startswith("tag") or k.lower().startswith("hashtag"):
                if v:
                    tags.append(v)

    # fallback ts from 'time' field (string)
    if ts_ms is None:
        tfield = fields.get("time") or fields.get("ts")
        if tfield:
            try:
                ts_ms = int(tfield)
            except Exception:
                try:
                    ts_ms = int(float(tfield) * 1000)
                except Exception:
                    ts_ms = None

    # normalize tags
    clean = []
    for tag in tags:
        try:
            t = str(tag).strip().lower().lstrip("#")
            if t:
                clean.append(t)
        except Exception:
            continue

    return clean, event_type, user_id, ts_ms, payload_obj

def window_key_for_ts(ts_ms):
    if ts_ms is None:
        dt = datetime.utcnow()
    else:
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    window = dt.strftime("%Y%m%d%H%M")
    key = f"{WINDOW_PREFIX}{window}"
    return key, window, int(dt.replace(tzinfo=timezone.utc).timestamp())

def process_message(msg_id, fields):
    try:
        tags, event_type, user_id, ts_ms, payload_obj = parse_hashtags_from_fields(fields)

        if not tags and not event_type:
            # nothing to aggregate — ack and continue
            log.info("No hashtags or event type in message %s — fields=%s", msg_id, {k: (v[:200] + '...') if isinstance(v, str) and len(v)>200 else v for k,v in fields.items()})
            r.xack(STREAM, GROUP, msg_id)
            return

        # attempt dedupe by event_id in payload (best) or fallback to message-id (less ideal)
        event_id = payload_obj.get("event_id") if isinstance(payload_obj, dict) else None
        if event_id:
            dedupe_key = f"processed:{event_id}"
            # SET NX EX — returns True if set, None/False if already exists
            was_set = r.set(dedupe_key, "1", nx=True, ex=DEDUPE_TTL_SECONDS)
            if not was_set:
                # already processed
                r.xack(STREAM, GROUP, msg_id)
                log.info("Duplicate detected — skipping event_id=%s msg=%s", event_id, msg_id)
                return
        else:
            # no event_id: optional strategy could be to dedupe by message-id, but skip for now
            pass

        window_key, window_name, window_ts = window_key_for_ts(ts_ms)

        pipe = r.pipeline()
        
        # Update hashtag rankings
        for tag in tags:
            pipe.zincrby(GLOBAL_RANKING, 1, tag)
            pipe.zincrby(window_key, 1, tag)
        pipe.zadd(WINDOW_INDEX, {window_name: window_ts})
        
        # Update event type statistics
        if event_type:
            stats_key = f"stats:{event_type}"
            pipe.incr(stats_key)
        
        # Update user activity rankings
        if user_id:
            pipe.zincrby("users:activity", 1, user_id)
            pipe.zincrby(f"users:activity:{window_name}", 1, user_id)
        
        # Store recent comments (keep last 100)
        try:
            comment = None
            if isinstance(payload_obj, dict):
                comment = payload_obj.get('comment')
            if comment:
                comment_obj = json.dumps({"user": user_id or "", "comment": str(comment), "ts": ts_ms or int(time.time() * 1000)})
                pipe.lpush("recent:comments", comment_obj)
                pipe.ltrim("recent:comments", 0, 99)
        except Exception:
            log.debug("Failed to push recent comment", exc_info=True)
        
        pipe.execute()

        r.xack(STREAM, GROUP, msg_id)
        log.info("Processed %s tags=%s event_type=%s user=%s window=%s", msg_id, ",".join(tags), event_type, user_id, window_name)
    except Exception as e:
        log.exception("Error processing message %s: %s", msg_id, e)
        # do not ack on unexpected error — message remains in pending for investigation

def cleanup_old_windows(retention_minutes):
    try:
        cutoff = int(time.time()) - (retention_minutes * 60)
        old = r.zrangebyscore(WINDOW_INDEX, 0, cutoff)
        if not old:
            return
        log.info("Cleaning %d old windows (cutoff=%d)", len(old), cutoff)
        pipe = r.pipeline()
        for window_name in old:
            pipe.delete(f"{WINDOW_PREFIX}{window_name}")
            pipe.zrem(WINDOW_INDEX, window_name)
        pipe.execute()
    except Exception:
        log.exception("Error during cleanup_old_windows")

def main_loop():
    ensure_group()
    last_cleanup = time.time()
    while True:
        try:
            resp = r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=BATCH_SIZE, block=BLOCK_MS)
            if resp:
                for stream_name, messages in resp:
                    for msg_id, fields in messages:
                        process_message(msg_id, fields)

            if time.time() - last_cleanup > 30:
                cleanup_old_windows(RETENTION_MINUTES)
                last_cleanup = time.time()
        except redis.exceptions.ResponseError as re:
            log.exception("Redis ResponseError (ensuring group): %s", re)
            try:
                ensure_group()
            except Exception:
                time.sleep(1)
        except Exception as e:
            log.exception("Error in main loop: %s", e)
            time.sleep(1)

if __name__ == "__main__":
    log.info("Starting consumer. STREAM=%s GROUP=%s CONSUMER=%s", STREAM, GROUP, CONSUMER)
    main_loop()