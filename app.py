"""
Auto Subtitle Generator — Local Version
Optimized for Intel CPU (no GPU required)
"""

import whisper
try:
    import torch
except Exception:
    torch = None
import pykakasi
from deep_translator import GoogleTranslator
import gradio as gr
import json
import os
import re
import tempfile
import sys
import platform
import subprocess

# Workaround: some gradio_client.json schemas can be boolean (True/False).
# Older gradio_client versions assume schema is a dict and try to iterate keys
# which raises TypeError. Patch small helpers to be tolerant of boolean schema.
try:
    import gradio_client.utils as _gc_utils

    _orig__json_schema = getattr(_gc_utils, "_json_schema_to_python_type", None)
    if _orig__json_schema:
        def _patched__json_schema_to_python_type(schema, defs=None):
            if isinstance(schema, bool):
                schema = {}
            return _orig__json_schema(schema, defs)

        _gc_utils._json_schema_to_python_type = _patched__json_schema_to_python_type

    _orig_get_type = getattr(_gc_utils, "get_type", None)
    if _orig_get_type:
        def _patched_get_type(schema):
            if isinstance(schema, bool):
                return "dict"
            return _orig_get_type(schema)

        _gc_utils.get_type = _patched_get_type
except Exception:
    pass

# Workaround: starlette/Jinja2 signature mismatch in some envs.
# Older Gradio call sites sometimes call `templates.TemplateResponse(name, context)`
# while newer Starlette expects `templates.TemplateResponse(request, name, context)`.
# Shim `Jinja2Templates.TemplateResponse` to accept either form and extract the
# `request` from the provided context when necessary.
try:
    import starlette.templating as _st_templating

    _orig_TemplateResponse = getattr(_st_templating.Jinja2Templates, "TemplateResponse", None)

    if _orig_TemplateResponse:
        def _patched_TemplateResponse(self, request_or_name, name_or_context=None, context=None, status_code=200, headers=None, media_type=None, background=None):
            # If called as (name, context) — i.e., first arg is a template name string —
            # extract the request from the context dict and call original signature.
            try:
                if isinstance(request_or_name, str):
                    name = request_or_name
                    ctx = name_or_context or {}
                    req = ctx.get("request") if isinstance(ctx, dict) else None
                    return _orig_TemplateResponse(self, req, name, ctx, status_code=status_code, headers=headers, media_type=media_type, background=background)
            except Exception:
                pass

            # Otherwise assume modern signature (request, name, context)
            return _orig_TemplateResponse(self, request_or_name, name_or_context, context, status_code=status_code, headers=headers, media_type=media_type, background=background)

        _st_templating.Jinja2Templates.TemplateResponse = _patched_TemplateResponse
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_kks = None

def get_kakasi():
    global _kks
    if _kks is None:
        _kks = pykakasi.kakasi()
    return _kks


def has_japanese(text):
    return bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text))


def create_furigana_html(text):
    kks = get_kakasi()
    parts = []
    for item in kks.convert(text):
        orig = item["orig"]
        hira = item["hira"]
        is_kanji = bool(re.search(r"[\u4e00-\u9fff]", orig))
        if is_kanji and hira and hira != orig:
            parts.append(
                "<ruby>" + orig +
                "<rp>(</rp><rt style=\"font-size:0.65em;color:#888;\">" +
                hira + "</rt><rp>)</rp></ruby>"
            )
        else:
            parts.append(orig)
    return "".join(parts)


def create_romaji(text):
    kks = get_kakasi()
    return " ".join(i["hepburn"] for i in kks.convert(text) if i["hepburn"]).strip()


def _get_cpu_info():
    try:
        cores = os.cpu_count() or 1
    except Exception:
        cores = 1
    name = None
    try:
        # try cpuinfo first (optional dependency)
        from cpuinfo import get_cpu_info

        info = get_cpu_info()
        name = info.get("brand_raw")
    except Exception:
        pass

    if not name:
        try:
            name = platform.processor() or platform.uname().processor
        except Exception:
            name = None

    if not name and os.name == "nt":
        try:
            out = subprocess.check_output(["wmic", "cpu", "get", "Name"], universal_newlines=True)
            lines = [l.strip() for l in out.splitlines() if l.strip() and "Name" not in l]
            if lines:
                name = lines[0]
        except Exception:
            pass

    return {"name": name or "CPU", "cores": cores}


