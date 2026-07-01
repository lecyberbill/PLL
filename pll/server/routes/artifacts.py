import os
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import Project, Artifact
from schemas import (
    ProjectCreate, ProjectUpdate, ProjectOut,
    ArtifactCreate, ArtifactUpdate, ArtifactOut,
)
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter(prefix="/api/projects", tags=["Artifacts & Projects"])

def _disk_files(pdir: Path) -> list[dict]:
    if not pdir.exists():
        return []
    return _build_tree(pdir, pdir)

def _build_tree(root: Path, current: Path) -> list[dict]:
    _skip_names = {".venv", "__pycache__", "node_modules", ".git", "target", ".pytest_cache", ".mypy_cache", ".rnd"}
    entries = []
    for child in sorted(current.iterdir()):
        if child.name in _skip_names:
            continue
        if child.is_file():
            entries.append({
                "name": child.name,
                "path": str(child.relative_to(root)),
                "type": "file",
                "size": child.stat().st_size,
            })
        elif child.is_dir():
            children = _build_tree(root, child)
            entries.append({
                "name": child.name,
                "path": str(child.relative_to(root)),
                "type": "dir",
                "children": children,
            })
    return entries

# ---- Projects ----

@router.get("", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.updated_at.desc()))
    return result.scalars().all()

@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(name=data.name, description=data.description, disk_path=data.disk_path)
    if data.disk_path:
        pdir = Path(data.disk_path).resolve()
        pdir.mkdir(parents=True, exist_ok=True)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project

@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project

@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, data: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if data.name is not None:
        project.name = data.name
    if data.description is not None:
        project.description = data.description
    if data.disk_path is not None:
        old_pdir = Path(project.disk_path).resolve() if project.disk_path else None
        project.disk_path = data.disk_path
        if data.disk_path:
            new_pdir = Path(data.disk_path).resolve()
            new_pdir.mkdir(parents=True, exist_ok=True)
    project.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(project)
    return project

@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, keep_files: bool = True, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not keep_files and project.disk_path:
        pdir = Path(project.disk_path).resolve()
        if pdir.exists():
            shutil.rmtree(str(pdir))
    await db.delete(project)
    await db.commit()

# ---- Files (disk mode OR DB mode) ----

def _is_disk_mode(project: Project) -> bool:
    return bool(project.disk_path)

@router.get("/{project_id}/files")
async def list_files(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if _is_disk_mode(project):
        return _disk_files(Path(project.disk_path).resolve())
    result = await db.execute(
        select(Artifact).where(Artifact.project_id == project_id).order_by(Artifact.path)
    )
    artifacts = result.scalars().all()
    flat = [{"path": a.path, "content": a.content, "mode": "db", "id": a.id} for a in artifacts]
    return _build_tree_from_paths(flat)

def _build_tree_from_paths(flat: list[dict]) -> list[dict]:
    """Convert flat list of {path, ...} into a tree structure with nested dirs/files."""
    tree = {}
    for item in flat:
        parts = item["path"].replace("\\", "/").split("/")
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                current[part] = item | {"type": "file", "name": part}
            else:
                if part not in current:
                    current[part] = {"type": "dir", "name": part, "children": {}}
                current = current[part]["children"]
    return _tree_to_list(tree)

def _tree_to_list(tree: dict) -> list[dict]:
    result = []
    for key in sorted(tree.keys()):
        node = tree[key]
        if node["type"] == "dir":
            node["children"] = _tree_to_list(node["children"])
            result.append(node)
        else:
            result.append(node)
    return result

@router.post("/{project_id}/files", response_model=dict, status_code=201)
async def create_or_update_file(project_id: int, data: ArtifactCreate, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    content = data.content or ""
    if _is_disk_mode(project):
        pdir = Path(project.disk_path).resolve()
        fpath = pdir / data.path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
        return {"path": data.path, "size": len(content), "mode": "disk"}
    result = await db.execute(
        select(Artifact).where(Artifact.project_id == project_id, Artifact.path == data.path)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.content = content
        existing.updated_at = datetime.now(timezone.utc)
        artifact = existing
    else:
        artifact = Artifact(project_id=project_id, path=data.path, content=content)
        db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return {"path": artifact.path, "size": len(artifact.content), "mode": "db", "id": artifact.id}

@router.get("/{project_id}/files/{path:path}")
async def get_file(project_id: int, path: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if _is_disk_mode(project):
        fpath = Path(project.disk_path).resolve() / path
        if not fpath.exists() or not fpath.is_file():
            raise HTTPException(404, "File not found")
        try:
            content = fpath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            return {"path": path, "content": "", "mode": "disk", "size": fpath.stat().st_size, "binary": True}
        return {"path": path, "content": content, "mode": "disk", "size": len(content)}
    result = await db.execute(
        select(Artifact).where(Artifact.project_id == project_id, Artifact.path == path)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(404, "File not found")
    return {"path": artifact.path, "content": artifact.content, "mode": "db", "size": len(artifact.content)}

@router.put("/{project_id}/files/rename", status_code=200)
async def rename_file(project_id: int, old_path: str = Query(...), new_path: str = Query(...), db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if _is_disk_mode(project):
        pdir = Path(project.disk_path).resolve()
        old_fp = pdir / old_path
        new_fp = pdir / new_path
        if not old_fp.exists():
            raise HTTPException(404, "Source file not found")
        if new_fp.exists():
            raise HTTPException(409, "Target file already exists")
        new_fp.parent.mkdir(parents=True, exist_ok=True)
        old_fp.rename(new_fp)
        return {"old_path": old_path, "new_path": new_path}
    result = await db.execute(
        select(Artifact).where(Artifact.project_id == project_id, Artifact.path == old_path)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(404, "File not found")
    existing = await db.execute(
        select(Artifact).where(Artifact.project_id == project_id, Artifact.path == new_path)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Target file already exists")
    artifact.path = new_path
    artifact.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(artifact)
    return {"old_path": old_path, "new_path": new_path}

@router.delete("/{project_id}/files/{path:path}", status_code=204)
async def delete_file(project_id: int, path: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if _is_disk_mode(project):
        fpath = Path(project.disk_path).resolve() / path
        if fpath.exists():
            fpath.unlink()
        return
    result = await db.execute(
        select(Artifact).where(Artifact.project_id == project_id, Artifact.path == path)
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(404, "File not found")
    await db.delete(artifact)
    await db.commit()

@router.post("/{project_id}/sync-from-disk", response_model=list[str])
async def sync_from_disk(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not _is_disk_mode(project):
        raise HTTPException(400, "Not a disk-mode project")
    pdir = Path(project.disk_path).resolve()
    if not pdir.exists():
        raise HTTPException(404, "Directory not found")
    synced = []
    for fpath in sorted(pdir.rglob("*")):
        if fpath.is_file():
            rel = str(fpath.relative_to(pdir))
            content = fpath.read_text(encoding="utf-8", errors="replace")
            result = await db.execute(
                select(Artifact).where(Artifact.project_id == project_id, Artifact.path == rel)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.content = content
            else:
                db.add(Artifact(project_id=project_id, path=rel, content=content))
            synced.append(rel)
    await db.commit()
    return synced
