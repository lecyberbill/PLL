"""
Git integration routes.

Provides status, diff, add, commit, push, log operations
for project directories. Uses gitpython or shell git.
"""
import os
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import Project
from config import PROJECTS_DIR

router = APIRouter(prefix="/api/git", tags=["Git"])


def _git_dir(project) -> Path:
    if project.disk_path:
        return Path(project.disk_path).resolve()
    base = Path(PROJECTS_DIR) if isinstance(PROJECTS_DIR, str) else PROJECTS_DIR
    return base / str(project.id)


def _git(*args, cwd: Path) -> dict:
    """Run a git command and return {"ok": bool, "out": str, "err": str}."""
    try:
        r = subprocess.run(
            ["git"] + list(args),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {"ok": r.returncode == 0, "out": r.stdout.strip(), "err": r.stderr.strip()}
    except FileNotFoundError:
        return {"ok": False, "out": "", "err": "git not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "out": "", "err": "git command timed out"}


# --- Schemas ---

class GitStatusResponse(BaseModel):
    branch: str = ""
    is_repo: bool = False
    ahead: int = 0
    behind: int = 0
    staged: list[str] = []
    modified: list[str] = []
    untracked: list[str] = []
    deleted: list[str] = []
    commit_count: int = 0


class GitLogEntry(BaseModel):
    hash: str
    author: str
    date: str
    message: str


class GitCommitRequest(BaseModel):
    message: str = ""
    auto_message: bool = False


# --- Helpers ---

async def _get_project(project_id: int, db: AsyncSession) -> Project:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _ensure_repo(git_dir: Path):
    """Init git repo if not already one."""
    if not (git_dir / ".git").exists():
        _git("init", cwd=git_dir)
        _git("config", "user.name", "PLL Agent", cwd=git_dir)
        _git("config", "user.email", "agent@pll.dev", cwd=git_dir)


def _parse_status(out: str) -> tuple[list[str], list[str], list[str], list[str]]:
    staged, modified, untracked, deleted = [], [], [], []
    for line in out.split("\n"):
        if not line.strip():
            continue
        code = line[:2]
        path = line[3:].strip()
        if code == "??":
            untracked.append(path)
        elif code.startswith("M"):
            modified.append(path)
        elif code.startswith("A") or code.startswith(" "):
            staged.append(path)
        elif code.startswith("D"):
            deleted.append(path)
    return staged, modified, untracked, deleted


# --- Routes ---

@router.get("/{project_id}/status", response_model=GitStatusResponse)
async def git_status(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        return GitStatusResponse()
    git_dir = _git_dir(project)
    if not (git_dir / ".git").exists():
        return GitStatusResponse(is_repo=False)

    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=git_dir)
    status = _git("status", "--porcelain", cwd=git_dir)
    commit_count = _git("rev-list", "--count", "HEAD", cwd=git_dir)

    staged, modified, untracked, deleted = _parse_status(status.get("out", ""))

    # Count ahead/behind
    ahead = behind = 0
    remote = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", cwd=git_dir)
    if remote["ok"]:
        rev = _git("rev-list", "--left-right", "--count", "HEAD...@{upstream}", cwd=git_dir)
        if rev["ok"]:
            parts = rev["out"].split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])

    return GitStatusResponse(
        branch=branch.get("out", "main"),
        is_repo=True,
        ahead=ahead,
        behind=behind,
        staged=staged,
        modified=modified,
        untracked=untracked,
        deleted=deleted,
        commit_count=int(commit_count.get("out", "0") or "0"),
    )


@router.get("/{project_id}/log", response_model=list[GitLogEntry])
async def git_log(project_id: int, max_count: int = Query(10, le=50), db: AsyncSession = Depends(get_db)):
    project = await _get_project(project_id, db)
    git_dir = _git_dir(project)
    if not (git_dir / ".git").exists():
        return []
    r = _git("log", f"--max-count={max_count}", "--format=%H||%an||%ai||%s", cwd=git_dir)
    if not r["ok"]:
        return []
    entries = []
    for line in r["out"].split("\n"):
        if "||" in line:
            parts = line.split("||", 3)
            entries.append(GitLogEntry(
                hash=parts[0][:8], author=parts[1], date=parts[2], message=parts[3],
            ))
    return entries


