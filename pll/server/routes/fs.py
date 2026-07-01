"""
Filesystem API — allows agents to read, write, copy, move, delete files on disk.

All operations are scoped to the project directory for safety.
"""
import os
import re
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/fs", tags=["Filesystem"])

# Base directory for all FS operations (project root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # pll/


class ReadRequest(BaseModel):
    path: str

class WriteRequest(BaseModel):
    path: str
    content: str

class RenameRequest(BaseModel):
    old_path: str
    new_path: str

class CopyRequest(BaseModel):
    source: str
    dest: str

class DeleteRequest(BaseModel):
    path: str
    recursive: bool = False

class ListRequest(BaseModel):
    path: str = "."

class MkdirRequest(BaseModel):
    path: str


def _resolve(path: str) -> Path:
    """Resolve a path relative to BASE_DIR, with safety checks."""
    full = (BASE_DIR / path).resolve()
    if not str(full).startswith(str(BASE_DIR)):
        raise HTTPException(403, "Path outside project directory")
    return full


@router.post("/read")
async def fs_read(req: ReadRequest):
    fp = _resolve(req.path)
    if not fp.exists():
        raise HTTPException(404, f"Not found: {req.path}")
    if not fp.is_file():
        raise HTTPException(400, f"Not a file: {req.path}")
    return {"path": req.path, "content": fp.read_text(encoding="utf-8")}


@router.post("/write")
async def fs_write(req: WriteRequest):
    fp = _resolve(req.path)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(req.content, encoding="utf-8")
    return {"path": req.path, "size": len(req.content)}


@router.post("/rename")
async def fs_rename(req: RenameRequest):
    old = _resolve(req.old_path)
    new = _resolve(req.new_path)
    if not old.exists():
        raise HTTPException(404, f"Not found: {req.old_path}")
    new.parent.mkdir(parents=True, exist_ok=True)
    old.rename(new)
    return {"from": req.old_path, "to": req.new_path}


@router.post("/copy")
async def fs_copy(req: CopyRequest):
    src = _resolve(req.source)
    dst = _resolve(req.dest)
    if not src.exists():
        raise HTTPException(404, f"Not found: {req.source}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    return {"from": req.source, "to": req.dest}


@router.post("/delete")
async def fs_delete(req: DeleteRequest):
    fp = _resolve(req.path)
    if not fp.exists():
        raise HTTPException(404, f"Not found: {req.path}")
    if fp.is_file():
        fp.unlink()
    elif req.recursive:
        shutil.rmtree(fp)
    else:
        raise HTTPException(400, "Use recursive=true to delete directories")
    return {"deleted": req.path}


@router.post("/list")
async def fs_list(req: ListRequest):
    fp = _resolve(req.path)
    if not fp.exists():
        raise HTTPException(404, f"Not found: {req.path}")
    if not fp.is_dir():
        raise HTTPException(400, f"Not a directory: {req.path}")
    entries = []
    for child in sorted(fp.iterdir()):
        entries.append({
            "name": child.name,
            "path": str(child.relative_to(BASE_DIR)),
            "type": "dir" if child.is_dir() else "file",
            "size": child.stat().st_size if child.is_file() else 0,
        })
    return {"path": req.path, "entries": entries}


@router.post("/mkdir")
async def fs_mkdir(req: MkdirRequest):
    fp = _resolve(req.path)
    fp.mkdir(parents=True, exist_ok=True)
    return {"created": req.path}


@router.post("/exists")
async def fs_exists(path: str):
    fp = _resolve(path)
    return {"path": path, "exists": fp.exists(), "type": "dir" if fp.is_dir() else "file" if fp.is_file() else None}


class GrepRequest(BaseModel):
    pattern: str
    path: str = "."
    include: str = ""  # file glob filter, e.g. "*.py"

class GlobRequest(BaseModel):
    pattern: str
    path: str = "."


@router.post("/grep")
async def fs_grep(req: GrepRequest):
    """Search file contents with regex."""
    root = _resolve(req.path)
    if not root.is_dir():
        raise HTTPException(400, f"Not a directory: {req.path}")
    try:
        regex = re.compile(req.pattern, re.IGNORECASE)
    except re.error as e:
        raise HTTPException(400, f"Invalid regex: {e}")
    matches = []
    for fpath in root.rglob("*"):
        if not fpath.is_file():
            continue
        if req.include and not fpath.match(req.include):
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.split("\n"), 1):
            if regex.search(line):
                rel = str(fpath.relative_to(BASE_DIR))
                matches.append({
                    "path": rel,
                    "line": i,
                    "content": line.strip()[:200],
                })
    return {"path": req.path, "pattern": req.pattern, "matches": matches, "count": len(matches)}


@router.post("/glob")
async def fs_glob(req: GlobRequest):
    """List files matching a glob pattern."""
    root = _resolve(req.path)
    if not root.is_dir():
        raise HTTPException(400, f"Not a directory: {req.path}")
    files = []
    for fpath in sorted(root.rglob(req.pattern)):
        rel = str(fpath.relative_to(BASE_DIR))
        files.append({
            "path": rel,
            "name": fpath.name,
            "type": "dir" if fpath.is_dir() else "file",
            "size": fpath.stat().st_size if fpath.is_file() else 0,
        })
    return {"path": req.path, "pattern": req.pattern, "files": files, "count": len(files)}
