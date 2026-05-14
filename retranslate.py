"""
retranslate.py — Perbaiki terjemahan SRT menggunakan deep-translator (Google)

Fitur:
- Menggunakan `deep-translator` (Google) — gratis dan tidak butuh API key.
- Checkpointing per-bar isian (`<output>.progress.json`) sehingga proses dapat
  dilanjutkan bila koneksi putus.
- Menyimpan output SRT secara berkala.

Cara pakai:
  python retranslate.py input.srt output.srt
  python retranslate.py input.srt output.srt --source ja --target id --batch 30
"""

import argparse
import json
import os
import re
import sys
import time
import requests

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

try:
    from argostranslate import translate as argostranslate_translate
    from argostranslate import package as argostranslate_package
    HAS_ARGOS = True
except Exception:
    argostranslate_translate = None
    argostranslate_package = None
    HAS_ARGOS = False

# Enforce a default requests timeout (used by deep-translator) to avoid long
# hanging network calls. This patches requests.Session.request to supply a
# sensible timeout when one isn't provided by callers (deep-translator doesn't
# expose a timeout parameter).
try:
    _orig_session_request = requests.sessions.Session.request
    def _session_request_with_timeout(self, method, url, **kwargs):
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 15
        return _orig_session_request(self, method, url, **kwargs)
    requests.sessions.Session.request = _session_request_with_timeout
except Exception:
    # Best-effort; if this fails we still continue without the global timeout
    pass

# Configuration
BATCH_SIZE = 30
RETRY = 3
RETRY_WAIT = 2
SLEEP_BETWEEN = 0.12

ERROR_RE = re.compile(r"^\[Translation error:.*\]")


def parse_srt(text):
    blocks = re.split(r"\n\n+", text.strip())
    entries = []
    for block in blocks:
        rows = block.strip().splitlines()
        if len(rows) < 2:
            continue
        idx = rows[0].strip()
        timecode = rows[1].strip()
        rest = rows[2:]

        content_lines = []
        has_error = False
        for line in rest:
            if ERROR_RE.match(line.strip()):
                has_error = True
            else:
                content_lines.append(line)

        entries.append({
            "index": idx,
            "timecode": timecode,
            "lines": content_lines,
            "translation": None,
            "has_error": has_error,
        })
    return entries


def write_srt(entries, progress, out_path):
    blocks = []
    for i, e in enumerate(entries):
        block = e["index"] + "\n" + e["timecode"] + "\n" + "\n".join(e["lines"])
        t = None
        if str(i) in progress and progress[str(i)]:
            t = progress[str(i)]
        elif e.get("translation"):
            t = e.get("translation")
        if t:
            block += "\n" + t
        blocks.append(block)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n\n".join(blocks) + "\n")
    # Use os.replace but tolerate occasional Windows locking by retrying
    for attempt in range(3):
        try:
            os.replace(tmp, out_path)
            return
        except PermissionError:
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
                os.replace(tmp, out_path)
                return
            except Exception:
                time.sleep(0.15)
    # Final fallback: write directly to the destination
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(blocks) + "\n")
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass


def save_progress(progress_path, progress):
    tmp = progress_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)
    # Try atomic replace with retries; on Windows this can fail if destination
    # is locked by another process. Fall back to direct write if necessary.
    for attempt in range(3):
        try:
            os.replace(tmp, progress_path)
            return
        except PermissionError:
            try:
                if os.path.exists(progress_path):
                    os.remove(progress_path)
                os.replace(tmp, progress_path)
                return
            except Exception:
                time.sleep(0.15)
    # Final fallback: write directly to the progress file
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass


