#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  stop.sh  —  Menghentikan Auto Subtitle Generator
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.app.pid"
PORT="${PORT:-7860}"

echo ""
echo -e "${CYAN}${BOLD}════════════════════════════════════════${NC}"
echo -e "${CYAN}${BOLD}  Auto Subtitle Generator — Stopping    ${NC}"
echo -e "${CYAN}${BOLD}════════════════════════════════════════${NC}"
echo ""

if [ ! -f "$PID_FILE" ]; then
    # Jika PID file tidak ada, periksa apakah ada proses yang mendengarkan PORT
    if command -v lsof &>/dev/null; then
        LSOF_OUT=$(lsof -nP -iTCP:$PORT -sTCP:LISTEN || true)
        if [ -n "$LSOF_OUT" ]; then
            echo -e "${YELLOW}⚠ Tidak ada PID file, namun port $PORT sedang digunakan oleh proses berikut:${NC}"
            echo "$LSOF_OUT"
            echo "  Untuk menghentikan proses tersebut, catat PID lalu jalankan: kill <PID>"
            echo ""
            exit 0
        fi
    fi

    echo -e "${YELLOW}⚠ Aplikasi tidak sedang berjalan (PID file tidak ada).${NC}"
    echo ""
    exit 0
fi

PID=$(cat "$PID_FILE")

if kill -0 "$PID" 2>/dev/null; then
    echo -e "${YELLOW}⏹ Menghentikan proses PID $PID...${NC}"
    kill "$PID"
    sleep 1

    # Pastikan sudah mati
    if kill -0 "$PID" 2>/dev/null; then
        echo "  Proses belum berhenti, memaksa (kill -9)..."
        kill -9 "$PID" 2>/dev/null
    fi

    rm -f "$PID_FILE"
    echo -e "${GREEN}${BOLD}✅  Server berhasil dihentikan.${NC}"
else
    echo -e "${YELLOW}⚠ Proses PID $PID tidak ditemukan (mungkin sudah berhenti).${NC}"
    rm -f "$PID_FILE"
fi

echo ""
echo -e "Untuk menghidupkan kembali: ${BOLD}bash start.sh${NC}"
echo ""
