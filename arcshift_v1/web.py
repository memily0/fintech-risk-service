"""Explicit static allowlist, never a file browser over the project tree."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


router = APIRouter(include_in_schema=False)
STATIC = Path(__file__).resolve().parent / "static"
ASSETS = {
    "app.css": "text/css",
    "app.js": "text/javascript",
    "lucide.min.js": "text/javascript",
}


@router.get("/")
def workbench():
    return FileResponse(STATIC / "index.html", media_type="text/html")


@router.get("/assets/{name}")
def asset(name: str):
    if name not in ASSETS:
        raise HTTPException(404)
    return FileResponse(STATIC / name, media_type=ASSETS[name])
