#!/usr/bin/env bash
# run_all.sh — uruchamia/wyłącza lokalny stack (Redis, backend, frontend, redis-commander)
# Usage:
#   ./run_all.sh start
#   ./run_all.sh stop
#   ./run_all.sh status
#   ./run_all.sh restart
#
# Zasady:
# - Nie zatrzymujemy systemowego Redisa, jeśli nie został uruchomiony przez skrypt.
# - Redis uruchamiany lokalnie dostaje PIDfile w ./run/pids/redis.pid (jeśli musimy go uruchomić).
# - redis-commander uruchamiany jest przez npx (nvm jest ładowane jeśli obecne).
# - Logi i PIDy w ./run/logs i ./run/pids.
set -eu

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS_DIR="$ROOT/run/pids"
LOGS_DIR="$ROOT/run/logs"

REDIS_PORT=6379
UVICORN_HOST="0.0.0.0"
UVICORN_PORT=8000
FRONTEND_PORT=8080
REDIS_CMD_PORT=8081
VENV_DIR="$ROOT/.venv"   # jeśli masz venv w innym miejscu, zmień tutaj

REDIS_STARTED_FLAG="$PIDS_DIR/redis.started"

mkdir -p "$PIDS_DIR" "$LOGS_DIR"

pidfile() { echo "$PIDS_DIR/$1.pid"; }
logfile() { echo "$LOGS_DIR/$1.log"; }

# Check if pidfile points to running process
is_running() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(cat "$pid_file")
    if ps -p "$pid" > /dev/null 2>&1; then
      return 0
    else
      return 1
    fi
  fi
  return 1
}

# Load nvm if present (so npx works)
load_nvm_if_present() {
  if [[ -d "$HOME/.nvm" ]]; then
    export NVM_DIR="$HOME/.nvm"
    # shellcheck source=/dev/null
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
  fi
}

# Kill process that listens on given port (ss -> pid)
kill_by_port() {
  local port="$1"
  # get pid listening on port (Linux ss output includes pid=)
  local pid
  pid=$(ss -ltnp "sport = :$port" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\),.*/\1/p' | head -n1 || true)
  if [[ -n "$pid" ]]; then
    echo "Found pid $pid listening on port $port — killing..."
    kill "$pid" 2>/dev/null || sudo kill -9 "$pid" 2>/dev/null || true
    sleep 0.2
    if ss -ltnp "sport = :$port" 2>/dev/null | grep -q LISTEN; then
      echo "Process on port $port still listening after kill — trying sudo kill -9"
      sudo kill -9 "$pid" 2>/dev/null || true
    else
      echo "Port $port is now free."
    fi
  else
    echo "No process found listening on port $port."
  fi
}

reset_redis() {
  echo "Resetting application data in Redis..."

  if ! command -v redis-cli >/dev/null 2>&1; then
    echo "redis-cli not found — cannot reset"
    return 1
  fi

  # sprawdź czy redis działa
  if ! redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
    echo "Redis not running — nothing to reset"
    return 0
  fi

  # usuń ranking hashtagów
  redis-cli -p "$REDIS_PORT" DEL hashtags:ranking >/dev/null 2>&1 || true

  # usuń stream zdarzeń
  redis-cli -p "$REDIS_PORT" DEL events:stream >/dev/null 2>&1 || true

  # usuń wszystkie statystyki
  for key in $(redis-cli -p "$REDIS_PORT" KEYS "stats:*"); do
    redis-cli -p "$REDIS_PORT" DEL "$key" >/dev/null 2>&1 || true
  done

  echo "Redis project data cleared."
}

