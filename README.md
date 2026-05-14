# 🎧 Auto Subtitle Generator — Local

Aplikasi subtitle otomatis yang berjalan di laptop kamu sendiri.
Cocok untuk Intel CPU tanpa GPU (termasuk Celeron N4000).

---

## 📋 Persyaratan Sistem

| Komponen | Minimal |
|----------|---------|
| OS       | Ubuntu / Debian / WSL2 di Windows |
| Python   | 3.9 atau lebih baru |
| RAM      | 2 GB bebas |
| Storage  | ~2 GB (untuk model Whisper + library) |
| Internet | Diperlukan saat install & terjemahan |
| ffmpeg   | Akan diinstall otomatis oleh install.sh |

---

## 🚀 Cara Install (satu kali saja)

Buka terminal, masuk ke folder ini, lalu jalankan:

```bash
cd subtitle-generator
bash install.sh
```

Proses install akan memakan waktu **5–15 menit** tergantung kecepatan internet.
Ini hanya perlu dilakukan **sekali saja**.

---

## ▶️ Menghidupkan Aplikasi

```bash
bash start.sh
```

Browser akan terbuka otomatis ke `http://localhost:7860`.
Jika tidak terbuka, buka manual di browser kamu.

---

## ⏹ Menghentikan Aplikasi

```bash
bash stop.sh
```

---

## 🔧 Cara Pakai

1. Klik **Upload File Audio** → pilih file MP3/WAV/M4A/OGG/FLAC
2. Pilih **Bahasa Audio** (contoh: Japanese untuk audio Jepang)
3. Pilih **Terjemahkan ke** bahasa tujuan (contoh: Indonesian)
4. Pilih **Model Whisper**:
   - `tiny` → paling cepat, cocok untuk Celeron N4000 ✅
   - `base` → lebih akurat, 2–3x lebih lambat
5. Klik **Generate Subtitles** dan tunggu proses selesai
6. Klik baris subtitle untuk loncat ke bagian audio tersebut
7. Download file SRT dengan tombol **Download SRT**

---

## ⏱️ Estimasi Waktu Proses (Celeron N4000, model tiny)

| Durasi Audio | Estimasi Waktu |
|-------------|----------------|
| 1 menit     | ~10–20 detik   |
| 10 menit    | ~1–3 menit     |
| 1 jam       | ~10–20 menit   |
| 1:42 jam    | ~20–35 menit   |

---

## 📁 Struktur File

```
subtitle-generator/
├── app.py          → Aplikasi utama
├── install.sh      → Script instalasi (jalankan sekali)
├── start.sh        → Menghidupkan server
├── stop.sh         → Mematikan server
├── requirements.txt→ Daftar library Python
├── README.md       → Panduan ini
├── venv/           → Virtual environment (dibuat saat install)
└── app.log         → Log server (dibuat saat start)
```

---

## 🐛 Troubleshooting

**Server tidak mau start:**
```bash
cat app.log   # lihat pesan error
```

**Port 7860 sudah dipakai:**
```bash
PORT=7861 bash start.sh
```

**Reinstall dari awal:**
```bash
rm -rf venv
bash install.sh
```

**ffmpeg not found:**
```bash
sudo apt install ffmpeg
```

---

## 📝 Catatan

- Model Whisper diunduh otomatis saat **pertama kali** dipakai (~75 MB untuk tiny, ~145 MB untuk base)
- Model disimpan di `~/.cache/whisper/` dan tidak perlu diunduh ulang
- Terjemahan memerlukan koneksi internet (menggunakan Google Translate gratis)
- File audio tidak diunggah ke server manapun — semua diproses secara lokal
