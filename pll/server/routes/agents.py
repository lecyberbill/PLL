from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import AgentSession
from schemas import (
    AgentSessionCreate, AgentSessionStatusUpdate, AgentSessionOut,
)
from datetime import datetime, timezone

router = APIRouter(prefix="/api/agents", tags=["Agent Sessions"])

@router.get("", response_model=list[AgentSessionOut])
async def list_sessions(project_id: int | None = None, db: AsyncSession = Depends(get_db)):
    query = select(AgentSession).order_by(AgentSession.created_at.desc())
    if project_id is not None:
        query = query.where(AgentSession.project_id == project_id)
    result = await db.execute(query)
    return result.scalars().all()

@router.post("", response_model=AgentSessionOut, status_code=201)
async def create_session(data: AgentSessionCreate, db: AsyncSession = Depends(get_db)):
    session = AgentSession(
        project_id=data.project_id,
        generation=data.generation,
        agent_type=data.agent_type,
        objective=data.objective,
        current_state=data.current_state,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

@router.get("/{session_id}", response_model=AgentSessionOut)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    session = await db.get(AgentSession, session_id)
    if not session:
        raise HTTPException(404, "Agent session not found")
    return session

@router.put("/{session_id}/status", response_model=AgentSessionOut)
async def update_session_status(session_id: int, data: AgentSessionStatusUpdate, db: AsyncSession = Depends(get_db)):
    session = await db.get(AgentSession, session_id)
    if not session:
        raise HTTPException(404, "Agent session not found")
    valid_statuses = {"born", "working", "documenting", "completed", "dead"}
    if data.status not in valid_statuses:
        raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}")
    session.status = data.status
    if data.current_state is not None:
        session.current_state = data.current_state
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return session
