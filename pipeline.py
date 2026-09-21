import argparse
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

import cv2
from faster_whisper import WhisperModel


HOOKS = {
    "important", "attention", "incroyable", "jamais", "toujours", "secret",
    "pourquoi", "comment", "voici", "regardez", "écoute", "écoutez",
    "imagine", "surprise", "exactement", "erreur", "problème", "meilleur",
    "worst", "best", "never", "always", "why", "how", "secret", "look"
}


def cmd(c):
    p = subprocess.run(c, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode:
        raise RuntimeError(p.stdout[-12000:])
    return p.stdout


def duration(path):
    out = cmd(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(out.strip())


def transcribe(path, language):
    model_name = os.getenv("WHISPER_MODEL", "small")
    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    model = WhisperModel(model_name, device=device, compute_type=compute)
    kwargs = dict(word_timestamps=True, vad_filter=True)
    if language != "auto":
        kwargs["language"] = language
    segments, info = model.transcribe(str(path), **kwargs)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            words.append({
                "start": float(w.start), "end": float(w.end),
                "text": (w.word or "").strip()
            })
    return words


def choose(words, total, count, target, context):
    # Deterministic local baseline: speech density + hook words + punctuation.
    step = max(15.0, target * 0.35)
    candidates = []
    starts = []
    t = 0.0
    while t + target <= total:
        starts.append(t)
        t += step
    if not starts:
        starts = [0.0]

    context_terms = {x.lower() for x in context.split() if len(x) > 3}
    for s in starts:
        e = min(total, s + target)
        inside = [w for w in words if w["end"] > s and w["start"] < e]
        text = " ".join(w["text"] for w in inside).lower()
        if not inside:
            score = 0.0
        else:
            density = min(1.0, len(inside) / max(1.0, target * 2.2))
            hooks = sum(1 for x in text.split() if x.strip(".,!?;:") in HOOKS)
            context_hits = sum(1 for x in context_terms if x in text)
            punctuation = text.count("?") + text.count("!")
            score = density * 55 + min(25, hooks * 4) + min(15, context_hits * 3) + min(10, punctuation)
        candidates.append((score, s, e))

    candidates.sort(reverse=True)
    selected = []
    for item in candidates:
        if all(abs(item[1] - x[1]) > target * 0.45 for x in selected):
            selected.append(item)
        if len(selected) >= count:
            break
    selected.sort(key=lambda x: x[1])
    return selected


def face_center(path, start, end):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    xs = []
    for _ in range(max(1, int((end-start) / 2))):
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(70, 70))
        if len(faces):
            faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
            x, y, w, h = faces[0]
            xs.append((x + w/2) / max(1, frame.shape[1]))
        for _skip in range(max(1, int(fps*2))-1):
            cap.grab()
    cap.release()
    return sum(xs)/len(xs) if xs else 0.5


def make_ass(words, start, end, out):
    relevant = [w for w in words if w["end"] > start and w["start"] < end]
    lines = []
    for i in range(0, len(relevant), 5):
        group = relevant[i:i+5]
        if not group:
            continue
        a = max(start, group[0]["start"]) - start
        b = min(end, group[-1]["end"]) - start
        def ts(x):
            h = int(x//3600); x%=3600
            m = int(x//60); s = x%60
            return f"{h}:{m:02d}:{s:05.2f}"
        text = " ".join(w["text"] for w in group).replace("{","").replace("}","")
        lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},Default,,0,0,0,,{text}")
    out.write_text(
        "[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,Strike,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,"
        "MarginL,MarginR,MarginV,Encoding\n"
        "Style: Default,Arial,18,&H00FFFFFF,&H0000FFFF,&H00000000,&H66000000,"
        "1,0,0,0,100,100,0,0,1,3,1,2,40,40,130,1\n"
        "[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n" +
        "\n".join(lines), encoding="utf-8"
    )


def render(src, out, start, end, words, reframe, captions):
    ass = None
    if captions and words:
        ass = out.with_suffix(".ass")
        make_ass(words, start, end, ass)

    if reframe:
        cx = face_center(src, start, end)
        crop_x = max(0.0, min(1.0, cx))
        # Scale so height is 1920 then crop 1080 wide.
        vf = "scale=-2:1920,crop=1080:1920:max(0\\,min(iw-1080\\,iw*%0.4-540)):0" % crop_x
    else:
        vf = "scale=-2:1920,crop=1080:1920:(iw-1080)/2:0"

    if ass:
        ass_path = str(ass).replace("\\", "/").replace(":", "\\:")
        vf += ",ass=" + ass_path

    cmdline = [
        "ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", str(src),
        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(out)
    ]
    cmd(cmdline)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--duration", type=int, default=90)
    ap.add_argument("--language", default="auto")
    ap.add_argument("--captions", type=int, default=1)
    ap.add_argument("--reframe", type=int, default=1)
    ap.add_argument("--context", default="")
    a = ap.parse_args()

    src = Path(a.source)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    total = duration(src)
    words = transcribe(src, a.language) if a.captions or True else []
    selected = choose(words, total, a.count, a.duration, a.context)

    for i, (_, s, e) in enumerate(selected, 1):
        render(src, out / f"clip_{i:02d}.mp4", s, e, words, bool(a.reframe), bool(a.captions))


if __name__ == "__main__":
    main()
