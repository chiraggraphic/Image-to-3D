"""Image -> detailed 3D model, powered by Meshy's official API.

The API key stays on the server. The browser talks only to this app.
Run:  uvicorn main:app --reload
"""
import base64
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

API_KEY = os.getenv("MESHY_API_KEY", "")
TARGET_FORMATS = [f.strip() for f in os.getenv("TARGET_FORMATS", "").split(",") if f.strip()]
ENDPOINT = "https://api.meshy.ai/openapi/v1/image-to-3d"
ALLOWED_TYPES = {"image/png", "image/jpeg"}
MAX_BYTES = 10 * 1024 * 1024
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Image to 3D")


def auth() -> dict:
    if not API_KEY:
        raise HTTPException(500, "MESHY_API_KEY is not set. Copy .env.example to .env and add your key.")
    return {"Authorization": f"Bearer {API_KEY}"}


@app.post("/api/convert")
async def convert(
    image: UploadFile = File(...),
    ai_model: str = Form("latest"),
    texture: bool = Form(True),
    pbr: bool = Form(True),
):
    """Start a conversion. Returns {"task_id": "..."}."""
    if image.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Upload a PNG or JPG image.")
    data = await image.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(400, "Image is larger than 10 MB.")
    if ai_model not in {"latest", "meshy-6", "meshy-5"}:
        raise HTTPException(400, "Unknown model version.")

    data_uri = f"data:{image.content_type};base64,{base64.b64encode(data).decode()}"
    payload = {
        "image_url": data_uri,
        "ai_model": ai_model,
        "model_type": "standard",  # full-detail mesh
        "should_texture": texture,
        "enable_pbr": pbr and texture,
    }
    if TARGET_FORMATS:
        payload["target_formats"] = TARGET_FORMATS

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(ENDPOINT, json=payload, headers=auth())
    if r.status_code >= 400:
        raise HTTPException(r.status_code, f"Meshy error: {r.text}")
    return {"task_id": r.json()["result"]}


@app.get("/api/task/{task_id}")
async def task(task_id: str):
    """Poll a task. Status is PENDING, IN_PROGRESS, SUCCEEDED, FAILED or CANCELED."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{ENDPOINT}/{task_id}", headers=auth())
    if r.status_code >= 400:
        raise HTTPException(r.status_code, f"Meshy error: {r.text}")
    t = r.json()
    return {
        "status": t.get("status"),
        "progress": t.get("progress", 0),
        "model_urls": t.get("model_urls") or {},
        "thumbnail_url": t.get("thumbnail_url"),
        "error": (t.get("task_error") or {}).get("message"),
    }


@app.get("/api/download")
async def download(url: str, name: str = "model"):
    """Stream a finished file through this server (avoids browser CORS limits)."""
    host = urlparse(url).hostname or ""
    if urlparse(url).scheme != "https" or not (host == "meshy.ai" or host.endswith(".meshy.ai")):
        raise HTTPException(400, "Only Meshy asset URLs can be downloaded.")
    safe = "".join(c for c in name if c.isalnum() or c in "._-") or "model"

    client = httpx.AsyncClient(timeout=120)
    upstream = await client.send(client.build_request("GET", url), stream=True)
    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(upstream.status_code, "Could not fetch the file.")

    async def body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        body(),
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
