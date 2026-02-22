from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Literal
import redis
import time
import json
import os

# konfiguracja połączenia (możesz nadpisać przez env REDIS_HOST/REDIS_PORT)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# połączenie z lokalnym redisem
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

app = FastAPI(title="Social Trends Analyzer")

# CORS (frontend działa na innym porcie)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ścisły model eventu: ograniczamy typy do tych, które obsługujemy
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
        # Nie ujawniamy stacktrace w odpowiedzi, ale zwracamy komunikat
        raise HTTPException(status_code=503, detail=f"redis error: {str(e)}")

@app.post("/api/events")
def post_event(ev: Event):
    """
    Atomowe przetwarzanie eventu:
    - zapisujemy pełny payload (JSON) do streama events:stream (pole 'payload')
    - inkrementujemy odpowiednie liczniki stats:likes/comments/shares
    - aktualizujemy ZSET hashtags:ranking
    Wszystko wykonane w pipeline(transaction=True) -> MULTI/EXEC
    """
    ts = int(time.time() * 1000)

    # przygotuj payload JSON do zapisu w streamie
    payload_obj = {
        "type": ev.type,
        "hashtags": ev.hashtags or [],
        "user_id": ev.user_id or "",
        "metadata": ev.metadata or {},
        "ts": ts
    }
    payload_str = json.dumps(payload_obj, ensure_ascii=False)

    try:
        pipe = r.pipeline(transaction=True)

        # zapisujemy pełny payload i oddzielne pola (hashtags jako CSV dla szybkiego podglądu)
        hashtags_csv = ",".join([h.strip() for h in (ev.hashtags or []) if h])
        pipe.xadd("events:stream", {"payload": payload_str, "time": ts, "hashtags": hashtags_csv})

        # inkrementacja liczników zgodnie z typem eventu
        if ev.type == "like":
            pipe.incr("stats:likes")
        elif ev.type == "comment":
            pipe.incr("stats:comments")
        elif ev.type == "share":
            pipe.incr("stats:shares")
        elif ev.type == "hashtag":
            # traktujemy event typu "hashtag" jako aktualizację rankingu (bez inkrementacji osobnych liczników)
            pass

        # zwiększamy ranking hashtagów (ZINCRBY) — tylko gdy są hashtagi
        for tag in ev.hashtags or []:
            if not tag:
                continue
            clean = tag.lower().strip().lstrip("#")
            if clean:
                # używamy score = 1; w przyszłości można użyć innych wag w metadata
                pipe.zincrby("hashtags:ranking", 1, clean)

        # wykonaj atomowo
        pipe.execute()
    except redis.RedisError as re:
        # błąd Redis — zwracamy HTTP 500
        raise HTTPException(status_code=500, detail=f"Redis error: {str(re)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

    return {"result": "ok", "ts": ts}

@app.get("/api/trends/hashtags")
def top_hashtags(n: int = 10):
    try:
        # ZREVRANGE zwraca [member, score, member, score, ...] jeśli withscores=True w redis-py <-> returns list of tuples
        raw = r.zrevrange("hashtags:ranking", 0, n - 1, withscores=True)
        # raw is list of (member, score)
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