def load_progress(progress_path):
    if os.path.exists(progress_path):
        try:
            with open(progress_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def translate_with_argos(text, source_lang, target_lang):
    """Translate using installed Argos Translate models (offline).

    Raises RuntimeError if no suitable model is installed.
    """
    if not HAS_ARGOS:
        raise RuntimeError("argostranslate not available")

    try:
        installed = argostranslate_translate.get_installed_languages()
    except Exception as e:
        raise RuntimeError(f"Failed to list Argos installed languages: {e}")

    # Find best matching language objects by code prefix
    src = None
    tgt = None
    for lang in installed:
        code = getattr(lang, 'code', None) or getattr(lang, 'language_code', None) or ''
        if not code:
            continue
        if code.lower().startswith(source_lang.lower()):
            src = lang
        if code.lower().startswith(target_lang.lower()):
            tgt = lang

    if src is None or tgt is None:
        installed_codes = ",".join(getattr(l, 'code', str(l)) for l in installed)
        raise RuntimeError(f"No Argos model installed for {source_lang}->{target_lang}. Installed: {installed_codes}")

    try:
        translator = src.get_translation(tgt)
        return translator.translate(text).strip()
    except Exception as e:
        raise RuntimeError(f"Argos translation failed: {e}")


def translate_text(translator, text, source_lang, target_lang, retries=RETRY):
    # Try online translator (deep-translator) first if available
    if translator is not None:
        for attempt in range(1, retries + 1):
            try:
                res = translator.translate(text)
                if res is not None:
                    return res.strip()
            except Exception as e:
                print(f"  Deep-translator attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(RETRY_WAIT * attempt)

    # Fallback to Argos Translate (offline) if available
    if HAS_ARGOS:
        try:
            return translate_with_argos(text, source_lang, target_lang)
        except Exception as e:
            print(f"  Argos fallback failed: {e}")

    return ""


def main():
    parser = argparse.ArgumentParser(description="Perbaiki SRT translation errors menggunakan Google (deep-translator)")
    parser.add_argument("input", help="File SRT input (dengan translation error)")
    parser.add_argument("output", help="File SRT output (sudah diperbaiki)")
    parser.add_argument("--source", "-s", default="ja", help="Bahasa sumber (default: ja)")
    parser.add_argument("--target", "-t", default="id", help="Bahasa target (default: id)")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help=f"Ukuran batch (default: {BATCH_SIZE})")
    parser.add_argument("--all", action="store_true", help="Terjemahkan ulang SEMUA baris, bukan hanya yang error")
    args = parser.parse_args()

    if GoogleTranslator is None and not HAS_ARGOS:
        print("ERROR: deep-translator not installed and argostranslate fallback not available.")
        print("Install with: pip install deep-translator or pip install argostranslate")
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"ERROR: File {args.input} tidak ditemukan.")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        raw = f.read()

    entries = parse_srt(raw)
    print(f"  {len(entries)} entri ditemukan")

    progress_path = args.output + ".progress.json"
    progress = load_progress(progress_path)

    to_fix = []
    for i, e in enumerate(entries):
        if not e["lines"]:
            continue
        if (args.all or e["has_error"]) and str(i) not in progress:
            to_fix.append(i)
        else:
            if str(i) in progress:
                entries[i]["translation"] = progress[str(i)]
                entries[i]["has_error"] = False

    print(f"  {len(to_fix)} entri perlu diterjemahkan")

    if not to_fix:
        print("  ✅ Tidak ada yang perlu diperbaiki!")
        write_srt(entries, progress, args.output)
        print(f"📄 Output ditulis ke: {args.output}")
        return

    batch_size = args.batch
    total = len(to_fix)
    done = 0

    print(f"\n🤖 Menerjemahkan ke-{total} entri (batch={batch_size})…\n")

    translator = GoogleTranslator(source=args.source, target=args.target) if GoogleTranslator else None

    for batch_start in range(0, total, batch_size):
        batch_indices = to_fix[batch_start: batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        print(f"  Batch {batch_num}/{total_batches} ({len(batch_indices)} kalimat)…", end=" ", flush=True)

        for idx in batch_indices:
            text = " ".join(entries[idx]["lines"]).strip()
            if not text:
                progress[str(idx)] = ""
                entries[idx]["translation"] = None
                save_progress(progress_path, progress)
                done += 1
                continue

            tr = translate_text(translator, text, args.source, args.target)
            progress[str(idx)] = tr
            entries[idx]["translation"] = tr if tr else None
            entries[idx]["has_error"] = False
            # persist per-item so we can resume immediately on network error
            try:
                save_progress(progress_path, progress)
            except Exception as e:
                print(f"  ⚠ Gagal menyimpan progress: {e}")

            done += 1
            # small delay to avoid hitting rate limits
            time.sleep(SLEEP_BETWEEN)

        # write SRT after each batch
        try:
            write_srt(entries, progress, args.output)
        except Exception as e:
            print(f"  ⚠ Gagal menulis output: {e}")

        print(f"✓ ({done}/{total})")

    print(f"\n💾 Menyimpan akhir ke: {args.output}")
    write_srt(entries, progress, args.output)
    print(f"✅ Selesai! {done} terjemahan berhasil diperbaiki.\n")


if __name__ == "__main__":
    main()