# Start Redis: try systemctl, then /etc/init.d, then local redis-server with pidfile
start_redis() {
  # If already listening, skip
  if ss -ltn "sport = :$REDIS_PORT" 2>/dev/null | grep -q LISTEN; then
    echo "Redis already listening on port $REDIS_PORT — skipping start."
    return 0
  fi

  # 1) Try systemctl
  if command -v systemctl >/dev/null 2>&1; then
    echo "Attempting to start redis via systemctl..."
    if sudo --non-interactive true 2>/dev/null; then
      sudo systemctl start redis || true
    else
      systemctl start redis || true
    fi
    sleep 0.5
    if ss -ltn "sport = :$REDIS_PORT" 2>/dev/null | grep -q LISTEN; then
      echo "Redis started (systemctl)."
      return 0
    fi
  fi

  # 2) Try /etc/init.d/redis-server
  if [[ -x "/etc/init.d/redis-server" ]] || [[ -f "/etc/init.d/redis-server" ]]; then
    echo "Attempting to start redis via /etc/init.d/redis-server..."
    if sudo --non-interactive true 2>/dev/null; then
      sudo /etc/init.d/redis-server start || true
    else
      /etc/init.d/redis-server start || true
    fi
    sleep 0.5
    if ss -ltn "sport = :$REDIS_PORT" 2>/dev/null | grep -q LISTEN; then
      echo "Redis started (/etc/init.d)."
      return 0
    fi
  fi

  # 3) Start local redis-server with pidfile in run/pids
  if command -v redis-server >/dev/null 2>&1; then
    echo "Starting local redis-server --daemonize yes with pidfile..."
    local pidfile_path
    pidfile_path="$(pidfile redis)"  # run/pids/redis.pid
    # remove any stale pidfile_path before starting
    rm -f "$pidfile_path" >/dev/null 2>&1 || true
    # start with pidfile argument (most redis builds accept --pidfile)
    redis-server --port "$REDIS_PORT" --daemonize yes --pidfile "$pidfile_path" >/dev/null 2>&1 || true
    sleep 0.5
    if [[ -f "$pidfile_path" ]]; then
      echo "Redis started locally. PIDfile: $pidfile_path"
      touch "$REDIS_STARTED_FLAG"
      return 0
    fi

    # fallback: try to detect pid by pgrep and save to pidfile
    local realpid
    realpid=$(pgrep -f "redis-server.*:$REDIS_PORT" || pgrep -f "redis-server" || true)
    if [[ -n "$realpid" ]]; then
      realpid=$(echo "$realpid" | head -n1)
      echo "$realpid" > "$pidfile_path"
      touch "$REDIS_STARTED_FLAG"
      echo "Redis started locally (PID $realpid), PIDfile: $pidfile_path"
      return 0
    fi

    echo "Failed to start local redis-server (no pid found)."
    return 1
  fi

  echo "redis-server not found. Please install Redis or start it manually."
  return 1
}

# Start backend (uvicorn). Use venv uvicorn if available, else python3 -m uvicorn
start_backend() {
  local pidf
  pidf="$(pidfile backend)"
  if is_running "$pidf"; then
    echo "Backend already running (PID $(cat "$pidf"))."
    return 0
  fi

  pushd "$ROOT/backend" >/dev/null

  echo "Starting backend (uvicorn)..."
  if [[ -d "$VENV_DIR" && -x "$VENV_DIR/bin/uvicorn" ]]; then
    nohup "$VENV_DIR/bin/uvicorn" app:app --host "$UVICORN_HOST" --port "$UVICORN_PORT" --reload > "$(logfile backend)" 2>&1 &
  else
    nohup python3 -m uvicorn app:app --host "$UVICORN_HOST" --port "$UVICORN_PORT" --reload > "$(logfile backend)" 2>&1 &
  fi

  sleep 0.4
  # find real pid of uvicorn
  local realpid
  realpid=$(pgrep -f "uvicorn.*app:app" || pgrep -f "uvicorn" || true)
  if [[ -n "$realpid" ]]; then
    realpid=$(echo "$realpid" | head -n1)
    echo "$realpid" > "$pidf"
    echo "Backend started (PID $realpid), log: $(logfile backend)"
  else
    echo "Warning: couldn't detect uvicorn PID. Check $(logfile backend)."
  fi

  popd >/dev/null
}

# Start frontend (python3 -m http.server)
start_frontend() {
  local pidf
  pidf="$(pidfile frontend)"
  if is_running "$pidf"; then
    echo "Frontend already running (PID $(cat "$pidf"))."
    return 0
  fi

  pushd "$ROOT/frontend" >/dev/null
  echo "Starting frontend server (python3 -m http.server $FRONTEND_PORT)..."
  nohup python3 -m http.server "$FRONTEND_PORT" > "$(logfile frontend)" 2>&1 &
  sleep 0.2

  local realpid
  realpid=$(pgrep -f "python3.*http.server" || pgrep -f "http.server" || true)
  if [[ -n "$realpid" ]]; then
    realpid=$(echo "$realpid" | head -n1)
    echo "$realpid" > "$pidf"
    echo "Frontend started (PID $realpid), log: $(logfile frontend)"
  else
    echo "Warning: couldn't detect frontend PID. Check $(logfile frontend)."
  fi
  popd >/dev/null
}

# Start redis-commander via npx (nvm loaded if present)
start_redis_commander() {
  local pidf
  pidf="$(pidfile redis-commander)"
  if is_running "$pidf"; then
    echo "Redis-Commander already running (PID $(cat "$pidf"))."
    return 0
  fi

  load_nvm_if_present

  echo "Starting redis-commander on port $REDIS_CMD_PORT (127.0.0.1)..."
  nohup npx --yes redis-commander --redis-host 127.0.0.1 --redis-port "$REDIS_PORT" --port "$REDIS_CMD_PORT" --address 127.0.0.1 > "$(logfile redis-commander)" 2>&1 &

  sleep 0.6
  local realpid
  realpid=$(pgrep -f "redis-commander" || true)
  if [[ -n "$realpid" ]]; then
    realpid=$(echo "$realpid" | head -n1)
    echo "$realpid" > "$pidf"
    echo "Redis-Commander started (PID $realpid), log: $(logfile redis-commander)"
  else
    echo "Warning: couldn't detect redis-commander PID. Check $(logfile redis-commander)."
  fi
}

