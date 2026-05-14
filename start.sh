#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  start.sh  —  Menghidupkan Auto Subtitle Generator
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Prefer existing .venv if present, otherwise use venv for compatibility
VENV_DIR="$SCRIPT_DIR/venv"
if [ -d "$SCRIPT_DIR/.venv" ]; then
    VENV_DIR="$SCRIPT_DIR/.venv"
fi
PID_FILE="$SCRIPT_DIR/.app.pid"
LOG_FILE="$SCRIPT_DIR/app.log"
PORT="${PORT:-7860}"

echo ""
echo -e "${CYAN}${BOLD}════════════════════════════════════════${NC}"
echo -e "${CYAN}${BOLD}  Auto Subtitle Generator — Starting    ${NC}"
echo -e "${CYAN}${BOLD}════════════════════════════════════════${NC}"
echo ""

# ── Cek apakah sudah berjalan ─────────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo -e "${YELLOW}⚠ Aplikasi sudah berjalan (PID $OLD_PID).${NC}"
        echo -e "  Buka browser ke: ${BOLD}http://localhost:$PORT${NC}"
        echo -e "  Untuk restart, jalankan ${BOLD}bash stop.sh${NC} terlebih dahulu."
        echo ""
        exit 0
    else
        # PID file usang, hapus
        rm -f "$PID_FILE"
    fi
fi

    # ── Cek apakah port sudah digunakan (cross-platform) ─────────────────────────
    # Try to bind to the port using a small Python snippet. If binding fails,
    # the port is already in use and we assume a previous instance is running.
    python - <<PY >/dev/null 2>&1
    import socket,sys
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", $PORT))
    except OSError:
        sys.exit(1)
    finally:
        try:
            s.close()
        except Exception:
            pass
    PY
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}⚠ Port $PORT sudah digunakan oleh proses lain. Aplikasi mungkin sudah berjalan.${NC}"
        # Tampilkan proses yang mendengarkan port jika tersedia
        if command -v lsof &>/dev/null; then
            echo "  Listening process:" 
            lsof -nP -iTCP:$PORT -sTCP:LISTEN || true
        elif command -v ss &>/dev/null; then
            echo "  Listening process:" 
            ss -ltnp | grep :$PORT || true
        elif command -v netstat &>/dev/null; then
            echo "  Listening process:" 
            netstat -ano | grep :$PORT || true
        fi
        echo -e "  Buka browser ke: ${BOLD}http://localhost:$PORT${NC} untuk memeriksa UI."
        echo -e "  Untuk restart, hentikan instance yang ada terlebih dahulu (mis. ${BOLD}bash stop.sh${NC} atau gunakan alat sistem).
    "
        exit 0
    fi

# ── Cek virtual environment ───────────────────────────────────────────────────
ACTIVATE_SCRIPT="$VENV_DIR/bin/activate"
if [ ! -f "$ACTIVATE_SCRIPT" ]; then
    ACTIVATE_SCRIPT="$VENV_DIR/Scripts/activate"
fi
if [ ! -f "$ACTIVATE_SCRIPT" ]; then
    echo -e "${RED}ERROR: Virtual environment tidak ditemukan di $VENV_DIR!${NC}"
    echo "Jalankan install terlebih dahulu: ${BOLD}bash install.sh${NC}"
    exit 1
fi

# Aktifkan venv dan jalankan
# shellcheck disable=SC1091
source "$ACTIVATE_SCRIPT"

# Prefer the python executable inside the venv (cross-platform)
if [ -x "$VENV_DIR/bin/python" ]; then
    VENV_PY="$VENV_DIR/bin/python"
elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then
    VENV_PY="$VENV_DIR/Scripts/python.exe"
else
    VENV_PY="python3"
fi

echo -e "${YELLOW}▶ Memulai server di port $PORT...${NC}"
# Export PORT for the process and run with the venv python
PORT=$PORT nohup "$VENV_PY" "$SCRIPT_DIR/app.py" > "$LOG_FILE" 2>&1 &
APP_PID=$!
echo $APP_PID > "$PID_FILE"

# ── Tunggu server siap ────────────────────────────────────────────────────────
echo -n "  Menunggu server siap"
READY=false
for i in $(seq 1 30); do
    sleep 1
    echo -n "."
    if grep -q "Running on local URL" "$LOG_FILE" 2>/dev/null || \
       grep -q "http://127.0.0.1" "$LOG_FILE" 2>/dev/null; then
        READY=true
        break
    fi
    # Cek apakah proses masih hidup
    if ! kill -0 "$APP_PID" 2>/dev/null; then
        echo ""
        echo -e "${RED}ERROR: Server gagal berjalan. Lihat log:${NC}"
        echo "  cat $LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
done
echo ""

if $READY; then
    echo ""
    echo -e "${GREEN}${BOLD}✅  Server berhasil berjalan!${NC}"
    echo ""
    echo -e "  🌐 Buka browser ke: ${BOLD}http://localhost:$PORT${NC}"
    echo -e "  📄 Log file: $LOG_FILE"
    echo -e "  🛑 Untuk stop: ${BOLD}bash stop.sh${NC}"
    echo ""
    # Coba buka browser otomatis
    if command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:$PORT" 2>/dev/null &
    fi
else
    echo -e "${YELLOW}⏳ Server masih starting, silahkan buka manual:${NC}"
    echo -e "  ${BOLD}http://localhost:$PORT${NC}"
    echo -e "  (tunggu beberapa detik lagi)"
    echo ""
fi
