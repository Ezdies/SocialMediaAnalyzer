# backend/app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Literal
import redis
import time
import json
import os

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
    Producer: jedynie zapisuje pełny event do streama (events:stream)
    Consumer przejmie agregacje (global i window).
    """
    ts = int(time.time() * 1000)
    payload_obj = {
        "type": ev.type,
        "hashtags": ev.hashtags or [],
        "user_id": ev.user_id or "",
        "metadata": ev.metadata or {},
        "ts": ts
    }
    payload_str = json.dumps(payload_obj, ensure_ascii=False)

    try:
        # zapis do streama tylko
        hashtags_csv = ",".join([h.strip() for h in (ev.hashtags or []) if h])
        r.xadd("events:stream", {"payload": payload_str, "time": ts, "hashtags": hashtags_csv})
    except redis.RedisError as re:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(re)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    return {"result": "ok", "ts": ts}

# Te endpointy służą do odczytu wyników, które generuje consumer
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
        likes = int(r.get("stats:likes") or 0)
        comments = int(r.get("stats:comments") or 0)
        shares = int(r.get("stats:shares") or 0)
        return {"likes": likes, "comments": comments, "shares": shares}
    except redis.RedisError as re:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(re)}")