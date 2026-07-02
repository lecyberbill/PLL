import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timezone
from database import get_db
from models import Project as ProjectModel, Artifact, Conversation
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


# Keywords for complexity detection
_SIMPLE_CREATE = {"crée", "create", "écris", "génère", "nouveau", "new", "ajoute"}
_EDIT = {"edit", "modifie", "fix", "corrige", "change", "update", "remplace", "rename"}
_RESUME = {"reprend", "reprends", "explique", "que fait", "décrit", "décris", "raconte", "résume", "status", "état", "projet en cours", "idée", "id", "suggestion", "propose", "idées"}
_COMPLEX = {"api", "microservice", "backend", "frontend", "fullstack", "complète", "complète", "entier", "entière", "tous", "toutes"}
_MULTI_STEP = {"cherche", "trouve", "search", "find", "grep", "parcours", "analyse", "explore"}
_MULTI_FILE = {"projet complet", "application", "plusieurs fichiers", "multi", "tous les fichiers", "structure"}


def _detect_mode(message: str, has_files: bool = False) -> str:
    msg_lower = message.lower()
    if any(kw in msg_lower for kw in _RESUME):
        return "resume"
    if any(kw in msg_lower for kw in _MULTI_FILE):
        return "orchestrate"
    if any(kw in msg_lower for kw in _MULTI_STEP) and has_files:
        return "react"
    if any(kw in msg_lower for kw in _COMPLEX) and has_files:
        return "orchestrate"
    if any(kw in msg_lower for kw in _EDIT):
        return "simple"
    return "simple"


