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
            req.project_id, req.message, backend=req.backend, target_file=req.target_file
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
        response = await brain.chat(req.project_id, req.message)
        return {"response": response}
    except (ValueError, ConnectionError, RuntimeError) as e:
        raise HTTPException(400, str(e))


# ---- Smart Auto-Router ----

class GoRequest(BaseModel):
    project_id: int
    message: str
    backend: str = ""
    session_id: Optional[int] = None


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


async def _get_or_restore_session(project_id: int, req_session_id: Optional[int], db: AsyncSession) -> AgentSession:
    if req_session_id:
        session = await db.get(AgentSession, req_session_id)
        if session:
            if session.status == "archived":
                session.status = "active"
                session.updated_at = datetime.now(timezone.utc)
                await db.commit()
                await db.refresh(session)
            return session
    return await _get_or_create_active_session(project_id, db)


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
        "You MUST express your decision using PLL (compact inter-agent language) variable declarations.\n\n"
        "Variables to declare:\n"
        "- 'thought': your step-by-step reasoning (string)\n"
        "- 'delegate': true if technical actions (creating, editing, fixing, deleting files, writing code, running shell commands, or verifying the project) are needed, false otherwise (boolean)\n"
        "- 'instruction': technical instructions for ReAct (string, only if delegate is true)\n"
        "- 'answer': direct reply to the user (string, only if delegate is false)\n\n"
        "Format Rules:\n"
        "1. Output ONLY the PLL declarations, no markdown, no explanation.\n"
        "2. Declare variables using the syntax: v name != \"value\" or v name != true/false\n\n"
        "Examples of PLL output:\n\n"
        "For 'comment je lance le jeu ?':\n"
        "v thought != \"The user is asking how to run the project. No file changes needed. Reply directly.\"\n"
        "v delegate != false\n"
        "v answer != \"Pour lancer le jeu, ouvrez index.html dans votre navigateur.\"\n\n"
        "For 'ajoute une fonction de log':\n"
        "v thought != \"The user wants to modify files to add logging. This requires technical execution.\"\n"
        "v delegate != true\n"
        "v instruction != \"Add a logging function to the main JS file\""
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
    resp = result.get("response", "").strip()
    
    import re
    delegate_m = re.search(r'v\s+delegate\s*!=\s*(true|false)', resp, re.IGNORECASE)
    instruction_m = re.search(r'v\s+instruction\s*!=\s*["\']([\s\S]*?)["\']', resp)
    answer_m = re.search(r'v\s+answer\s*!=\s*["\']([\s\S]*?)["\']', resp)
    
    is_delegate = False
    if delegate_m:
        is_delegate = (delegate_m.group(1).lower() == "true")
    else:
        # Fallback if variable was not declared explicitly but instruction exists
        is_delegate = bool(instruction_m)
        
    if is_delegate:
        inst = instruction_m.group(1).strip() if instruction_m else message
        return {"delegate": True, "instruction": inst, "raw_response": resp}
    else:
        ans = answer_m.group(1).strip() if answer_m else resp
        return {"delegate": False, "answer": ans}


