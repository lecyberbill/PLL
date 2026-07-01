from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from database import get_db
from models import Project
from services.agent_react import AgentReAct
from services.agent_coordinator import AgentCoordinator

router = APIRouter(prefix="/api/agentic", tags=["Agentic ReAct"])


class ReactRequest(BaseModel):
    project_id: int
    message: str
    backend: str = ""


class ReactResponse(BaseModel):
    answer: str = ""
    steps: list = []
    code: str = ""
    file_path: str = ""
    agent_info: dict = {}


@router.post("/react", response_model=ReactResponse)
async def agentic_react(req: ReactRequest, db: AsyncSession = Depends(get_db)):
    """ReAct loop: agent uses tools (grep, glob, read, write, edit) in a chain until done."""
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Build project context
    from services.agent_brain import AgentBrain
    brain = AgentBrain(db)
    context = await brain._build_context(req.project_id)
    context_str = (
        f"## Project: {project.name}\n"
        f"Description: {project.description or ''}\n"
        f"Files: {context['files_summary']}\n"
        f"Recent vault: {context['vault_summary']}"
    )

    agent = AgentReAct(req.project_id, req.backend)
    result = await agent.run(req.message, context_str)

    return ReactResponse(
        answer=result.get("answer", ""),
        steps=result.get("steps", []),
        code=result.get("code", ""),
        file_path=result.get("file_path", ""),
        agent_info={"steps": len(result.get("steps", [])), "mode": "react"},
    )


class OrchestrateRequest(BaseModel):
    project_id: int
    message: str
    backend: str = ""


@router.post("/orchestrate", response_model=ReactResponse)
async def agentic_orchestrate(req: OrchestrateRequest, db: AsyncSession = Depends(get_db)):
    """Multi-agent orchestration: planner breaks task → workers execute → coordinator merges."""
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    from services.agent_brain import AgentBrain
    brain = AgentBrain(db)
    context = await brain._build_context(req.project_id)
    context_str = (
        f"## Project: {project.name}\n"
        f"Files: {context['files_summary']}"
    )

    coord = AgentCoordinator(req.project_id, req.backend)
    result = await coord.orchestrate(req.message, context_str)

    return ReactResponse(
        answer=result.get("answer", ""),
        steps=[{"subtask": s["subtask"], "result": s["result"][:200]}
               for s in result.get("subtasks", [])],
        code=result.get("code", ""),
        file_path=result.get("file_path", ""),
        agent_info={"subtasks": len(result.get("subtasks", [])), "mode": "orchestrate"},
    )
