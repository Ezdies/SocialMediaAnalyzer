from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis
import time
from typing import List, Optional

# połączenie z lokalnym redisem
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

app = FastAPI(title="Social Trends Analyzer")

# pozwala frontendowi łączyć się z backendem (inne porty)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Event(BaseModel):
    type: str
    hashtags: Optional[List[str]] = []
    user_id: Optional[str] = None
    metadata: Optional[dict] = {}

@app.get("/api/health")
def health():
    r.ping()
    return {"status": "ok"}

@app.post("/api/events")
def post_event(ev: Event):
    ts = int(time.time() * 1000)

    # zapis do streamu
    r.xadd("events:stream", {
        "type": ev.type,
        "time": ts,
        "user": ev.user_id or ""
    })

    # interakcje
    if ev.type == "like":
        r.incr("stats:likes")
    elif ev.type == "comment":
        r.incr("stats:comments")
    elif ev.type == "share":
        r.incr("stats:shares")

    # hashtagi ranking
    for tag in ev.hashtags or []:
        clean = tag.lower().replace("#", "")
        if clean:
            r.zincrby("hashtags:ranking", 1, clean)

    return {"result": "ok"}

@app.get("/api/trends/hashtags")
def top_hashtags(n: int = 10):
    data = r.zrevrange("hashtags:ranking", 0, n-1, withscores=True)
    return [{"hashtag": h, "count": int(score)} for h, score in data]

@app.get("/api/stats/interactions")
def stats():
    return {
        "likes": int(r.get("stats:likes") or 0),
        "comments": int(r.get("stats:comments") or 0),
        "shares": int(r.get("stats:shares") or 0),
    }