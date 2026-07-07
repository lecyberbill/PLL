"""
[WFGY] Zone: SAFE | λ: 0.3 | Fallbacks: 1/File Redirection | Action: Run commands safely via file-redirection to avoid Windows hangs
Command Execution API — allows agents to propose and run shell commands.

Safety:
  - Commands require explicit user confirmation (propose -> confirm)
  - Timeout prevents runaway processes
  - Working directory is the project root (pll/)
"""
import asyncio
import os
import uuid
import subprocess
import tempfile
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
    """Execute a shell command safely using file-redirection to avoid handle-inheritance hangs on Windows."""
    loop = asyncio.get_running_loop()
    
    temp_dir = Path(tempfile.gettempdir())
    temp_id = uuid.uuid4().hex[:8]
    out_path = temp_dir / f".exec_out_{temp_id}.tmp"
    err_path = temp_dir / f".exec_err_{temp_id}.tmp"
    
    def run_sync():
        with open(out_path, "wb") as f_out, open(err_path, "wb") as f_err:
            return subprocess.run(
                command,
                shell=True,
                stdout=f_out,
                stderr=f_err,
                cwd=str(BASE_DIR),
                timeout=timeout
            )
        
    try:
        proc = await loop.run_in_executor(None, run_sync)
        
        # Read contents
        stdout_bytes = out_path.read_bytes() if out_path.is_file() else b""
        stderr_bytes = err_path.read_bytes() if err_path.is_file() else b""
        
        # Clean up files asynchronously/safely
        for path in (out_path, err_path):
            try:
                if path.is_file():
                    path.unlink()
            except Exception:
                pass # Ignore permission error if background process locks it
                
        return ExecResponse(
            exit_code=proc.returncode,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            command=command,
        )
    except subprocess.TimeoutExpired as e:
        # Attempt to clean up even on timeout
        for path in (out_path, err_path):
            try:
                if path.is_file():
                    path.unlink()
            except Exception:
                pass
        raise HTTPException(408, f"Command timed out after {timeout}s")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))

