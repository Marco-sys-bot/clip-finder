import asyncio
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(os.getenv("DATA_DIR", "/tmp/clip-finder-data"))
BASE.mkdir(parents=True, exist_ok=True)
JOBS = {}

app = FastAPI(title="Clip Finder AI", version="15.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC = Path(__file__).parent / "web"
app.mount("/assets", StaticFiles(directory=STATIC), name="assets")


def run_cmd(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stdout[-12000:])
    return p.stdout


def start_job(job_id: str, source: Optional[str], uploaded_path: Optional[Path],
              count: int, duration: int, language: str, captions: bool,
              reframe: bool, context: str):
    job = JOBS[job_id]
    job["status"] = "processing"
    work = BASE / job_id
    work.mkdir(parents=True, exist_ok=True)

    try:
        if uploaded_path:
            src = work / "source" + uploaded_path.suffix
            shutil.copy2(uploaded_path, src)
        else:
            src = work / "source.mp4"
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "-f", "bv*+ba/b",
                "--merge-output-format", "mp4",
                "-o", str(src),
                source,
            ]
            job["step"] = "Téléchargement de la vidéo"
            run_cmd(cmd)

        job["step"] = "Analyse audio et transcription"
        pipeline = Path(__file__).parent / "pipeline.py"
        cmd = [
            "python3", str(pipeline),
            "--source", str(src),
            "--out", str(work / "clips"),
            "--count", str(count),
            "--duration", str(duration),
            "--language", language,
            "--captions", "1" if captions else "0",
            "--reframe", "1" if reframe else "0",
            "--context", context[:1000],
        ]
        output = run_cmd(cmd, cwd=str(work))
        job["step"] = "Terminé"
        clips_dir = work / "clips"
        clips = []
        for p in sorted(clips_dir.glob("clip_*.mp4")):
            clips.append({
                "name": p.name,
                "url": f"/api/jobs/{job_id}/clips/{p.name}",
                "size": p.stat().st_size,
            })
        job["clips"] = clips
        job["status"] = "done"
        job["log"] = output[-5000:]
    except Exception as e:
        job["status"] = "error"
        job["step"] = "Échec"
        job["error"] = str(e)[-12000:]
    finally:
        if uploaded_path and uploaded_path.exists():
            uploaded_path.unlink(missing_ok=True)


@app.get("/", response_class=HTMLResponse)
def home():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    return {"ok": True, "version": "15.0", "engine": "Whisper + OpenCV + FFmpeg + yt-dlp"}


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
    if not url and not file:
        raise HTTPException(400, "Ajoute un fichier ou une URL.")
    count = max(1, min(count, 20))
    duration = max(60, min(duration, 180))

    job_id = uuid.uuid4().hex
    temp_upload = None
    if file:
        suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
        temp_upload = BASE / f"upload_{job_id}{suffix}"
        with temp_upload.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)

    JOBS[job_id] = {
        "id": job_id, "status": "queued", "step": "En attente",
        "clips": [], "error": None
    }

    asyncio.create_task(asyncio.to_thread(
        start_job, job_id, url.strip() or None, temp_upload,
        count, duration, language, bool(captions), bool(reframe), context
    ))
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
    if not p.exists():
        raise HTTPException(404, "Clip introuvable.")
    return FileResponse(p, media_type="video/mp4", filename=filename)


@app.get("/api/jobs/{job_id}/source")
def source_file(job_id: str):
    work = BASE / job_id
    for p in work.glob("source.*"):
        return FileResponse(p)
    raise HTTPException(404, "Source introuvable.")
