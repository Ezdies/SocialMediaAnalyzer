# Analiza trendów w social media – Redis

## Opis projektu

Projekt przedstawia prosty system analizy trendów w mediach społecznościowych działający w czasie rzeczywistym.
Aplikacja zlicza wystąpienia hashtagów oraz interakcje użytkowników (polubienia, komentarze, udostępnienia), a następnie prezentuje aktualne trendy w panelu webowym.

Dane są symulowane i wysyłane do systemu przez API.

---

## Architektura systemu

System składa się z trzech warstw:

* **Backend (FastAPI)** – logika aplikacji i REST API
* **RedisDB** – baza danych w pamięci operacyjnej
* **Frontend (HTML + JS)** – panel prezentujący dane

Frontend komunikuje się z backendem poprzez HTTP, natomiast backend wykonuje atomowe operacje na Redis.

---

## Wykorzystane struktury Redis

| Struktura  | Zastosowanie        |
| ---------- | ------------------- |
| String     | liczniki interakcji |
| Sorted Set | ranking hashtagów   |
| Stream     | rejestr zdarzeń     |

### Klucze w bazie

```redis
stats:likes
stats:comments
stats:shares
hashtags:ranking
events:stream
```

---

## Endpointy API

### POST /api/events

Rejestruje zdarzenie użytkownika i aktualizuje statystyki.

Przykład:

```bash
curl -X POST http://localhost:8000/api/events \
-H "Content-Type: application/json" \
-d "{\"type\":\"like\",\"hashtags\":[\"#AI\",\"#Python\"]}"
```

---

### GET /api/trends/hashtags

Zwraca listę najpopularniejszych hashtagów (TOP N).

---

### GET /api/stats/interactions

Zwraca liczbę interakcji użytkowników.

---

### GET /api/health

Sprawdza poprawność działania systemu.

---

## Uruchomienie projektu

### 1. Wymagania

* Python 3.10+
* Redis
* pip

---

### 2. Instalacja Redis

Linux:

```bash
sudo apt install redis-server
sudo service redis-server start
```

Sprawdzenie:

```bash
redis-cli ping
```

---

### 3. Uruchomienie aplikacji

#### Utworzenie środowiska

```bash
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows:

```bash
.venv\Scripts\activate
```

#### Instalacja zależności

```bash
pip install -r backend/requirements.txt
```

#### Uruchomienie backendu

```bash
cd backend
uvicorn app:app --reload
```

Backend:

```
http://localhost:8000/api/health
```

#### Uruchomienie frontendu

(drugi terminal)

```bash
cd frontend
python -m http.server 8080
```

Panel:

```
http://localhost:8080
```

---

## Sprawdzenie działania

Wyślij zdarzenie:

```bash
curl -X POST http://localhost:8000/api/events \
-H "Content-Type: application/json" \
-d "{\"type\":\"like\",\"hashtags\":[\"#redis\",\"#ai\"]}"
```

Sprawdź dane w Redis:

```bash
redis-cli
ZREVRANGE hashtags:ranking 0 -1 WITHSCORES
GET stats:likes
XRANGE events:stream - +
```

---

## Charakter czasu rzeczywistego

System wykorzystuje atomowe operacje Redis:

* INCR – liczniki
* ZINCRBY – ranking
* XADD – strumień zdarzeń

Pozwala to na obsługę dużej liczby zdarzeń i natychmiastową aktualizację wyników.

---

## Możliwe rozszerzenia

* analiza trendów w oknie czasowym
* wykresy historyczne
* integracja z rzeczywistymi API social media
* WebSocket zamiast odpytywania

---

## Autor

Projekt edukacyjny – analiza przetwarzania danych w czasie rzeczywistym z wykorzystaniem Redis.