def _get_gpu_info():
    # Prefer torch.cuda if available
    if torch is not None:
        try:
            if torch.cuda.is_available():
                try:
                    props = torch.cuda.get_device_properties(0)
                    name = getattr(props, "name", None) or torch.cuda.get_device_name(0)
                    mem = getattr(props, "total_memory", None)
                    mem_gb = round(mem / (1024 ** 3), 1) if mem else None
                    return {"available": True, "name": name, "memory_gb": mem_gb}
                except Exception:
                    # fallback to get_device_name
                    try:
                        name = torch.cuda.get_device_name(0)
                        return {"available": True, "name": name, "memory_gb": None}
                    except Exception:
                        pass
        except Exception:
            pass

    # fallback: try nvidia-smi
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], universal_newlines=True)
        first = out.splitlines()[0].split(',')
        name = first[0].strip()
        mem_gb = round(float(first[1].strip()) / 1024, 1)
        return {"available": True, "name": name, "memory_gb": mem_gb}
    except Exception:
        return {"available": False, "name": None, "memory_gb": None}


def _get_system_memory_info():
    """Return system RAM usage in GB (used, total). Uses psutil if available, otherwise best-effort fallbacks."""
    try:
        import psutil

        vm = psutil.virtual_memory()
        total = vm.total
        used = total - vm.available
        return {"total_gb": round(total / (1024 ** 3), 1), "used_gb": round(used / (1024 ** 3), 1)}
    except Exception:
        pass

    # Linux fallback: /proc/meminfo
    try:
        if os.name == "posix" and os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo") as f:
                meminfo = f.read()
            import re

            total_k = re.search(r'^MemTotal:\s+(\d+)', meminfo, re.M)
            avail_k = re.search(r'^MemAvailable:\s+(\d+)', meminfo, re.M)
            if total_k and avail_k:
                total = int(total_k.group(1)) * 1024
                avail = int(avail_k.group(1)) * 1024
                used = total - avail
                return {"total_gb": round(total / (1024 ** 3), 1), "used_gb": round(used / (1024 ** 3), 1)}
    except Exception:
        pass

    return {"total_gb": None, "used_gb": None}


def _get_gpu_memory_usage():
    """Return GPU memory usage in GB (used, total) when possible.
    Tries nvidia-smi, then torch.cuda as fallback.
    """
    # nvidia-smi
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], universal_newlines=True)
        first = out.splitlines()[0].split(',')
        used = float(first[0].strip())
        total = float(first[1].strip())
        return {"used_gb": round(used / 1024, 1), "total_gb": round(total / 1024, 1)}
    except Exception:
        pass

    # torch fallback
    if torch is not None:
        try:
            if torch.cuda.is_available():
                used = torch.cuda.memory_allocated(0)
                props = torch.cuda.get_device_properties(0)
                total = getattr(props, "total_memory", None)
                if total:
                    return {"used_gb": round(used / (1024 ** 3), 1), "total_gb": round(total / (1024 ** 3), 1)}
                return {"used_gb": round(used / (1024 ** 3), 1), "total_gb": None}
        except Exception:
            pass

    return {"used_gb": None, "total_gb": None}


def _classify_device():
    cpu = _get_cpu_info()
    gpu = _get_gpu_info()
    if gpu.get("available"):
        mem = gpu.get("memory_gb") or 0
        if mem >= 16:
            cat = "gpu_high"
        elif mem >= 8:
            cat = "gpu_mid"
        else:
            cat = "gpu_low"
    else:
        cores = cpu.get("cores") or 1
        name = (cpu.get("name") or "").lower()
        if "celeron" in name or "atom" in name or cores <= 2:
            cat = "cpu_low"
        elif cores <= 4:
            cat = "cpu_mid"
        else:
            cat = "cpu_high"

    return {"cpu": cpu, "gpu": gpu, "category": cat}