@router.post("/go", response_model=GoResponse)
async def agentic_go(req: GoRequest, db: AsyncSession = Depends(get_db)):
    """Smart single entry point — orchestrates, then generates or replies."""
    project = await db.get(ProjectModel, req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Get active session and handle rollover if context exceeds limit
    active_session = await _get_or_restore_session(req.project_id, req.session_id, db)
    active_session = await _check_and_rollover_session(req.project_id, active_session, db)

    # Load conversation history for the active session (last 10 messages)
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.project_id == req.project_id,
            Conversation.session_id == active_session.id
        ).order_by(Conversation.created_at.desc()).limit(10)
    )
    conv_msgs = list(reversed(conv_result.scalars().all()))
    from services.agent_brain import sync_decision_tree
    await sync_decision_tree(active_session, req.message, conv_msgs, db, req.backend)

    conv_history = ""
    if conv_msgs:
        conv_history = "\n\n## Conversation précédente:\n" + "\n".join(
            f"{'Utilisateur' if c.role == 'user' else 'Assistant'}: {c.content}"
            for c in conv_msgs[-5:]
        )

    decisions_summary = ""
    try:
        state_data = json.loads(active_session.current_state)
        decisions = state_data.get("decisions", [])
        active_decs = [d for d in decisions if d.get("status") != "overridden"]
        if active_decs:
            decisions_summary = "\n\n## Décisions et choix validés :\n" + "\n".join(
                f"- {d['question']} -> {d['answer']}"
                for d in active_decs
            )
    except Exception:
        pass

    # Append history and decisions to the message
    augmented_msg = req.message + conv_history + decisions_summary

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
        f"Description: {project.description or ''}\n"
        f"{decisions_summary}\n"
        f"{conv_history}"
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
    active_session = await _get_or_restore_session(req.project_id, req.session_id, db)
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
        from services.agent_brain import sync_decision_tree
        await sync_decision_tree(active_session, req.message, conv_msgs, db, req.backend)

        conv_history = ""
        if conv_msgs:
            conv_history = "\n\n## Conversation précédente:\n" + "\n".join(
                f"{'Utilisateur' if c.role == 'user' else 'Assistant'}: {c.content}"
                for c in conv_msgs[-5:]
            )

        decisions_summary = ""
        try:
            state_data = json.loads(active_session.current_state)
            decisions = state_data.get("decisions", [])
            active_decs = [d for d in decisions if d.get("status") != "overridden"]
            if active_decs:
                decisions_summary = "\n\n## Décisions et choix validés :\n" + "\n".join(
                    f"- {d['question']} -> {d['answer']}"
                    for d in active_decs
                )
        except Exception:
            pass

        augmented_msg = req.message + conv_history + decisions_summary

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
                f"Description: {project.description or ''}\n"
                f"{decisions_summary}\n"
                f"{conv_history}"
            )
            from services.agent_react import AgentReAct
            agent = AgentReAct(req.project_id, req.backend, max_steps=50)
            agent.session_id = active_session.id

            async def step_cb(steps, step_info, current, total):
                if step_info.get("status") == "pending_approval":
                    await _emit("require_confirmation",
                                tool=step_info.get("tool"),
                                command=step_info.get("args", {}).get("cmd"),
                                session_id=step_info.get("session_id"))
                else:
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

        # Save assistant reply linked to active session and save steps to current_state
        if answer:
            try:
                state_data = {}
                if active_session.current_state:
                    try:
                        state_data = json.loads(active_session.current_state)
                    except Exception:
                        state_data = {}
                if not isinstance(state_data, dict):
                    state_data = {}
                
                state_data["steps"] = result.get("steps", [])
                active_session.current_state = json.dumps(state_data)
                db.add(active_session)
            except Exception as e:
                print(f"Error saving session steps: {e}")

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
    current_state: str = ""
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


from models import PendingChange

@router.get("/sessions/{session_id}/pending")
async def list_pending_changes(session_id: int, db: AsyncSession = Depends(get_db)):
    """List all pending changes for a session."""
    res = await db.execute(
        select(PendingChange).where(PendingChange.session_id == session_id)
    )
    return [{"id": pc.id, "path": pc.path, "old_content": pc.old_content, "new_content": pc.new_content} for pc in res.scalars().all()]


@router.post("/sessions/{session_id}/accept")
async def accept_pending_changes(session_id: int, db: AsyncSession = Depends(get_db)):
    """Accept and confirm all pending changes (deletes records, keeps disk state)."""
    res = await db.execute(
        select(PendingChange).where(PendingChange.session_id == session_id)
    )
    pcs = res.scalars().all()
    for pc in pcs:
        await db.delete(pc)
    await db.commit()
    return {"status": "ok", "message": f"Accepted {len(pcs)} modifications."}


@router.post("/sessions/{session_id}/reject")
async def reject_pending_changes(session_id: int, db: AsyncSession = Depends(get_db)):
    """Reject all pending changes (reverts disk files to old_content and deletes records)."""
    from pathlib import Path
    res = await db.execute(
        select(PendingChange).where(PendingChange.session_id == session_id)
    )
    pcs = res.scalars().all()
    reverted_count = 0
    for pc in pcs:
        from models import Project
        project = await db.get(Project, pc.project_id)
        if project and project.disk_path:
            pdir = Path(project.disk_path).resolve()
            fp = (pdir / pc.path).resolve()
            try:
                if not pc.old_content.strip():
                    # If it was a new file, delete it
                    if fp.exists():
                        fp.unlink()
                else:
                    fp.parent.mkdir(parents=True, exist_ok=True)
                    fp.write_text(pc.old_content, encoding="utf-8")
                reverted_count += 1
            except Exception as e:
                print(f"Error reverting file {pc.path}: {e}")
        await db.delete(pc)
    await db.commit()
    return {"status": "ok", "message": f"Rejected and reverted {reverted_count} modifications."}


@router.post("/sessions/{session_id}/archive")
async def archive_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """Archive a specific session by ID."""
    session = await db.get(AgentSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.status = "archived"
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return {"status": "ok", "message": f"Session {session_id} archived."}


class ConfirmCommandRequest(BaseModel):
    approved: bool


@router.post("/sessions/{session_id}/confirm_command")
async def confirm_command(session_id: int, req: ConfirmCommandRequest):
    """Confirm or reject a pending agent command for the given session."""
    from services.agent_react import PENDING_APPROVALS
    pending = PENDING_APPROVALS.get(session_id)
    if not pending:
        raise HTTPException(404, "No pending command approval found for this session")
    
    pending["approved"] = req.approved
    pending["event"].set()
    return {"status": "ok", "message": "Command approved" if req.approved else "Command rejected"}


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """Get details of a specific agent session."""
    session = await db.get(AgentSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session

