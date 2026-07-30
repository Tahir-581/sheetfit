"""FastAPI service for the Sheetfit web app."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import DEFAULT_TARGET_PAGES, DEFAULT_THRESHOLD, __version__
from .expand import expand_pdf
from .extract import page_count

DATA_DIR = Path(__file__).resolve().parents[1] / ".data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Sheetfit", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InfoResponse(BaseModel):
    pages: int
    threshold: int
    target: int
    will_expand: bool
    will_pad: bool
    passthrough: bool


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@app.post("/info", response_model=InfoResponse)
async def info(
    file: UploadFile = File(...),
    threshold: int = Form(DEFAULT_THRESHOLD),
    target: int = Form(DEFAULT_TARGET_PAGES),
) -> InfoResponse:
    suffix = Path(file.filename or "book.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        pages = page_count(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return InfoResponse(
        pages=pages,
        threshold=threshold,
        target=target,
        will_expand=pages < threshold,
        will_pad=threshold <= pages < target,
        passthrough=pages >= target,
    )


@app.post("/expand")
async def expand(
    file: UploadFile = File(...),
    target: int = Form(DEFAULT_TARGET_PAGES),
    threshold: int = Form(DEFAULT_THRESHOLD),
):
    job_id = uuid.uuid4().hex[:12]
    job_dir = DATA_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    src_name = Path(file.filename or "input.pdf").name
    src = job_dir / src_name
    src.write_bytes(await file.read())
    out = job_dir / "expanded.pdf"
    report_path = job_dir / "report.json"

    try:
        report = expand_pdf(
            src,
            out,
            target_pages=target,
            threshold=threshold,
            report_path=report_path,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "job_id": job_id,
        "report": report.to_dict(),
        "download_url": f"/download/{job_id}",
        "report_url": f"/report/{job_id}",
    }


@app.get("/download/{job_id}")
def download(job_id: str):
    path = DATA_DIR / job_id / "expanded.pdf"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Job not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename="sheetfit-expanded.pdf",
    )


@app.get("/report/{job_id}")
def report(job_id: str):
    path = DATA_DIR / job_id / "report.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(path, media_type="application/json")