_ESTIMATES = {
    "gpu_high": {"tiny": "≈ 0.5–2 menit", "base": "≈ 1–3 menit", "small": "≈ 2–6 menit", "medium": "≈ 6–20 menit"},
    "gpu_mid":  {"tiny": "≈ 1–3 menit",   "base": "≈ 2–5 menit", "small": "≈ 5–12 menit", "medium": "≈ 12–35 menit"},
    "gpu_low":  {"tiny": "≈ 2–6 menit",   "base": "≈ 5–15 menit", "small": "≈ 12–40 menit", "medium": "≈ 40–120 menit"},
    "cpu_high": {"tiny": "≈ 10–25 menit", "base": "≈ 20–60 menit", "small": "≈ 45–150 menit", "medium": "≈ 150–400 menit"},
    "cpu_mid":  {"tiny": "≈ 20–60 menit", "base": "≈ 45–120 menit", "small": "≈ 90–300 menit", "medium": "≈ 300–800 menit"},
    "cpu_low":  {"tiny": "≈ 60–180 menit","base": "≈ 120–360 menit","small": "≈ 300–900 menit","medium": "≈ 900+ menit"},
}


def build_device_message_html():
    info = _classify_device()
    cpu = info["cpu"]
    gpu = info["gpu"]
    cat = info["category"]

    lines = []
    lines.append("<div style='font-size:0.95em;color:#444;margin-bottom:6px;'>")
    if gpu.get("available"):
        gpu_name = gpu.get("name") or "GPU"
        mem = f" — {gpu.get('memory_gb')} GB" if gpu.get('memory_gb') else ""
        lines.append(f"ℹ️ Detected GPU: <strong>{gpu_name}{mem}</strong>")
    else:
        cpu_name = cpu.get("name") or "CPU"
        cores = cpu.get("cores") or 1
        lines.append(f"ℹ️ Detected CPU: <strong>{cpu_name} ({cores} cores)</strong>")

    lines.append("</div>")

    # estimates per model size
    est = _ESTIMATES.get(cat, _ESTIMATES["cpu_mid"]) 
    lines.append("<div style='font-size:0.92em;color:#555;margin-top:6px;'>Perkiraan waktu pemrosesan (per 1 jam audio):</div>")
    lines.append("<ul style='margin-top:6px;color:#444;'>")
    for m in ["tiny", "base", "small", "medium"]:
        label = {
            "tiny": "tiny — cepat (direkomendasikan untuk perangkat lambat)",
            "base": "base — lebih akurat, agak lambat",
            "small": "small — akurat, lambat di CPU",
            "medium": "medium — sangat lambat di CPU (tidak direkomendasikan)",
        }[m]
        lines.append(f"<li><strong>{label}</strong>: {est.get(m)}</li>")
    lines.append("</ul>")

    lines.append("<div style='font-size:0.88em;color:#666;margin-top:8px;'>Perangkat yang akan digunakan saat pemuatan model akan terlihat setelah proses dimulai.</div>")

    return "".join(lines)


def translate_text(text, source, target):
    if not text.strip() or target == "none":
        return ""
    try:
        return GoogleTranslator(source=source, target=target).translate(text) or ""
    except Exception as e:
        print(f"[Translation error] {e}", file=sys.stderr)
        return f"[Translation error: {e}]"


