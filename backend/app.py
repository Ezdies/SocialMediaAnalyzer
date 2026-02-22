from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Literal
import redis
import time
import json
import os
from uuid import uuid4
from datetime import datetime, timezone, timedelta

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

app = FastAPI(title="Social Trends Analyzer (producer-only)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Event(BaseModel):
    type: Literal["like", "comment", "share", "hashtag"]
    hashtags: Optional[List[str]] = []
    comment: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Optional[dict] = {}

@app.get("/api/health")
def health():
    try:
        pong = r.ping()
        return {"status": "ok", "redis": bool(pong)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"redis error: {str(e)}")

@app.post("/api/events")
def post_event(ev: Event):
    """
    Producer: jedynie zapisuje pełny event do streama (events:stream).
    Zwraca event_id (UUID) aby ułatwić testy idempotencji.
    """
    ts = int(time.time() * 1000)
    event_id = str(uuid4())
    payload_obj = {
        "event_id": event_id,
        "type": ev.type,
        "hashtags": ev.hashtags or [],
        "comment": ev.comment or "",
        "user_id": ev.user_id or "",
        "metadata": ev.metadata or {},
        "ts": ts
    }
    payload_str = json.dumps(payload_obj, ensure_ascii=False)

    try:
        hashtags_csv = ",".join([h.strip() for h in (ev.hashtags or []) if h])
        # zapis do streama tylko
        r.xadd("events:stream", {"payload": payload_str, "time": ts, "hashtags": hashtags_csv})
    except redis.RedisError as re:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(re)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    return {"result": "ok", "ts": ts, "event_id": event_id}

# Endpointy do odczytu wyników (materializowanych przez consumer)
@app.get("/api/trends/hashtags")
def top_hashtags(n: int = 10):
    try:
        raw = r.zrevrange("hashtags:ranking", 0, n - 1, withscores=True)
        out = [{"hashtag": member, "count": int(score)} for member, score in raw]
        return out
    except redis.RedisError as re:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(re)}")

@app.get("/api/stats/interactions")
def stats():
    try:
        likes = int(r.get("stats:like") or 0)
        comments = int(r.get("stats:comment") or 0)
        shares = int(r.get("stats:share") or 0)
        return {"likes": likes, "comments": comments, "shares": shares}
    except redis.RedisError as re:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(re)}")

@app.get("/api/trends/hashtags/period")
def top_hashtags_by_period(period: str = "1h", n: int = 10):
    """
    Get top hashtags for a specific time period.
    Periods: 1h, 24h, 7d
    """
    try:
        # Calculate window name based on period
        now = datetime.now(timezone.utc)
        
        if period == "1h":
            window_name = now.strftime("%Y%m%d%H%M")
            key = f"hashtags:ranking:{window_name}"
        elif period == "24h":
            # Aggregate all windows from past 24 hours
            windows = []
            for i in range(24 * 60):
                w = (now - timedelta(minutes=i)).strftime("%Y%m%d%H%M")
                windows.append(f"hashtags:ranking:{w}")
            key = None  # We'll handle this specially
        elif period == "7d":
            # Aggregate all windows from past 7 days
            windows = []
            for i in range(7 * 24 * 60):
                w = (now - timedelta(minutes=i)).strftime("%Y%m%d%H%M")
                windows.append(f"hashtags:ranking:{w}")
            key = None  # We'll handle this specially
        else:
            raise HTTPException(status_code=400, detail="period must be 1h, 24h, or 7d")
        
        if key:
            # Single window
            raw = r.zrevrange(key, 0, n - 1, withscores=True)
        else:
            # Multiple windows - use ZUNIONSTORE
            dest_key = f"temp:hashtags:{period}:{int(time.time() * 1000)}"
            r.zunionstore(dest_key, {w: 1 for w in windows})
            r.expire(dest_key, 60)  # expire after 60 seconds
            raw = r.zrevrange(dest_key, 0, n - 1, withscores=True)
        
        out = [{"hashtag": member, "count": int(score)} for member, score in raw]
        return out
    except redis.RedisError as re:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(re)}")

@app.get("/api/trends/top-users")
def top_users(period: str = "all", n: int = 10):
    """
    Get most active users.
    Periods: all (global), 1h, 24h, 7d
    """
    try:
        if period == "all":
            key = "users:activity"
            raw = r.zrevrange(key, 0, n - 1, withscores=True)
        else:
            now = datetime.now(timezone.utc)
            
            if period == "1h":
                window_name = now.strftime("%Y%m%d%H%M")
                key = f"users:activity:{window_name}"
                raw = r.zrevrange(key, 0, n - 1, withscores=True)
            elif period == "24h":
                windows = []
                for i in range(24 * 60):
                    w = (now - timedelta(minutes=i)).strftime("%Y%m%d%H%M")
                    windows.append(f"users:activity:{w}")
                dest_key = f"temp:users:{period}:{int(time.time() * 1000)}"
                r.zunionstore(dest_key, {w: 1 for w in windows})
                r.expire(dest_key, 60)
                raw = r.zrevrange(dest_key, 0, n - 1, withscores=True)
            elif period == "7d":
                windows = []
                for i in range(7 * 24 * 60):
                    w = (now - timedelta(minutes=i)).strftime("%Y%m%d%H%M")
                    windows.append(f"users:activity:{w}")
                dest_key = f"temp:users:{period}:{int(time.time() * 1000)}"
                r.zunionstore(dest_key, {w: 1 for w in windows})
                r.expire(dest_key, 60)
                raw = r.zrevrange(dest_key, 0, n - 1, withscores=True)
            else:
                raise HTTPException(status_code=400, detail="period must be all, 1h, 24h, or 7d")
        
        out = [{"user": member, "activity_count": int(score)} for member, score in raw]
        return out
    except redis.RedisError as re:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(re)}")


@app.get("/api/comments/recent")
def recent_comments(n: int = 20):
    """
    Return recent comments stored by the consumer (most recent first).
    """
    try:
        raw = r.lrange("recent:comments", 0, n - 1)
        out = []
        for item in raw:
            try:
                out.append(json.loads(item))
            except Exception:
                # fallback to raw string
                out.append({"user": "", "comment": item, "ts": None})
        return out
    except redis.RedisError as re:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(re)}")