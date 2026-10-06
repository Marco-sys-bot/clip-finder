import asyncio
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(os.getenv("DATA_DIR", "/tmp/clip-finder-data"))
BASE.mkdir(parents=True, exist_ok=True)

JOBS = {}

app = FastAPI(title="Clip Finder AI", version="15.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC = Path(__file__).resolve().parent


def run_cmd(cmd, cwd=None):
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=None,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"Programme introuvable: {cmd[0]}") from e

    if p.returncode != 0:
        raise RuntimeError(p.stdout[-12000:] or f"Commande échouée: {cmd[0]}")

    return p.stdout


def start_job(
    job_id: str,
    source: Optional[str],
    uploaded_path: Optional[Path],
    count: int,
    duration: int,
    language: str,
    captions: bool,
    reframe: bool,
    context: str,
):
    job = JOBS[job_id]
    job["status"] = "processing"
    work = BASE / job_id
    work.mkdir(parents=True, exist_ok=True)

    try:
        if uploaded_path:
            suffix = uploaded_path.suffix.lower() or ".mp4"
            src = work / f"source{suffix}"
            shutil.copy2(uploaded_path, src)
        else:
            src = work / "source.mp4"
            job["step"] = "Téléchargement de la vidéo"
            run_cmd(
                [
                    "yt-dlp",
                    "--no-playlist",
                    "--no-warnings",
                    "-f",
                    "bv*+ba/b",
                    "--merge-output-format",
                    "mp4",
                    "-o",
                    str(src),
                    source,
                ]
            )

        if not src.exists() or src.stat().st_size == 0:
            raise RuntimeError("La vidéo source n'a pas pu être créée.")

        job["step"] = "Analyse audio et transcription"

        pipeline = STATIC / "pipeline.py"
        if not pipeline.exists():
            raise RuntimeError("pipeline.py est introuvable dans le projet.")

        clips_dir = work / "clips"

        output = run_cmd(
            [
                "python3",
                str(pipeline),
                "--source",
                str(src),
                "--out",
                str(clips_dir),
                "--count",
                str(count),
                "--duration",
                str(duration),
                "--language",
                language,
                "--captions",
                "1" if captions else "0",
                "--reframe",
                "1" if reframe else "0",
                "--context",
                context[:1000],
            ],
            cwd=str(work),
        )

        clips = []
        for p in sorted(clips_dir.glob("clip_*.mp4")):
            clips.append(
                {
                    "name": p.name,
                    "url": f"/api/jobs/{job_id}/clips/{p.name}",
                    "size": p.stat().st_size,
                }
            )

        if not clips:
            raise RuntimeError(
                "Le traitement est terminé mais aucun clip n'a été généré."
            )

        job["clips"] = clips
        job["status"] = "done"
        job["step"] = "Terminé"
        job["log"] = output[-5000:]

    except Exception as e:
        job["status"] = "error"
        job["step"] = "Échec"
        job["error"] = str(e)[-12000:]

    finally:
        if uploaded_path and uploaded_path.exists():
            try:
                uploaded_path.unlink()
            except OSError:
                pass


@app.get("/", response_class=HTMLResponse)
def home():
    index = STATIC / "index.html"
    if not index.exists():
        raise HTTPException(500, "index.html est introuvable.")
    return index.read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "version": "15.1",
        "engine": "Whisper + OpenCV + FFmpeg + yt-dlp",
    }


@app.post("/api/jobs")
async def create_job(
    url: str = Form(""),
    file: Optional[UploadFile] = File(None),
    count: int = Form(5),
    duration: int = Form(90),
    language: str = Form("auto"),
    captions: int = Form(1),
    reframe: int = Form(1),
    context: str = Form(""),
):
    url = url.strip()

    if not url and not file:
        raise HTTPException(400, "Ajoute un fichier ou une URL.")

    count = max(1, min(count, 20))
    duration = max(60, min(duration, 180))

    job_id = uuid.uuid4().hex
    temp_upload = None

    if file:
        filename = Path(file.filename or "video.mp4")
        suffix = filename.suffix.lower() or ".mp4"

        allowed = {
            ".mp4",
            ".mov",
            ".mkv",
            ".webm",
            ".avi",
            ".m4v",
            ".mpeg",
            ".mpg",
        }

        if suffix not in allowed:
            raise HTTPException(400, "Format vidéo non pris en charge.")

        temp_upload = BASE / f"upload_{job_id}{suffix}"

        try:
            with temp_upload.open("wb") as f:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
        except Exception:
            if temp_upload.exists():
                temp_upload.unlink()
            raise

        if temp_upload.stat().st_size == 0:
            temp_upload.unlink(missing_ok=True)
            raise HTTPException(400, "Le fichier vidéo est vide.")

    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "step": "En attente",
        "clips": [],
        "error": None,
    }

    asyncio.create_task(
        asyncio.to_thread(
            start_job,
            job_id,
            url or None,
            temp_upload,
            count,
            duration,
            language,
            bool(captions),
            bool(reframe),
            context,
        )
    )

    return {"id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = JOBS.get(job_id)

    if not job:
        raise HTTPException(404, "Job introuvable.")

    return job


@app.get("/api/jobs/{job_id}/clips/{filename}")
def clip_file(job_id: str, filename: str):
    if Path(filename).name != filename:
        raise HTTPException(400, "Nom de fichier invalide.")

    p = BASE / job_id / "clips" / filename

    if not p.exists() or not p.is_file():
        raise HTTPException(404, "Clip introuvable.")

    return FileResponse(
        p,
        media_type="video/mp4",
        filename=filename,
    )


@app.get("/api/jobs/{job_id}/source")
def source_file(job_id: str):
    work = BASE / job_id

    for p in work.glob("source.*"):
        if p.is_file():
            return FileResponse(p)

    raise HTTPException(404, "Source introuvable.")