def fmt_srt_time(s):
    s = float(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    ms = (s % 1) * 1000
    return "%02d:%02d:%02d,%03d" % (int(h), int(m), int(sec), int(ms))


def fmt_display_time(s):
    s = float(s)
    m, sec = divmod(s, 60)
    return "%02d:%02d" % (int(m), int(sec))


def generate_srt_content(segments):
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(fmt_srt_time(seg["start"]) + " --> " + fmt_srt_time(seg["end"]))
        lines.append(seg["text"])
        if seg.get("translation"):
            lines.append(seg["translation"])
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# HTML SUBTITLE RENDERER
# ─────────────────────────────────────────────────────────────────────────────

def generate_subtitle_html(segments, source_lang):
    items_html = []
    for i, seg in enumerate(segments):
        text        = seg["text"]
        translation = seg.get("translation", "")
        romaji      = seg.get("romaji", "")
        furigana    = seg.get("furigana_html", text)
        time_label  = fmt_display_time(seg["start"])

        item = (
            f'<div class="sub-item" id="seg-{i}"'
            f' onclick="seekToSeg({i})"'
            f' style="cursor:pointer;padding:12px 16px;margin:4px 0;'
            f'background:white;border-radius:8px;'
            f'border-left:4px solid transparent;'
            f'transition:all 0.2s ease;'
            f'box-shadow:0 1px 3px rgba(0,0,0,0.08);">'
        )
        item += f'<div style="font-size:0.75em;color:#aaa;margin-bottom:4px;">{time_label}</div>'

        if source_lang == "ja" and has_japanese(text):
            item += f'<div style="font-size:1.2em;line-height:2.4;color:#333;">{furigana}</div>'
            if romaji:
                item += (
                    f'<div style="font-size:0.82em;color:#999;font-style:italic;'
                    f'margin-top:2px;">{romaji}</div>'
                )
        else:
            item += f'<div style="font-size:1.05em;color:#333;line-height:1.5;">{text}</div>'

        if translation:
            item += (
                f'<div style="font-size:0.93em;color:#555;margin-top:6px;'
                f'padding-top:6px;border-top:1px solid #f0f0f0;">{translation}</div>'
            )
        item += "</div>"
        items_html.append(item)

    segs_data = json.dumps(
        [{"start": s["start"], "end": s["end"]} for s in segments]
    )

    js = """
<script>
var __subSegs = """ + segs_data + """;
var __lastIdx = -1;

function seekToSeg(idx) {
    var audio = document.querySelector("audio");
    if (audio && __subSegs[idx] !== undefined) {
        audio.currentTime = __subSegs[idx].start;
        if (audio.paused) { audio.play(); }
    }
}

function __updateSubs() {
    var audio = document.querySelector("audio");
    if (!audio) return;
    var t = audio.currentTime;
    var activeIdx = -1;
    for (var i = 0; i < __subSegs.length; i++) {
        if (t >= __subSegs[i].start && t < __subSegs[i].end) {
            activeIdx = i; break;
        }
    }
    if (activeIdx === __lastIdx) return;
    __lastIdx = activeIdx;
    var items = document.querySelectorAll(".sub-item");
    items.forEach(function(el) {
        el.style.background = "white";
        el.style.borderLeftColor = "transparent";
        el.style.transform = "scale(1)";
    });
    if (activeIdx >= 0) {
        var el = document.getElementById("seg-" + activeIdx);
        if (el) {
            el.style.background = "#e8f5e9";
            el.style.borderLeftColor = "#43a047";
            el.style.transform = "scale(1.005)";
            el.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
    }
}

function __initSubSync() {
    var audio = document.querySelector("audio");
    if (!audio) { setTimeout(__initSubSync, 800); return; }
    audio.addEventListener("timeupdate", __updateSubs);
    console.log("Subtitle sync OK!");
}
setTimeout(__initSubSync, 600);
</script>"""
    return (
        '<div style="font-family:\'Noto Sans JP\',sans-serif;">'
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;700&display=swap" rel="stylesheet">'
        '<div style="background:#f0f7f0;border-radius:10px;padding:8px 12px;'
        'margin-bottom:8px;border:1px solid #c8e6c9;">'
        '<div style="font-size:0.82em;color:#388e3c;text-align:center;">'
        '💡 Klik baris subtitle untuk loncat ke posisi audio tersebut'
        '</div></div>'
        '<div id="sub-scroll" style="max-height:520px;overflow-y:auto;padding:4px;">'
        + "".join(items_html)
        + '</div>'
        + js
        + '</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

_whisper_model      = None
_current_model_size = None
_whisper_device     = None


def process_audio(audio_path, source_lang, target_lang, model_size, progress=gr.Progress()):
    global _whisper_model, _current_model_size, _whisper_device

    if audio_path is None:
        return (
            "<p style='color:#e53935;padding:20px;'>⚠️ Silahkan upload file audio terlebih dahulu.</p>",
            None,
        )

    if _whisper_model is None or _current_model_size != model_size:
        # Tentukan apakah GPU (CUDA) tersedia
        prefer_gpu = False
        if torch is not None:
            try:
                prefer_gpu = torch.cuda.is_available()
            except Exception:
                prefer_gpu = False

        if prefer_gpu:
            progress(0.05, desc=f"Loading Whisper model '{model_size}' on GPU…")
            try:
                _whisper_model = whisper.load_model(model_size, device="cuda")
                _whisper_device = "cuda"
            except Exception as e:
                print(f"[GPU load failed] {e}", file=sys.stderr)
                progress(0.05, desc=f"Loading Whisper model '{model_size}' on CPU as fallback…")
                _whisper_model = whisper.load_model(model_size, device="cpu")
                _whisper_device = "cpu"
        else:
            progress(0.05, desc=f"Loading Whisper model '{model_size}' on CPU…")
            _whisper_model = whisper.load_model(model_size, device="cpu")
            _whisper_device = "cpu"

        _current_model_size = model_size

    # Build runtime device info to show in UI
    try:
        if _whisper_device == "cuda":
            gpu = _get_gpu_info()
            dev_name = gpu.get("name") or "GPU"
            # GPU VRAM
            gpu_mem = _get_gpu_memory_usage()
            v_used = gpu_mem.get("used_gb")
            v_total = gpu_mem.get("total_gb")
            if v_used is not None and v_total is not None:
                vram_line = f"<div style='font-size:0.9em;color:#666;margin-top:4px;'>VRAM: {v_used} GB used / {v_total} GB total</div>"
            elif v_total is not None:
                vram_line = f"<div style='font-size:0.9em;color:#666;margin-top:4px;'>VRAM: {v_total} GB total</div>"
            else:
                vram_line = "<div style='font-size:0.9em;color:#666;margin-top:4px;'>VRAM: unknown</div>"

            # System RAM
            sys_mem = _get_system_memory_info()
            s_used = sys_mem.get("used_gb")
            s_total = sys_mem.get("total_gb")
            if s_used is not None and s_total is not None:
                ram_line = f"<div style='font-size:0.9em;color:#666;'>RAM: {s_used} GB used / {s_total} GB total</div>"
            elif s_total is not None:
                ram_line = f"<div style='font-size:0.9em;color:#666;'>RAM: {s_total} GB total</div>"
            else:
                ram_line = "<div style='font-size:0.9em;color:#666;'>RAM: unknown</div>"

            runtime_device_html = (
                f"<div style='font-size:0.95em;color:#333;'>Device running: <strong>GPU — {dev_name}</strong></div>"
                + vram_line
                + ram_line
            )
        else:
            cpu = _get_cpu_info()
            dev_name = cpu.get("name") or "CPU"
            sys_mem = _get_system_memory_info()
            s_used = sys_mem.get("used_gb")
            s_total = sys_mem.get("total_gb")
            if s_used is not None and s_total is not None:
                ram_line = f"<div style='font-size:0.9em;color:#666;margin-top:4px;'>RAM: {s_used} GB used / {s_total} GB total</div>"
            elif s_total is not None:
                ram_line = f"<div style='font-size:0.9em;color:#666;margin-top:4px;'>RAM: {s_total} GB total</div>"
            else:
                ram_line = "<div style='font-size:0.9em;color:#666;margin-top:4px;'>RAM: unknown</div>"

            runtime_device_html = (
                f"<div style='font-size:0.95em;color:#333;'>Device running: <strong>CPU — {dev_name}</strong></div>"
                + ram_line
            )
    except Exception:
        runtime_device_html = ""

    progress(0.15, desc="Transkripsi audio…")

    lang_code = None if source_lang == "auto" else source_lang
    use_fp16 = (_whisper_device == "cuda")
    result    = _whisper_model.transcribe(
        audio_path,
        language=lang_code,
        task="transcribe",
        verbose=False,
        fp16=use_fp16,
    )

    raw_segs      = result["segments"]
    detected_lang = result.get("language", source_lang)
    if source_lang == "auto":
        source_lang = detected_lang

    processed = []
    n = len(raw_segs)

    for i, seg in enumerate(raw_segs):
        progress(
            0.25 + 0.55 * (i / max(n, 1)),
            desc=f"Processing segment {i+1}/{n}…",
        )
        text = seg["text"].strip()
        if not text:
            continue

        furigana_html = text
        romaji        = ""
        if source_lang == "ja":
            furigana_html = create_furigana_html(text)
            romaji        = create_romaji(text)

        translation = ""
        if target_lang != "none":
            translation = translate_text(text, source_lang, target_lang)

        processed.append({
            "start":        seg["start"],
            "end":          seg["end"],
            "text":         text,
            "furigana_html": furigana_html,
            "romaji":        romaji,
            "translation":   translation,
        })

    progress(0.90, desc="Membuat tampilan subtitle…")
    subtitle_html = generate_subtitle_html(processed, source_lang)
    # Gabungkan info device (jika ada) ke tampilan subtitle supaya tidak perlu output terpisah
    try:
        subtitle_html = runtime_device_html + subtitle_html
    except Exception:
        pass

    progress(0.96, desc="Membuat file SRT…")
    srt_content = generate_srt_content(processed)
    srt_path    = tempfile.mktemp(suffix=".srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    progress(1.0, desc="Selesai! ✅")
    return subtitle_html, srt_path


# ─────────────────────────────────────────────────────────────────────────────
# GRADIO UI
# ─────────────────────────────────────────────────────────────────────────────

SOURCE_LANGS = [
    ("Auto-detect",      "auto"),
    ("Japanese 🇯🇵",    "ja"),
    ("English 🇺🇸",     "en"),
    ("Korean 🇰🇷",      "ko"),
    ("Chinese 🇨🇳",     "zh"),
    ("Indonesian 🇮🇩",  "id"),
    ("Spanish 🇪🇸",     "es"),
    ("French 🇫🇷",      "fr"),
    ("German 🇩🇪",      "de"),
]

TARGET_LANGS = [
    ("Tidak ada terjemahan", "none"),
    ("Indonesian 🇮🇩",     "id"),
    ("English 🇺🇸",        "en"),
    ("Japanese 🇯🇵",       "ja"),
    ("Korean 🇰🇷",         "ko"),
    ("Chinese Simplified 🇨🇳", "zh-CN"),
    ("Spanish 🇪🇸",        "es"),
    ("French 🇫🇷",         "fr"),
    ("German 🇩🇪",         "de"),
    ("Portuguese 🇧🇷",     "pt"),
    ("Arabic 🇸🇦",         "ar"),
]

# tiny dan base lebih cocok untuk Celeron N4000
MODEL_SIZES = [
    ("tiny  — paling cepat (recommended untuk Celeron) ✅", "tiny"),
    ("base  — lebih akurat, agak lambat",                   "base"),
    ("small — akurat, lambat di CPU",                       "small"),
    ("medium — sangat lambat di CPU (tidak direkomendasikan)", "medium"),
]

CUSTOM_CSS = """
    footer { display: none !important; }
    .gradio-container { max-width: 1100px !important; margin: auto; }
    #subtitle-panel { min-height: 400px; }
"""

with gr.Blocks(
    title="Auto Subtitle Generator",
    theme=gr.themes.Soft(primary_hue="green"),
    css=CUSTOM_CSS,
) as demo:

    gr.Markdown("""
# 🎧 Auto Subtitle Generator — Local
Transkripsi audio otomatis · Furigana Jepang · Terjemahan gratis · Download SRT
    """)

    with gr.Row():
        # ── Left panel ──────────────────────────────────────────────────────
        with gr.Column(scale=1, min_width=280):
            audio_input = gr.Audio(
                label="📁 Upload File Audio",
                type="filepath",
                sources=["upload"],
            )
            source_lang_dd = gr.Dropdown(
                choices=SOURCE_LANGS,
                value="ja",
                label="🌐 Bahasa Audio",
            )
            target_lang_dd = gr.Dropdown(
                choices=TARGET_LANGS,
                value="id",
                label="🔀 Terjemahkan ke",
            )
            model_dd = gr.Dropdown(
                choices=MODEL_SIZES,
                value="tiny",
                label="🤖 Model Whisper",
            )
            device_info_html = gr.HTML(value=build_device_message_html())
            process_btn = gr.Button(
                "🚀  Generate Subtitles",
                variant="primary",
                size="lg",
            )
            srt_file = gr.File(label="⬇️ Download SRT")

        # ── Right panel ──────────────────────────────────────────────────────
        with gr.Column(scale=2):
            subtitle_html = gr.HTML(
                value=(
                    "<div style='text-align:center;padding:80px 20px;color:#bbb;"
                    "font-family:sans-serif;'>"
                    "<div style='font-size:3.5em;margin-bottom:16px;'>🎵</div>"
                    "<div style='font-size:1.1em;'>Upload file audio lalu klik "
                    "<strong>Generate Subtitles</strong></div>"
                    "</div>"
                ),
                elem_id="subtitle-panel",
            )

    process_btn.click(
        fn=process_audio,
        inputs=[audio_input, source_lang_dd, target_lang_dd, model_dd],
        outputs=[subtitle_html, srt_file],
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print(f"\n🚀 Auto Subtitle Generator berjalan di http://localhost:{port}\n")
    demo.launch(
        # server_name="127.0.0.1",
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_error=True,
        quiet=False,
    )
