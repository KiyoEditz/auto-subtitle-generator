#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  fix-translation.sh  —  Perbaiki terjemahan SRT yang gagal
#  Menggunakan Claude AI API, bukan Google Translate
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

echo ""
echo -e "${CYAN}${BOLD}════════════════════════════════════════${NC}"
echo -e "${CYAN}${BOLD}  SRT Translation Fixer (Google via deep-translator) ${NC}"
echo -e "${CYAN}${BOLD}════════════════════════════════════════${NC}"
echo ""

# ── Cek argumen ───────────────────────────────────────────────────────────────
if [ "$#" -lt 1 ]; then
    echo -e "Cara pakai:"
    echo -e "  ${BOLD}bash fix-translation.sh input.srt${NC}"
    echo -e "  ${BOLD}bash fix-translation.sh input.srt output.srt${NC}"
    echo -e "  ${BOLD}bash fix-translation.sh input.srt output.srt --source ja --target id${NC}"
    echo ""
    echo -e "Contoh:"
    echo -e "  bash fix-translation.sh subtitle.srt subtitle_fixed.srt"
    echo ""
    echo -e "Opsi tambahan:"
    echo -e "  --source ja    Bahasa sumber (default: ja untuk Jepang)"
    echo -e "  --target id    Bahasa tujuan (default: id untuk Indonesia)"
    echo -e "  --all          Terjemahkan ulang SEMUA baris (bukan hanya yang error)"
    echo -e "  --batch 30     Jumlah kalimat per request (default: 30)"
    echo ""
    exit 1
fi

INPUT_FILE="$1"
shift

# Tentukan output file
if [ -n "$1" ] && [[ "$1" != --* ]]; then
    OUTPUT_FILE="$1"
    shift
else
    # Default: tambahkan _fixed sebelum ekstensi
    BASENAME="${INPUT_FILE%.srt}"
    OUTPUT_FILE="${BASENAME}_fixed.srt"
fi

# ── Cek file input ────────────────────────────────────────────────────────────
if [ ! -f "$INPUT_FILE" ]; then
    echo -e "${RED}ERROR: File '$INPUT_FILE' tidak ditemukan!${NC}"
    exit 1
fi

echo -e "  Input : ${BOLD}$INPUT_FILE${NC}"
echo -e "  Output: ${BOLD}$OUTPUT_FILE${NC}"
echo ""

# Using Google Translate via deep-translator; no API key required.
echo -e "${GREEN}✓ Using deep-translator (Google). No API key required.${NC}"
echo ""

# ── Aktifkan venv jika ada ────────────────────────────────────────────────────
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
    echo -e "${GREEN}✓ Virtual environment aktif${NC}"
else
    echo -e "${YELLOW}⚠ Virtual environment tidak ditemukan, menggunakan Python sistem${NC}"
fi

# ── Jalankan script ───────────────────────────────────────────────────────────
echo -e "${YELLOW}▶ Memulai proses terjemahan…${NC}"
echo ""

python3 "$SCRIPT_DIR/retranslate.py" "$INPUT_FILE" "$OUTPUT_FILE" "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✅ Selesai! File tersimpan di: $OUTPUT_FILE${NC}"
else
    echo -e "${RED}ERROR: Script gagal dengan kode $EXIT_CODE${NC}"
fi
echo ""