@router.post("/{project_id}/commit")
async def git_commit(project_id: int, req: GitCommitRequest, db: AsyncSession = Depends(get_db)):
    project = await _get_project(project_id, db)
    git_dir = _git_dir(project)
    if not (git_dir / ".git").exists():
        raise HTTPException(400, "Not a git repository")

    # Stage all changes
    _git("add", "-A", cwd=git_dir)

    # Generate commit message via LLM if auto_message
    message = req.message
    if req.auto_message or not message:
        diff = _git("diff", "--cached", cwd=git_dir)
        if diff["ok"] and diff["out"]:
            from services.llm_proxy import chat_completion
            llm = await chat_completion(
                messages=[{"role": "user", "content": (
                    f"Write a concise git commit message for these changes:\n{diff['out'][:2000]}"
                )}],
                system_prompt="Write a short, descriptive commit message (max 72 chars first line). "
                              "Output ONLY the message, no explanation.",
                temperature=0.1,
            )
            message = llm["response"].strip().split("\n")[0][:200]
        else:
            message = message or "Auto-commit"

    r = _git("commit", "-m", message, cwd=git_dir)
    return {"ok": r["ok"], "message": message, "out": r["out"], "err": r["err"]}


@router.post("/{project_id}/push")
async def git_push(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await _get_project(project_id, db)
    git_dir = _git_dir(project)
    r = _git("push", cwd=git_dir)
    return {"ok": r["ok"], "out": r["out"], "err": r["err"]}


@router.post("/{project_id}/pull")
async def git_pull(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await _get_project(project_id, db)
    git_dir = _git_dir(project)
    r = _git("pull", "--ff-only", cwd=git_dir)
    return {"ok": r["ok"], "out": r["out"], "err": r["err"]}

@router.post("/{project_id}/init")
async def git_init_repo(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await _get_project(project_id, db)
    git_dir = _git_dir(project)
    git_dir.mkdir(parents=True, exist_ok=True)
    if (git_dir / ".git").exists():
        return {"ok": True, "out": "Already a git repository"}
    _ensure_repo(git_dir)
    return {"ok": True, "out": "Git repository initialized"}


class GitRemoteRequest(BaseModel):
    url: str
    branch: str = "main"


@router.post("/{project_id}/remote")
async def git_set_remote(project_id: int, req: GitRemoteRequest, db: AsyncSession = Depends(get_db)):
    project = await _get_project(project_id, db)
    git_dir = _git_dir(project)
    if not (git_dir / ".git").exists():
        raise HTTPException(400, "Not a git repository. Init first.")
    # Remove old origin if exists
    _git("remote", "remove", "origin", cwd=git_dir)
    r = _git("remote", "add", "origin", req.url, cwd=git_dir)
    if not r["ok"]:
        raise HTTPException(400, r["err"])
    _git("branch", "-M", req.branch, cwd=git_dir)
    return {"ok": True, "out": f"Remote origin set to {req.url} on branch {req.branch}"}


@router.post("/{project_id}/clone")
async def git_clone_repo(project_id: int, req: GitRemoteRequest, db: AsyncSession = Depends(get_db)):
    project = await _get_project(project_id, db)
    git_dir = _git_dir(project)
    if git_dir.exists() and any(git_dir.iterdir()):
        raise HTTPException(400, "Project directory is not empty. Cannot clone into a non-empty project.")
    git_dir.mkdir(parents=True, exist_ok=True)
    r = _git("clone", req.url, ".", cwd=git_dir)
    if not r["ok"]:
        raise HTTPException(400, r["err"])
    return {"ok": True, "out": f"Cloned {req.url}"}
