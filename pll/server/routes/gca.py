from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from schemas import (
    GCAInitResponse, GCACheckpointCreate, GCAHandoffResponse,
    GCASummary, GCAVaultEntryOut, PLLMessage, AgentSessionOut,
)
from services.gca_orchestrator import GCAOrchestrator

router = APIRouter(prefix="/api/gca", tags=["GCA Orchestrator"])

@router.post("/init/{project_id}", response_model=GCAInitResponse)
async def init_gca(project_id: int, objective: str = "", db: AsyncSession = Depends(get_db)):
    """Start a GCA cycle: creates Primary + Shadow agents."""
    orch = GCAOrchestrator(db)
    try:
        primary, shadow = await orch.init_cycle(project_id, objective)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return GCAInitResponse(
        project_id=project_id,
        primary_session=AgentSessionOut.model_validate(primary),
        shadow_session=AgentSessionOut.model_validate(shadow),
    )

@router.post("/checkpoint", response_model=GCAVaultEntryOut)
async def checkpoint(data: GCACheckpointCreate, db: AsyncSession = Depends(get_db)):
    """Save agent state checkpoint to the vault."""
    orch = GCAOrchestrator(db)
    try:
        entry = await orch.checkpoint(
            data.project_id, data.session_id, data.key, data.content, data.current_state
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    return GCAVaultEntryOut.model_validate(entry)

@router.post("/next-generation/{project_id}", response_model=GCAHandoffResponse)
async def next_generation(project_id: int, db: AsyncSession = Depends(get_db)):
    """
    Perform agent handoff:
    Primary -> dead, Shadow -> Primary, new Shadow created.
    """
    orch = GCAOrchestrator(db)
    try:
        old_primary, new_primary, new_shadow = await orch.handoff(project_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return GCAHandoffResponse(
        old_primary=AgentSessionOut.model_validate(old_primary),
        new_primary=AgentSessionOut.model_validate(new_primary),
        new_shadow=AgentSessionOut.model_validate(new_shadow),
        vault_summary=f"Handoff to generation {new_primary.generation} complete. Vault entries written.",
    )

@router.get("/vault/{project_id}", response_model=list[GCAVaultEntryOut])
async def get_vault(project_id: int, db: AsyncSession = Depends(get_db)):
    """Read all vault entries for a project."""
    orch = GCAOrchestrator(db)
    try:
        entries = await orch.get_vault(project_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return [GCAVaultEntryOut.model_validate(e) for e in entries]

@router.get("/status/{project_id}", response_model=GCASummary)
async def get_gca_status(project_id: int, db: AsyncSession = Depends(get_db)):
    """Get current GCA lifecycle status."""
    orch = GCAOrchestrator(db)
    try:
        status = await orch.get_status(project_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return GCASummary(
        project_id=status["project_id"],
        total_generations=status["total_generations"],
        current_primary=AgentSessionOut.model_validate(status["current_primary"]) if status["current_primary"] else None,
        current_shadow=AgentSessionOut.model_validate(status["current_shadow"]) if status["current_shadow"] else None,
        vault_entries_count=status["vault_entries_count"],
    )

@router.post("/wrap-message")
async def wrap_pll_message(msg: PLLMessage):
    """Wrap a message in PLL format for inter-agent communication."""
    orch = GCAOrchestrator(None)  # db not needed for wrapping
    pll = await orch.wrap_message(
        msg.sender, msg.receiver, msg.message_type, msg.generation, msg.payload
    )
    return {"pll_message": pll}

@router.post("/handoff", response_model=GCAHandoffResponse)
async def handoff(project_id: int, db: AsyncSession = Depends(get_db)):
    """Alias for next-generation. Perform agent handoff."""
    return await next_generation(project_id, db)
