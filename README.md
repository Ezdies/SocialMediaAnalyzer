# Analiza trendów w social media – Redis

## Opis projektu

Projekt przedstawia prosty system analizy trendów w mediach społecznościowych działający w czasie rzeczywistym.
Aplikacja zlicza wystąpienia hashtagów oraz interakcje użytkowników (polubienia, komentarze, udostępnienia), a następnie prezentuje aktualne trendy w panelu webowym.

Dane są symulowane i wysyłane do systemu przez API.

---

## Architektura systemu

# SocialMediaAnalyzer — analiza trendów w czasie rzeczywistym

Aktualny projekt to edukacyjna aplikacja pokazująca przepływ zdarzeń (events) od frontendu/symulatora, przez backend (FastAPI) do Redis, gdzie działa prosty agregator (consumer) tworzący materializowane widoki (rankingi, liczniki, lista ostatnich komentarzy). Frontend je odczytuje i prezentuje w panelu.

Ten README opisuje szybkie uruchomienie, kluczowe endpointy, strukturę Redis i sposób czyszczenia danych.

---

## Architektura — krótko

- `frontend/` — statyczny panel (HTML/JS) + symulator (`sim.js`) wysyłający zdarzenia do API.
- `backend/` — FastAPI: przyjmuje POST `/api/events` (XADD do `events:stream`) oraz udostępnia czytelnicze endpointy (trendy, statystyki, ostatnie komentarze).
- `consumer.py` — proces działający w tle: odczytuje `events:stream`, deduplikuje, aktualizuje ZSETy/STRINGS/LIST w Redis (np. `hashtags:ranking`, `users:activity`, `stats:*`, `recent:comments`).
- `Redis` — pamięć, używane typy: Stream, Sorted Set, String, List.

Przepływ: frontend → POST /api/events → Redis Stream `events:stream` → consumer (XREADGROUP/XREAD) → materializowane widoki → API GET → frontend.

---

## Kluczowe Redis‑keys używane przez projekt

- `events:stream` — Redis Stream z oryginalnymi zdarzeniami
- `processed:*` — deduplikacja pojedynczych eventów (consumer)
- `stats:like`, `stats:comment`, `stats:share` — proste liczniki
- `hashtags:ranking` oraz `hashtags:ranking:<window>` — ZSETy dla globalnych i okien czasowych
- `users:activity` oraz `users:activity:<window>` — ZSETy aktywności użytkowników
- `recent:comments` — LISTa ostatnich komentarzy (LPUSH + LTRIM)

Uwaga: nazwy okien i dodatkowe klucze mogą być tworzone dynamicznie przez consumer (np. `hashtags:ranking:1h`).

---

## Endpointy API (wybrane)

- POST `/api/events` — przyjmuje JSON eventu: `{ "type": "like|comment|share", "hashtags": ["#tag"], "user_id": "user123", "comment": "opcjonalny tekst" }`.
- GET `/api/trends/hashtags` — najpopularniejsze hashtagi (globalnie).
- GET `/api/trends/hashtags/period?period=1h|24h|7d` — trendy dla przedziału czasowego.
- GET `/api/trends/top-users?period=...` — top userów wg aktywności.
- GET `/api/stats/interactions` — sumaryczne liczniki interakcji.
- GET `/api/comments/recent?n=20` — ostatnie `n` komentarzy z `recent:comments`.

Przykład POST:

```bash
curl -s -X POST http://localhost:8000/api/events \
	-H "Content-Type: application/json" \
	-d '{"type":"comment","hashtags":["#redis"],"user_id":"sim-1","comment":"Świetny wpis!"}'
```

---

## Uruchamianie lokalnie (skrót)

1. Przygotuj venv i zależności:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

2. Uruchom skrypt pomocniczy `run_all.sh` (start/stop/reset/status/restart):

```bash
./run_all.sh start      # startuje redis (jeśli dostępny), backend, frontend, consumer, redis-commander
./run_all.sh stop
./run_all.sh status
./run_all.sh reset      # startuje stack i czyści klucze projektu w Redis
FULL_REDIS_RESET=1 ./run_all.sh reset  # Uwaga: pełny FLUSHDB
```

Ważne: `restart` wykonuje stop/start, ale NIE czyści danych — do wyczyszczenia użyj `reset`.

---

## Jak zresetować dane (bez pełnego FLUSH)

`./run_all.sh reset` usuwa klucze używane przez aplikację (statystyki, ranking, recent comments, events stream i klucze pomocnicze). Jeśli wolisz całkowite wyczyszczenie bazy, ustaw `FULL_REDIS_RESET=1` przed wywołaniem `reset`.

Ręczne sprawdzenie stanu Redis:

```bash
redis-cli -p 6379 --scan | wc -l      # liczba kluczy
redis-cli -p 6379 DBSIZE               # liczba kluczy w DB
redis-cli -p 6379 --scan | sed -n '1,50p'   # pierwsze 50 kluczy
```

Jeżeli chcesz wymusić ponowne przetworzenie historycznych eventów po zmianie consumer-a, usuń klucze `processed:*` i (opcjonalnie) stwórz/zresetuj consumer group dla `events:stream`.

---

## Symulator (frontend/js/sim.js)

Symulator generuje zdarzenia i wysyła je do `/api/events`. Dla typu `comment` symulator obecnie dołącza pole `comment` z przykładowym tekstem, dzięki czemu komentarze przepływają przez consumer i pojawiają się w `/api/comments/recent`.

## Interaktywny wykres

W panelu webowym znajduje się nowa sekcja **Interactive Chart**. Umożliwia ona wybór metryki (najpopularniejsze hashtagi, aktywność użytkowników lub łączna liczba interakcji) oraz okresu (`1h`, `24h`, `7d` lub `all`).
Wykres typu słupkowego rysowany jest przy użyciu Chart.js i odświeża się automatycznie po każdej zmianie filtrów. Służy do szybkiej wizualizacji rankingów danych.


---

## Debug / typowe komendy

Uruchomienie backendu ręcznie:

```bash
cd backend
.venv/bin/uvicorn app:app --reload
```

Sprawdzenie streamu i rankingów:

```bash
redis-cli -p 6379 XRANGE events:stream - +
redis-cli -p 6379 ZREVRANGE hashtags:ranking 0 10 WITHSCORES
redis-cli -p 6379 LRANGE recent:comments 0 20
```

---
