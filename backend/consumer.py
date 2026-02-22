#!/usr/bin/env python3
"""
backend/consumer.py  -- resilient consumer for events:stream

This worker is robust to several message formats:
 - preferred: field "payload" containing JSON with keys: ts, hashtags (list)
 - fallback: field "hashtags" containing CSV string
 - otherwise: ack and skip (no hashtags)
"""
import redis
import json
import time
import logging
from datetime import datetime, timezone
import os

# configuration
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("consumer")

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

def ensure_group():
    try:
        # create group at the end of stream ($) so we don't reprocess old messages by default
        r.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
        log.info("Created consumer group %s on %s", GROUP, STREAM)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            log.debug("Consumer group %s already exists", GROUP)
        else:
            raise

def parse_hashtags_from_fields(fields):
    """
    Robust extraction of hashtags from stream message fields.
    Returns (hashtags_list, ts_ms) where hashtags_list is normalized (lowercase, no '#').
    ts_ms may be None if not present.
    """
    hashtags = []
    ts_ms = None

    # 1) try payload JSON
    payload = fields.get("payload")
    if payload:
        try:
            obj = json.loads(payload)
            # timestamp if present
            ts_ms = obj.get("ts") or obj.get("time")
            h = obj.get("hashtags") or obj.get("tags") or []
            if isinstance(h, list):
                hashtags = [str(x) for x in h if x]
        except Exception:
            log.debug("Failed to parse payload JSON, falling back to other fields")

    # 2) fallback: CSV in 'hashtags' field
    if not hashtags:
        hcsv = fields.get("hashtags")
        if hcsv:
            # sometimes stored like "#AI,#Redis" or "ai,redis"
            try:
                hashtags = [s.strip() for s in hcsv.split(",") if s.strip()]
            except Exception:
                log.debug("Failed to parse hashtags CSV")

    # 3) fallback: maybe producer stored individual fields like 'tag1','tag2' (rare)
    if not hashtags:
        # scan for keys that look like tag fields (e.g., tag0, tag1) - optional heuristic
        tag_keys = [k for k in fields.keys() if k.lower().startswith("tag")]
        if tag_keys:
            hashtags = [fields[k] for k in tag_keys if fields.get(k)]

    # 4) fallback for ts if present as separate 'time' field (string or int)
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

    # normalize tags: lowercase, strip '#', strip whitespace
    clean = []
    for tag in hashtags:
        try:
            t = str(tag).strip().lower().lstrip("#")
            if t:
                clean.append(t)
        except Exception:
            continue

    return clean, ts_ms

def window_key_for_ts(ts_ms):
    # get minute-level window key like 20260222T1437 -> YYYYMMDDHHMM
    if ts_ms is None:
        dt = datetime.utcnow()
    else:
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    window = dt.strftime("%Y%m%d%H%M")
    key = f"{WINDOW_PREFIX}{window}"
    return key, window, int(dt.replace(tzinfo=timezone.utc).timestamp())

def process_message(msg_id, fields):
    try:
        tags, ts_ms = parse_hashtags_from_fields(fields)
        if not tags:
            # nothing to aggregate — ack and move on, but log for debug
            log.info("No hashtags in message %s — fields=%s", msg_id, {k: (v[:200] + '...') if isinstance(v, str) and len(v)>200 else v for k,v in fields.items()})
            r.xack(STREAM, GROUP, msg_id)
            return

        window_key, window_name, window_ts = window_key_for_ts(ts_ms)

        pipe = r.pipeline()
        for tag in tags:
            pipe.zincrby(GLOBAL_RANKING, 1, tag)
            pipe.zincrby(window_key, 1, tag)
        # record active window (score = unix seconds)
        pipe.zadd(WINDOW_INDEX, {window_name: window_ts})
        pipe.execute()

        r.xack(STREAM, GROUP, msg_id)
        log.info("Processed %s tags=%s window=%s", msg_id, ",".join(tags), window_name)
    except Exception as e:
        log.exception("Error processing message %s: %s", msg_id, e)
        # do not ack here so pending can be examined later

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