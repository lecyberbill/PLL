"""
[WFGY] Zone: SAFE | λ: 0.5 | Fallbacks: None | Action: Implement unified Chef d'Orchestre (Orchestrator Agent) flow
"""
import re
import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timezone
from database import get_db
from models import Project as ProjectModel, Artifact, Conversation, AgentSession
from schemas import AgentSessionOut, ArtifactOut
from services.agent_brain import AgentBrain

router = APIRouter(prefix="/api/agentic", tags=["Agentic IDE"])


class AskRequest(BaseModel):
    project_id: int
    message: str
    backend: str = ""  # "deepseek" | "lmstudio" | "" (auto)
    target_file: str = ""  # specific file to edit (auto-detected if empty)


class AskResponse(BaseModel):
    code: str = ""
    file_path: str = ""
    explanation: str = ""
    files_modified: list[str] = []
    agent_info: dict = {}
    conversation: str = ""
    edit_mode: bool = False
    response: str = ""  # text response (for resume/explain mode)


@router.post("/ask", response_model=AskResponse)
async def agentic_ask(req: AskRequest, db: AsyncSession = Depends(get_db)):
    brain = AgentBrain(db)
    try:
        result = await brain.process_request(
            req.project_id, augmented_msg, backend=req.backend, target_file=req.target_file
        )
        if result.get("explanation"):
            return AskResponse(
                explanation=result["explanation"],
                agent_info=result.get("agent_info", {}),
                edit_mode=False,
                conversation=result["explanation"],
                response=result["explanation"],
            )
        verb = "edited" if result.get("edit_mode") else "generated"
        return AskResponse(
            code=result["code"],
            file_path=result["file_path"],
            files_modified=result["files_modified"],
            agent_info=result["agent_info"],
            edit_mode=result.get("edit_mode", False),
            conversation=f"Agent #{result['agent_info']['session_id']} "
                        f"(gen {result['agent_info']['generation']}) "
                        f"{verb} {result['file_path']}",
        )
    except (ValueError, ConnectionError, RuntimeError) as e:
        raise HTTPException(400, str(e))


class ChatRequest(BaseModel):
    project_id: int
    message: str