@router.post("/go", response_model=GoResponse)
async def agentic_go(req: GoRequest, db: AsyncSession = Depends(get_db)):
    """Smart single entry point — clarifies if needed, then generates."""

    project = await db.get(ProjectModel, req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Load conversation history (last 10 messages)
    conv_result = await db.execute(
        select(Conversation).where(Conversation.project_id == req.project_id)
            .order_by(Conversation.created_at.desc()).limit(10)
    )
    conv_msgs = list(reversed(conv_result.scalars().all()))
    conv_history = ""
    if conv_msgs:
        conv_history = "\n\n## Conversation précédente:\n" + "\n".join(
            f"{'Utilisateur' if c.role == 'user' else 'Assistant'}: {c.content[:200]}"
            for c in conv_msgs[-5:]
        )

    # Append history to the message
    augmented_msg = req.message + conv_history

    # Save user message + append conversation history
    db.add(Conversation(project_id=req.project_id, role="user", content=req.message[:500]))
    await db.commit()
    conv_result = await db.execute(
        select(Conversation).where(Conversation.project_id == req.project_id)
            .order_by(Conversation.created_at.desc()).limit(10)
    )
    history = "\n".join(f"{'User' if c.role=='user' else 'Asst'}: {c.content[:200]}"
                        for c in reversed(conv_result.scalars().all()))
    if history:
        req.message += "\n\n## Recent conversation:\n" + history

    async def _respond(**kw):
        answer = kw.get("answer") or kw.get("explanation") or kw.get("question", "")
        if answer:
            db.add(Conversation(project_id=req.project_id, role="assistant", content=str(answer)[:500]))
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
            disk_files = [f for f in pdir.rglob("*") if f.is_file()]
            has_files = len(disk_files) > 0
            file_names = [str(f.relative_to(pdir)) for f in disk_files[:50]]
    brain = AgentBrain(db)

    # Check for pending clarification
    agent_session = await brain._get_or_create_primary(req.project_id, req.message)
    pending = None
    if agent_session.current_state:
        pending = AgentBrain._parse_pending(agent_session.current_state)

    mode = _detect_mode(req.message, has_files)

    # Resume mode (clear pending, fresh exploration)
    if mode == "resume":
        if pending:
            agent_session.current_state = ""
            await db.commit()
            pending = None
        result = await brain.process_request(req.project_id, req.message, backend=req.backend)
        if result.get("explanation"):
            return await _respond(
                answer=result["explanation"],
                explanation=result["explanation"],
                mode="resume",
                agent_info=result.get("agent_info", {}),
            )
        return await _respond(answer="Projet analysé.", mode="resume")

    if pending:
        # User is responding to a clarification question
        pending["history"].append({"a": req.message})
        ctx_lines = [f"Demande originale: {pending['original']}"]
        for h in pending["history"]:
            if "q" in h and "a" in h:
                ctx_lines.append(f"Q: {h['q']}  A: {h['a']}")
            elif "q" in h:
                ctx_lines.append(f"Q: {h['q']}")
        ctx_lines.append(f"Reponse utilisateur: {req.message}")
        full_message = "\n".join(ctx_lines)

        # Check if we need further clarification
        context_str = f"Project: {project.name}\nFiles: {', '.join(file_names) if file_names else '(empty)'}"
        sub = await brain.clarify_if_needed(full_message, context_str, req.backend)
        if sub.get("needs"):
            pending["history"].append({"q": sub["question"]})
            agent_session.current_state = AgentBrain._pending_key(pending)
            agent_session.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return await _respond(question=sub["question"], mode="clarify")

        # Clear enough — proceed with generation
        agent_session.current_state = ""
        await db.commit()
        req.message = full_message
    else:
        context_str = f"Project: {project.name}\nFiles: {', '.join(file_names) if file_names else '(empty)'}"

    mode = _detect_mode(req.message, has_files)

    if mode == "resume":
        result = await brain.process_request(req.project_id, req.message, backend=req.backend)
        if result.get("explanation"):
            return await _respond(
                answer=result["explanation"],
                explanation=result["explanation"],
                mode="resume",
                agent_info=result.get("agent_info", {}),
            )

    # Clarification (only for non-resume modes — resume is inherently open-ended)
    if not pending and mode != "resume":
        sub = await brain.clarify_if_needed(req.message, context_str, req.backend)
        if sub.get("needs"):
            pending_data = {"original": req.message, "history": [{"q": sub["question"]}]}
            agent_session.current_state = AgentBrain._pending_key(pending_data)
            agent_session.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return await _respond(question=sub["question"], mode="clarify")

    if mode == "simple":
        target = ""
        if has_files:
            for fname in file_names:
                if fname.replace(".", " ").replace("_", " ") in req.message.lower() or fname in req.message:
                    target = fname
                    break
        result = await brain.process_request(
            req.project_id, req.message, backend=req.backend, target_file=target
        )
        if result.get("explanation"):
            return await _respond(
                answer=result["explanation"], explanation=result["explanation"], mode="resume"
            )
        return await _respond(
            answer=f"{'Edited' if result.get('edit_mode') else 'Created'} {result['file_path']}",
            code=result["code"],
            file_path=result["file_path"],
            files_modified=result.get("files_modified", []),
            mode="edit" if result.get("edit_mode") else "create",
            agent_info=result.get("agent_info", {}),
        )

    if mode == "react":
        from services.agent_react import AgentReAct
        context_str = (
            f"## Project: {project.name}\n"
            f"Files: {', '.join(file_names) if file_names else '(empty)'}\n"
            f"Description: {project.description or ''}"
        )
        agent = AgentReAct(req.project_id, req.backend, max_steps=15)
        result = await agent.run(req.message, context_str)
        return await _respond(
            answer=result.get("answer", ""),
            code=result.get("code", ""),
            file_path=result.get("file_path", ""),
            steps=result.get("steps", []),
            mode="react",
        )

    from services.agent_coordinator import AgentCoordinator
    context_str = (
        f"## Project: {project.name}\n"
        f"Files: {', '.join(file_names) if file_names else '(empty)'}"
    )
    coord = AgentCoordinator(req.project_id, req.backend)
    result = await coord.orchestrate(req.message, context_str)
    return await _respond(
        answer=result.get("answer", ""),
        code=result.get("code", ""),
        file_path=result.get("file_path", ""),
        steps=[{"subtask": s.get("subtask", ""), "result": s.get("result", "")[:200]}
               for s in result.get("subtasks", [])],
        mode="orchestrate",
    )

