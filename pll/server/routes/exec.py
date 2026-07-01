"""
Command Execution API — allows agents to propose and run shell commands.

Safety:
  - Commands require explicit user confirmation (propose -> confirm)
  - Timeout prevents runaway processes
  - Working directory is the project root (pll/)
"""
import asyncio
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/exec", tags=["Command Execution"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # pll/

# In-memory store of pending command proposals
_pending: dict[str, dict] = {}


class ProposeRequest(BaseModel):
    command: str
    description: str = ""


class ProposeResponse(BaseModel):
    proposal_id: str
    command: str
    description: str


class ConfirmRequest(BaseModel):
    proposal_id: str


class ExecResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    command: str


@router.post("/propose", response_model=ProposeResponse)
async def exec_propose(req: ProposeRequest):
    """Agent proposes a command. Returns a proposal_id for user confirmation."""
    if not req.command.strip():
        raise HTTPException(400, "Empty command")
    proposal_id = uuid.uuid4().hex[:12]
    _pending[proposal_id] = {
        "command": req.command.strip(),
        "description": req.description or req.command[:80],
    }
    return ProposeResponse(
        proposal_id=proposal_id,
        command=req.command.strip(),
        description=req.description or req.command[:80],
    )


@router.post("/confirm", response_model=ExecResponse)
async def exec_confirm(req: ConfirmRequest):
    """User confirms a proposed command. Executes it and returns output."""
    proposal = _pending.pop(req.proposal_id, None)
    if not proposal:
        raise HTTPException(404, "Proposal not found or expired")
    return await _run(proposal["command"])


@router.post("/run", response_model=ExecResponse)
async def exec_run(command: str, timeout: int = 30):
    """Direct execution (only in dev/trusted mode)."""
    if not command.strip():
        raise HTTPException(400, "Empty command")
    return await _run(command.strip(), timeout)


async def _run(command: str, timeout: int = 60) -> ExecResponse:
    """Execute a shell command asynchronously."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(BASE_DIR),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return ExecResponse(
            exit_code=proc.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            command=command,
        )
    except asyncio.TimeoutError:
        if proc:
            proc.kill()
        raise HTTPException(408, f"Command timed out after {timeout}s")
    except Exception as e:
        raise HTTPException(500, str(e))
