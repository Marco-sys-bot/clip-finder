import argparse
import os
import subprocess
from pathlib import Path

import cv2
from faster_whisper import WhisperModel


HOOKS = {
    "important", "attention", "incroyable", "jamais", "toujours",
    "secret", "pourquoi", "comment", "voici", "regardez", "écoute",
    "écoutez", "imagine", "surprise", "exactement", "erreur",
    "problème", "meilleur", "worst", "best", "never", "always",
    "why", "how", "look",
}


def cmd(command):
    try:
        p = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"Programme introuvable: {command[0]}") from e

    if p.returncode != 0:
        raise RuntimeError(p.stdout[-12000:] or "Commande FFmpeg/ffprobe échouée.")

    return p.stdout


def video_duration(path):
    out = cmd([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]).strip()

    try:
        value = float(out)
    except ValueError as e:
        raise RuntimeError("Impossible de lire la durée de la vidéo.") from e

    if value <= 0:
        raise RuntimeError("La vidéo a une durée invalide.")

    return value


def transcribe(path, language):
    model_name = os.getenv("WHISPER_MODEL", "small")
    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    model = WhisperModel(
        model_name,
        device=device,
        compute_type=compute,
    )

    kwargs = {
        "word_timestamps": True,
        "vad_filter": True,
    }

    if language and language != "auto":
        kwargs["language"] = language

    segments, _info = model.transcribe(str(path), **kwargs)

    words = []

    for segment in segments:
        for word in segment.words or []:
            if word.start is None or word.end is None:
                continue

            text = (word.word or "").strip()

            if text:
                words.append(
                    {
                        "start": float(word.start),
                        "end": float(word.end),
                        "text": text,
                    }
                )

    return words


def choose(words, total, count, target, context):
    target = min(float(target), total)
    target = max(1.0, target)

    step = max(15.0, target * 0.35)

    starts = []
    t = 0.0

    while t + target <= total:
        starts.append(t)
        t += step

    if not starts:
        starts = [0.0]

    context_terms = {
        x.lower()
        for x in context.split()
        if len(x) > 3
    }

    candidates = []

    for start in starts:
        end = min(total, start + target)

        inside = [
            w for w in words
            if w["end"] > start and w["start"] < end
        ]

        text = " ".join(w["text"] for w in inside).lower()

        if not inside:
            score = 0.0
        else:
            density = min(
                1.0,
                len(inside) / max(1.0, target * 2.2),
            )

            hooks = sum(
                1
                for token in text.split()
                if token.strip(".,!?;:()[]\"'") in HOOKS
            )

            context_hits = sum(
                1 for term in context_terms if term in text
            )

            punctuation = text.count("?") + text.count("!")

            score = (
                density * 55
                + min(25, hooks * 4)
                + min(15, context_hits * 3)
                + min(10, punctuation)
            )

        candidates.append((score, start, end))

    candidates.sort(key=lambda item: item[0], reverse=True)

    selected = []

    for item in candidates:
        if all(
            abs(item[1] - chosen[1]) > target * 0.45
            for chosen in selected
        ):
            selected.append(item)

        if len(selected) >= count:
            break

    if not selected:
        selected = [(0.0, 0.0, min(total, target))]

    selected.sort(key=lambda item: item[1])

    return selected


def face_center(path, start, end):
    cap = cv2.VideoCapture(str(path))

    if not cap.isOpened():
        return 0.5

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)

    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades
        + "haarcascade_frontalface_default.xml"
    )

    xs = []

    sample_count = max(1, int((end - start) / 2))

    for _ in range(sample_count):
        ok, frame = cap.read()

        if not ok:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = cascade.detectMultiScale(
            gray,
            1.1,
            5,
            minSize=(70, 70),
        )

        if len(faces):
            faces = sorted(
                faces,
                key=lambda face: face[2] * face[3],
                reverse=True,
            )

            x, _y, w, _h = faces[0]

            xs.append(
                (x + w / 2) / max(1, frame.shape[1])
            )

        for _skip in range(max(1, int(fps * 2)) - 1):
            cap.grab()

    cap.release()

    return sum(xs) / len(xs) if xs else 0.5


def make_ass(words, start, end, output):
    relevant = [
        w for w in words
        if w["end"] > start and w["start"] < end
    ]

    lines = []

    for i in range(0, len(relevant), 5):
        group = relevant[i:i + 5]

        if not group:
            continue

        a = max(start, group[0]["start"]) - start
        b = min(end, group[-1]["end"]) - start

        def timestamp(value):
            hours = int(value // 3600)
            value %= 3600
            minutes = int(value // 60)
            seconds = value % 60
            return f"{hours}:{minutes:02d}:{seconds:05.2f}"

        text = " ".join(
            word["text"] for word in group
        ).replace("{", "").replace("}", "")

        lines.append(
            f"Dialogue: 0,{timestamp(a)},{timestamp(b)},"
            f"Default,,0,0,0,,{text}"
        )

    output.write_text(
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
        "OutlineColour,BackColour,Bold,Italic,Underline,Strike,ScaleX,"
        "ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,"
        "MarginL,MarginR,MarginV,Encoding\n"
        "Style: Default,Arial,18,&H00FFFFFF,&H0000FFFF,&H00000000,"
        "&H66000000,1,0,0,0,100,100,0,0,1,3,1,2,40,40,130,1\n"
        "[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,"
        "Effect,Text\n"
        + "\n".join(lines),
        encoding="utf-8",
    )


def render(src, output, start, end, words, reframe, captions):
    ass = None

    if captions and words:
        ass = output.with_suffix(".ass")
        make_ass(words, start, end, ass)

    if reframe:
        center = face_center(src, start, end)
        center = max(0.0, min(1.0, center))

        # After scaling the height to 1920, keep a 1080px vertical crop
        # centered on the detected face.
        vf = (
            "scale=-2:1920,"
            f"crop=1080:1920:(iw-1080)*{center}:0"
        )
    else:
        vf = "scale=-2:1920,crop=1080:1920:(iw-1080)/2:0"

    if ass:
        ass_path = (
            str(ass)
            .replace("\\", "/")
            .replace(":", "\\:")
        )
        vf += ",ass=" + ass_path

    cmd([
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-to", str(end),
        "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "160k",
        "-movflags", "+faststart",
        str(output),
    ])


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--duration", type=int, default=90)
    parser.add_argument("--language", default="auto")
    parser.add_argument("--captions", type=int, default=1)
    parser.add_argument("--reframe", type=int, default=1)
    parser.add_argument("--context", default="")

    args = parser.parse_args()

    source = Path(args.source)
    output_dir = Path(args.out)

    if not source.exists():
        raise RuntimeError(f"Vidéo source introuvable: {source}")

    output_dir.mkdir(parents=True, exist_ok=True)

    total = video_duration(source)

    # Transcription is needed both for clip selection and optional captions.
    words = transcribe(source, args.language)

    selected = choose(
        words,
        total,
        max(1, min(args.count, 20)),
        max(1, min(args.duration, 180)),
        args.context,
    )

    for index, (_score, start, end) in enumerate(selected, 1):
        render(
            source,
            output_dir / f"clip_{index:02d}.mp4",
            start,
            end,
            words,
            bool(args.reframe),
            bool(args.captions),
        )


if __name__ == "__main__":
    main()