@router.post("/chat")
async def agentic_chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Conversational chat with RAG context from the vault."""
    brain = AgentBrain(db)
    try:
        response = await brain.chat(req.project_id, augmented_msg)
        return {"response": response}
    except (ValueError, ConnectionError, RuntimeError) as e:
        raise HTTPException(400, str(e))


# ---- Smart Auto-Router ----

class GoRequest(BaseModel):
    project_id: int
    message: str
    backend: str = ""


class GoResponse(BaseModel):
    answer: str = ""
    code: str = ""
    file_path: str = ""
    files_modified: list[str] = []
    explanation: str = ""
    question: str = ""
    steps: list = []
    mode: str = "simple"
    agent_info: dict = {}


async def _get_or_create_active_session(project_id: int, db: AsyncSession) -> AgentSession:
    # Look for active session
    res = await db.execute(
        select(AgentSession).where(
            AgentSession.project_id == project_id,
            AgentSession.status != "archived"
        ).order_by(AgentSession.created_at.desc()).limit(1)
    )
    session = res.scalar_one_or_none()
    if not session:
        session = AgentSession(project_id=project_id, status="active", agent_type="primary")
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return session


async def _check_and_rollover_session(project_id: int, session: AgentSession, db: AsyncSession) -> AgentSession:
    # Query all conversations in this session
    res = await db.execute(
        select(Conversation).where(
            Conversation.project_id == project_id,
            Conversation.session_id == session.id
        ).order_by(Conversation.created_at.asc())
    )
    msgs = res.scalars().all()
    total_len = sum(len(m.content) for m in msgs)
    
    # Rollover threshold: 20000 characters (approx. 5000 tokens)
    if total_len > 20000:
        # Archive current session
        session.status = "archived"
        session.updated_at = datetime.now(timezone.utc)
        await db.commit()
        
        # Create new session
        new_session = AgentSession(project_id=project_id, status="active", agent_type="primary")
        db.add(new_session)
        await db.commit()
        await db.refresh(new_session)
        
        # Add system notice to the new session
        notice = (
            "System Notice: The conversation history exceeded the context window limit. "
            "A new session has been automatically started to keep responses fast and clean."
        )
        db.add(Conversation(project_id=project_id, session_id=new_session.id, role="assistant", content=notice))
        await db.commit()
        return new_session
    return session


async def _run_orchestrator(message: str, project_name: str, file_names: list, backend: str) -> dict:
    from services.llm_proxy import chat_completion
    system_prompt = (
        "You are the Orchestrator (Chef d'Orchestre) of a software development agent.\n"
        "Your role is to understand the user's intent and decide whether to reply directly or delegate the task to your ReAct executor.\n\n"
        "When to REPLY DIRECTLY:\n"
        "- Greetings, conversation, questions asking for explanations, status checks, questions about how to run/start/use/play the project, and general discussions.\n"
        "- In this case, simply output the text response.\n\n"
        "When to DELEGATE:\n"
        "- Requests to create, edit, fix, delete files, write code, run shell commands, or test the project.\n"
        "- In this case, you MUST wrap the delegated technical instructions inside the following tag:\n"
        "  <delegate>Technical instructions for the ReAct executor</delegate>\n"
        "- Keep your thoughts outside the tag, but make sure the tag contains the precise instruction to execute.\n\n"
        "Multilingual Examples:\n"
        "- 'comment je lance le jeu ?' -> Thought: Question asking how to launch the game, no code change needed. Reply directly: 'Pour lancer le jeu, ouvrez index.html...'\n"
        "- 'wie starte ich das?' -> Thought: German question about launching the game. Reply directly: 'Um das Spiel zu starten...'\n"
        "- 'ajoute une fonction de log' -> Thought: Requests file modification. Delegate: <delegate>Add a logging function to the main JS file</delegate>\n"
        "- 'run the tests' -> Thought: Requests project verification. Delegate: <delegate>Run tests on the project</delegate>"
    )
    
    files_str = ", ".join(file_names) if file_names else "(empty)"
    prompt = (
        f"Project Name: {project_name}\n"
        f"Project Files: {files_str}\n"
        f"User Message: {message}"
    )
    
    result = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=system_prompt,
        temperature=0.1,
        backend=backend,
    )
    resp = result.get("response", "")
    import re
    match = re.search(r'<delegate>(.*?)</delegate>', resp, re.DOTALL)
    if match:
        return {"delegate": True, "instruction": match.group(1).strip(), "raw_response": resp}
    return {"delegate": False, "answer": resp}


@router.post("/go", response_model=GoResponse)
async def agentic_go(req: GoRequest, db: AsyncSession = Depends(get_db)):
    """Smart single entry point — orchestrates, then generates or replies."""
    project = await db.get(ProjectModel, req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Get active session and handle rollover if context exceeds limit
    active_session = await _get_or_create_active_session(req.project_id, db)
    active_session = await _check_and_rollover_session(req.project_id, active_session, db)

    # Load conversation history for the active session (last 10 messages)
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.project_id == req.project_id,
            Conversation.session_id == active_session.id
        ).order_by(Conversation.created_at.desc()).limit(10)
    )
    conv_msgs = list(reversed(conv_result.scalars().all()))
    conv_history = ""
    if conv_msgs:
        conv_history = "\n\n## Conversation précédente:\n" + "\n".join(
            f"{'Utilisateur' if c.role == 'user' else 'Assistant'}: {c.content}"
            for c in conv_msgs[-5:]
        )

    # Append history to the message
    augmented_msg = req.message + conv_history

    # Save user message linked to active session
    db.add(Conversation(
        project_id=req.project_id,
        session_id=active_session.id,
        role="user",
        content=req.message
    ))
    await db.commit()

    async def _respond(**kw):
        answer = kw.get("answer") or kw.get("explanation") or kw.get("question", "")
        if answer:
            db.add(Conversation(
                project_id=req.project_id,
                session_id=active_session.id,
                role="assistant",
                content=str(answer)
            ))
            await db.commit()
        return GoResponse(**kw)

    files_result = await db.execute(
        select(Artifact).where(Artifact.project_id == req.project_id)
    )
    files = files_result.scalars().all()
    file_names = [f.path for f in files]

    # Disk mode: also check actual filesystem
    has_files = len(files) > 0
    if not has_files and project.disk_path:
        from pathlib import Path
        pdir = Path(project.disk_path).resolve()
        if pdir.exists():
            skip_dirs = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache", "target"}
            disk_files = [
                f for f in pdir.rglob("*")
                if f.is_file() and not any(p in f.parts for p in skip_dirs)
            ]
            has_files = len(disk_files) > 0
            file_names = [str(f.relative_to(pdir)) for f in disk_files[:50]]

    # Call Orchestrator
    orchestration = await _run_orchestrator(augmented_msg, project.name, file_names, req.backend)

    if not orchestration["delegate"]:
        # Direct response
        return await _respond(
            answer=orchestration["answer"],
            explanation=orchestration["answer"],
            mode="resume",
        )

    # Delegated task
    from services.agent_react import AgentReAct
    context_str = (
        f"## Project: {project.name}\n"
        f"Files: {', '.join(file_names) if file_names else '(empty)'}\n"
        f"Description: {project.description or ''}"
    )
    agent = AgentReAct(req.project_id, req.backend, max_steps=50)
    result = await agent.run(orchestration["instruction"], context_str)
    return await _respond(
        answer=result.get("answer", ""),
        code=result.get("code", ""),
        file_path=result.get("file_path", ""),
        steps=result.get("steps", []),
        mode="react",
    )


@router.post("/go-stream")
async def agentic_go_stream(req: GoRequest, db: AsyncSession = Depends(get_db)):
    """SSE streaming version of /go. Yields events as the agent works."""
    project = await db.get(ProjectModel, req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Get active session and handle rollover if context exceeds limit
    active_session = await _get_or_create_active_session(req.project_id, db)
    active_session = await _check_and_rollover_session(req.project_id, active_session, db)

    async def event_stream():
        queue = asyncio.Queue()
        yield f"data: {json.dumps({'type': 'init', 'project': project.name})}\n\n"

        # Save user message linked to active session
        db.add(Conversation(
            project_id=req.project_id,
            session_id=active_session.id,
            role="user",
            content=req.message
        ))
        await db.commit()

        # Load conversation history for active session
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.project_id == req.project_id,
                Conversation.session_id == active_session.id
            ).order_by(Conversation.created_at.desc()).limit(10)
        )
        conv_msgs = list(reversed(conv_result.scalars().all()))
        conv_history = ""
        if conv_msgs:
            conv_history = "\n\n## Conversation précédente:\n" + "\n".join(
                f"{'Utilisateur' if c.role == 'user' else 'Assistant'}: {c.content}"
                for c in conv_msgs[-5:]
            )
        augmented_msg = req.message + conv_history

        # Gather files
        files_result = await db.execute(
            select(Artifact).where(Artifact.project_id == req.project_id)
        )
        files = files_result.scalars().all()
        has_files = len(files) > 0
        file_names = [f.path for f in files]
        if not has_files and project.disk_path:
            from pathlib import Path
            pdir = Path(project.disk_path).resolve()
            if pdir.exists():
                skip_dirs = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache", "target"}
                disk_files = [
                    f for f in pdir.rglob("*")
                    if f.is_file() and not any(p in f.parts for p in skip_dirs)
                ]
                has_files = len(disk_files) > 0
                file_names = [str(f.relative_to(pdir)) for f in disk_files[:50]]

        # Call Orchestrator
        orchestration = await _run_orchestrator(augmented_msg, project.name, file_names, req.backend)

        async def _emit(ev_type, **kw):
            await queue.put(({"type": ev_type, **kw}, False))

        async def _drain_queue():
            """Yield all queued events and stop when sentinel received."""
            while True:
                ev, done = await queue.get()
                if done:
                    break
                yield f"data: {json.dumps(ev)}\n\n"

        if not orchestration["delegate"]:
            # Direct response
            explanation = orchestration["answer"]
            yield f"data: {json.dumps({'type': 'mode', 'mode': 'resume'})}\n\n"
            yield f"data: {json.dumps({'type': 'explanation', 'text': explanation})}\n\n"
            answer = explanation
        else:
            # technical execution
            yield f"data: {json.dumps({'type': 'mode', 'mode': 'react'})}\n\n"
            context_str = (
                f"## Project: {project.name}\n"
                f"Files: {', '.join(file_names) if file_names else '(empty)'}\n"
                f"Description: {project.description or ''}"
            )
            from services.agent_react import AgentReAct
            agent = AgentReAct(req.project_id, req.backend, max_steps=50)

            async def step_cb(steps, step_info, current, total):
                await _emit("step", step=current, total=total,
                            tool=step_info.get("tool"),
                            result=step_info.get("result", ""))

            # Run agent in background, drain queue in foreground
            async def _run_agent():
                try:
                    result = await asyncio.wait_for(
                        agent.run(orchestration["instruction"], context_str, step_callback=step_cb),
                        timeout=300
                    )
                    return result
                except asyncio.TimeoutError:
                    return {"answer": "Agent timed out after 5 minutes.", "steps": []}
                finally:
                    await queue.put(({}, True))

            agent_task = asyncio.create_task(_run_agent())
            async for ev in _drain_queue():
                yield ev
            result = await agent_task
            answer = result.get("answer", "")
            if result.get("code"):
                yield f"data: {json.dumps({'type': 'code', 'code': result['code'], 'file_path': result.get('file_path', '')})}\n\n"

        # Save assistant reply linked to active session
        if answer:
            db.add(Conversation(
                project_id=req.project_id,
                session_id=active_session.id,
                role="assistant",
                content=str(answer)
            ))
            await db.commit()

        yield f"data: {json.dumps({'type': 'done', 'answer': answer})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class SessionResponse(BaseModel):
    id: int
    project_id: int
    agent_type: str
    status: str
    generation: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/projects/{project_id}/sessions", response_model=list[SessionResponse])
async def list_project_sessions(project_id: int, db: AsyncSession = Depends(get_db)):
    """List all agent sessions for a project."""
    res = await db.execute(
        select(AgentSession).where(AgentSession.project_id == project_id)
            .order_by(AgentSession.created_at.desc())
    )
    return res.scalars().all()


@router.get("/sessions/{session_id}/conversations", response_model=list[ConversationResponse])
async def list_session_conversations(session_id: int, db: AsyncSession = Depends(get_db)):
    """List all conversations within a specific session."""
    res = await db.execute(
        select(Conversation).where(Conversation.session_id == session_id)
            .order_by(Conversation.created_at.asc())
    )
    return res.scalars().all()


@router.post("/projects/{project_id}/sessions/new", response_model=SessionResponse)
async def create_new_project_session(project_id: int, db: AsyncSession = Depends(get_db)):
    """Manually start a new clean session (archives the previous one)."""
    # Archive current active sessions
    res = await db.execute(
        select(AgentSession).where(
            AgentSession.project_id == project_id,
            AgentSession.status != "archived"
        )
    )
    active_sessions = res.scalars().all()
    for session in active_sessions:
        session.status = "archived"
        session.updated_at = datetime.now(timezone.utc)
    
    # Create new session
    new_session = AgentSession(project_id=project_id, status="active", agent_type="primary")
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return new_session

