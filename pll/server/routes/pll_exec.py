"""
PLL Execution endpoint — compiles and runs PLL code via the Rust CLI.
"""
import subprocess
import tempfile
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/pll", tags=["PLL Execution"])

# Find the pll-cli binary
_here = Path(__file__).resolve().parent.parent  # server/
_binary = None
for candidate in [
    _here.parent / "target" / "release" / "pll-cli.exe",
    _here.parent / "target" / "release" / "pll-cli",
    _here.parent / "pll-cli.exe",
    _here.parent / "pll-cli",
]:
    if candidate.exists():
        _binary = str(candidate.resolve())
        break


class ExecRequest(BaseModel):
    code: str
    args: list[str] = []


class ExecResponse(BaseModel):
    ok: bool = False
    output: str = ""
    error: str = ""


@router.post("/exec", response_model=ExecResponse)
async def pll_exec(req: ExecRequest):
    if not _binary:
        return ExecResponse(ok=False, error="pll-cli binary not found")

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pll", delete=False, encoding="utf-8") as f:
            f.write(req.code)
            tmp_path = f.name
        result = subprocess.run(
            [_binary, "run", "--bc", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        os.unlink(tmp_path)
        return ExecResponse(
            ok=result.returncode == 0,
            output=result.stdout.strip(),
            error=result.stderr.strip(),
        )
    except subprocess.TimeoutExpired:
        return ExecResponse(ok=False, error="Execution timed out (30s)")
    except FileNotFoundError:
        return ExecResponse(ok=False, error="pll-cli binary not found")
    except Exception as e:
        return ExecResponse(ok=False, error=str(e))