# Stop process by pidfile if exists
stop_process() {
  local pidf="$1"
  if [[ -f "$pidf" ]]; then
    local pid
    pid=$(cat "$pidf")
    if ps -p "$pid" > /dev/null 2>&1; then
      echo "Stopping PID $pid ..."
      kill "$pid" || true
      sleep 0.2
      if ps -p "$pid" > /dev/null 2>&1; then
        echo "PID $pid still running — sending kill -9"
        kill -9 "$pid" || true
      fi
    fi
    rm -f "$pidf"
  fi
}

# Stop all components (safe)
stop_all() {
  echo "Stopping components..."

  # stop by pidfiles first
  stop_process "$(pidfile redis-commander)"
  stop_process "$(pidfile frontend)"
  stop_process "$(pidfile backend)"

  # additional cleanup: kill by ports if processes still listening
  kill_by_port "$REDIS_CMD_PORT"   # redis-commander
  kill_by_port "$FRONTEND_PORT"    # frontend
  kill_by_port "$UVICORN_PORT"     # backend

  # Redis: if script started it, try clean shutdown then kill by port
  if [[ -f "$REDIS_STARTED_FLAG" ]]; then
    echo "This script started Redis — attempting clean shutdown via redis-cli..."
    if command -v redis-cli >/dev/null 2>&1; then
      redis-cli -p "$REDIS_PORT" shutdown || true
      sleep 0.3
    fi
    if ss -ltn "sport = :$REDIS_PORT" 2>/dev/null | grep -q LISTEN; then
      echo "Redis still listening — killing by port $REDIS_PORT"
      kill_by_port "$REDIS_PORT"
    fi
    rm -f "$REDIS_STARTED_FLAG" "$(pidfile redis)" 2>/dev/null || true
  else
    if ss -ltn "sport = :$REDIS_PORT" 2>/dev/null | grep -q LISTEN; then
      echo "Redis listening on $REDIS_PORT but was not started by this script — leaving it running."
    else
      echo "Redis not listening."
    fi
  fi

  echo "Stop_all: done."
}

# Status report
status_all() {
  echo "Status components:"
  # backend
  local backend_pidf; backend_pidf=$(pidfile backend)
  if is_running "$backend_pidf"; then
    echo "  backend: running (PID $(cat "$backend_pidf"))"
  else
    local bpid; bpid=$(pgrep -f "uvicorn.*app:app" || pgrep -f "uvicorn" || true)
    if [[ -n "$bpid" ]]; then
      echo "  backend: running (PID $(echo "$bpid" | head -n1))"
    else
      echo "  backend: stopped"
    fi
  fi

  # frontend
  local fe_pidf; fe_pidf=$(pidfile frontend)
  if is_running "$fe_pidf"; then
    echo "  frontend: running (PID $(cat "$fe_pidf"))"
  else
    local fpid; fpid=$(pgrep -f "python3.*http.server" || pgrep -f "http.server" || true)
    if [[ -n "$fpid" ]]; then
      echo "  frontend: running (PID $(echo "$fpid" | head -n1))"
    else
      echo "  frontend: stopped"
    fi
  fi

  # redis-commander
  local rc_pidf; rc_pidf=$(pidfile redis-commander)
  if is_running "$rc_pidf"; then
    echo "  redis-commander: running (PID $(cat "$rc_pidf"))"
  else
    local rpid; rpid=$(pgrep -f "redis-commander" || true)
    if [[ -n "$rpid" ]]; then
      echo "  redis-commander: running (PID $(echo "$rpid" | head -n1))"
    else
      echo "  redis-commander: stopped"
    fi
  fi

  # redis server
  if ss -ltn "sport = :$REDIS_PORT" 2>/dev/null | grep -q LISTEN; then
    echo "  redis: listening on port $REDIS_PORT"
  else
    echo "  redis: not listening on $REDIS_PORT"
  fi

  if [[ -f "$REDIS_STARTED_FLAG" ]]; then
    echo "  redis: started by this script (flag present)"
  fi
}

# Main
case "${1:-start}" in
  start)
    echo "Starting stack..."
    start_redis || echo "Warning: problem starting Redis."
    start_backend
    start_frontend
    start_redis_commander
    echo ""
    echo "Stack should be up. Frontend: http://localhost:$FRONTEND_PORT  Backend: http://localhost:$UVICORN_PORT  Redis-Commander: http://localhost:$REDIS_CMD_PORT"
    ;;

  reset)
    echo "Starting stack with Redis reset..."
    start_redis || echo "Warning: problem starting Redis."
    reset_redis
    start_backend
    start_frontend
    start_redis_commander
    echo ""
    echo "Stack reset & started. Clean database ready."
    ;;

  stop)
    stop_all
    ;;

  status)
    status_all
    ;;

  restart)
    stop_all
    sleep 0.5
    $0 start
    ;;

  *)
    echo "Usage: $0 {start|reset|stop|status|restart}"
    exit 2
    ;;
esac