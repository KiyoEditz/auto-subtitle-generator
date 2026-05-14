#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  install.sh  —  Auto Subtitle Generator (Local)
#  Jalankan sekali saja untuk menyiapkan semua kebutuhan.
# ─────────────────────────────────────────────────────────────────────────────

 # keluar jika ada error

# Warna output
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Prefer existing .venv if present, otherwise use venv for compatibility
VENV_DIR="$SCRIPT_DIR/venv"
if [ -d "$SCRIPT_DIR/.venv" ]; then
    VENV_DIR="$SCRIPT_DIR/.venv"
fi

echo ""
echo -e "${CYAN}${BOLD}════════════════════════════════════════${NC}"
echo -e "${CYAN}${BOLD}  Auto Subtitle Generator — Installer   ${NC}"
echo -e "${CYAN}${BOLD}════════════════════════════════════════${NC}"
echo ""

# ── 1. Cek Python 3 (multi-platform) ────────────────────────────────────────
echo -e "${YELLOW}[1/5] Mengecek Python 3...${NC}"
# Allow overriding the python command via environment variable PYTHON_CMD
if [ -n "$PYTHON_CMD" ]; then
    PY_CMD=$PYTHON_CMD
else
    PY_CMD=""
    # Prefer specific Windows launcher py -3.10 when available
    if command -v py &>/dev/null && py -3.10 --version >/dev/null 2>&1; then
        PY_CMD="py -3.10"
    elif command -v python3 &>/dev/null; then
        PY_CMD=python3
    elif command -v python &>/dev/null && python --version 2>&1 | grep -q "Python 3"; then
        PY_CMD=python
    elif command -v py &>/dev/null && py -3 --version >/dev/null 2>&1; then
        PY_CMD="py -3"
    fi
fi

if [ -z "$PY_CMD" ]; then
    echo -e "${RED}ERROR: Python 3 tidak ditemukan!${NC}"
    echo "Install Python 3 (Linux: sudo apt install python3 python3-venv)."
    exit 1
fi

# When using a multi-word launcher like 'py -3.10', avoid quoting so shell splits it
PY_VER=$($PY_CMD --version 2>&1)
echo -e "${GREEN}OK → $PY_VER${NC}"

# ── 2. Cek ffmpeg ─────────────────────────────────────────────────────────────
echo -e "${YELLOW}[2/5] Mengecek ffmpeg...${NC}"
if ! command -v ffmpeg &>/dev/null; then
    echo "  ffmpeg tidak ditemukan, mencoba install otomatis..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -q ffmpeg
        echo -e "${GREEN}OK → ffmpeg berhasil diinstall${NC}"
    else
        echo -e "${RED}ERROR: Tidak bisa install ffmpeg otomatis.${NC}"
        echo "Install manual: sudo apt install ffmpeg"
        exit 1
    fi
else
    FFMPEG_VER=$(ffmpeg -version 2>&1 | head -n1)
    echo -e "${GREEN}OK → $FFMPEG_VER${NC}"
fi

# ── 3. Buat virtual environment ───────────────────────────────────────────────
echo -e "${YELLOW}[3/5] Membuat virtual environment Python...${NC}"
if [ -d "$VENV_DIR" ]; then
    echo "  Virtual environment sudah ada di $VENV_DIR, melewati pembuatan."
else
    echo "  Membuat virtual environment di $VENV_DIR..."
    $PY_CMD -m venv "$VENV_DIR"
    echo -e "${GREEN}OK → venv dibuat di $VENV_DIR${NC}"
fi

# Aktifkan venv — try POSIX path first, then Windows-style Scripts\n
ACTIVATE_SCRIPT="$VENV_DIR/bin/activate"
if [ ! -f "$ACTIVATE_SCRIPT" ]; then
    ACTIVATE_SCRIPT="$VENV_DIR/Scripts/activate"
fi
if [ -f "$ACTIVATE_SCRIPT" ]; then
    # shellcheck disable=SC1091
    source "$ACTIVATE_SCRIPT"
else
    echo -e "${RED}ERROR: Tidak menemukan skrip aktivasi virtualenv di $VENV_DIR${NC}"
    exit 1
fi

# ── 4. Upgrade pip ────────────────────────────────────────────────────────────
echo -e "${YELLOW}[4/5] Upgrade pip...${NC}"
pip install --upgrade pip --quiet
echo -e "${GREEN}OK → pip ter-update${NC}"

# ── 5. Install dependencies ───────────────────────────────────────────────────
echo -e "${YELLOW}[5/5] Menginstall dependencies (ini mungkin memakan waktu 5–15 menit)...${NC}"
echo "  Menginstall build tools dan Whisper (via Git) terlebih dahulu..."
pip install "setuptools<81" wheel setuptools_scm packaging --quiet

echo "  Menginstall Whisper dari repository (bypass problematic sdist)..."
pip install --no-build-isolation git+https://github.com/openai/whisper.git --quiet || true

echo "  Menginstall library lainnya dari requirements.txt..."
pip install -r requirements.txt --quiet || true

echo "  (Opsional) Menginstall PyTorch CPU wheel yang cocok (jika belum terpasang)..."
pip install "torch==2.12.0+cpu" --extra-index-url https://download.pytorch.org/whl/cpu --quiet || true

echo "  Memeriksa versi paket penting..."
python - <<PY
import os
pkgs = ["gradio","gradio_client","huggingface_hub","Jinja2","numpy","torch"]
for p in pkgs:
    try:
        m = __import__(p)
        v = getattr(m, '__version__', None)
    except Exception:
        v = None
    print(f"{p}: {v}")
PY

echo -e "${GREEN}OK → Semua dependencies berhasil diinstall${NC}"

# ── Selesai ───────────────────────────────────────────────────────────────────
deactivate

echo ""
echo -e "${CYAN}${BOLD}════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}✅  Instalasi selesai!${NC}"
echo -e "${CYAN}${BOLD}════════════════════════════════════════${NC}"
echo ""
echo -e "Untuk menjalankan aplikasi:"
echo -e "  ${BOLD}bash start.sh${NC}"
echo ""
echo -e "Untuk menghentikan aplikasi:"
echo -e "  ${BOLD}bash stop.sh${NC}"
echo ""
