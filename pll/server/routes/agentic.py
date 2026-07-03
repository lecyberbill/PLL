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


async def _detect_mode(message: str, has_files: bool = False) -> str:
    from services.llm_proxy import chat_completion
    system_prompt = (
        "You are an AI router. Classify the user request into exactly one of three categories:\n"
        "- 'resume': if the request is a general question, greeting, conversational chat, or request for explanations/status of the project.\n"
        "- 'simple': if the request is to create or edit a single file (no tool loop needed).\n"
        "- 'react': if the request requires multiple steps, checking folders/files, running shell commands, or utilizing tools (like verification, exploration, multi-file code creation/edits).\n\n"
        "Reply with exactly one word: 'resume', 'simple', or 'react'."
    )
    result = await chat_completion(
        messages=[{"role": "user", "content": message[:500]}],
        system_prompt=system_prompt,
        temperature=0,
        backend="",
    )
    mode = result.get("response", "").strip().lower()
    return mode if mode in ("resume", "simple", "react") else "react"


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
            f"{'Utilisateur' if c.role == 'user' else 'Assistant'}: {c.content}"
            for c in conv_msgs[-5:]
        )

    # Append history to the message
    augmented_msg = req.message + conv_history

    # Save user message + append conversation history
    db.add(Conversation(project_id=req.project_id, role="user", content=req.message))
    await db.commit()
    conv_result = await db.execute(
        select(Conversation).where(Conversation.project_id == req.project_id)
            .order_by(Conversation.created_at.desc()).limit(10)
    )
    history = "\n".join(f"{'User' if c.role=='user' else 'Asst'}: {c.content}"
                        for c in reversed(conv_result.scalars().all()))
    if history:
        augmented_msg += "\n\n## Recent conversation:\n" + history

    async def _respond(**kw):
        answer = kw.get("answer") or kw.get("explanation") or kw.get("question", "")
        if answer:
            db.add(Conversation(project_id=req.project_id, role="assistant", content=str(answer)))
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
    agent_session = await brain._get_or_create_primary(req.project_id, augmented_msg)
    pending = None
    if agent_session.current_state:
        pending = AgentBrain._parse_pending(agent_session.current_state)

    mode = await _detect_mode(req.message, has_files)

    # Resume mode (clear pending, fresh exploration)
    if mode == "resume":
        if pending:
            agent_session.current_state = ""
            await db.commit()
            pending = None
        result = await brain.process_request(req.project_id, augmented_msg, backend=req.backend)
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
        pending["history"].append({"a": augmented_msg})
        ctx_lines = [f"Demande originale: {pending['original']}"]
        for h in pending["history"]:
            if "q" in h and "a" in h:
                ctx_lines.append(f"Q: {h['q']}  A: {h['a']}")
            elif "q" in h:
                ctx_lines.append(f"Q: {h['q']}")
        ctx_lines.append(f"Reponse utilisateur: {augmented_msg}")
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
        augmented_msg = full_message
    else:
        context_str = f"Project: {project.name}\nFiles: {', '.join(file_names) if file_names else '(empty)'}"

    mode = await _detect_mode(req.message, has_files)

    if mode == "resume":
        result = await brain.process_request(req.project_id, augmented_msg, backend=req.backend)
        if result.get("explanation"):
            return await _respond(
                answer=result["explanation"],
                explanation=result["explanation"],
                mode="resume",
                agent_info=result.get("agent_info", {}),
            )

    # Clarification (only for non-resume modes — resume is inherently open-ended)
    if not pending and mode != "resume":
        sub = await brain.clarify_if_needed(augmented_msg, context_str, req.backend)
        if sub.get("needs"):
            pending_data = {"original": augmented_msg, "history": [{"q": sub["question"]}]}
            agent_session.current_state = AgentBrain._pending_key(pending_data)
            agent_session.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return await _respond(question=sub["question"], mode="clarify")

    if mode == "simple":
        target = ""
        if has_files:
            for fname in file_names:
                if fname.replace(".", " ").replace("_", " ") in augmented_msg.lower() or fname in augmented_msg:
                    target = fname
                    break
        result = await brain.process_request(
            req.project_id, augmented_msg, backend=req.backend, target_file=target
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
        agent = AgentReAct(req.project_id, req.backend, max_steps=50)
        result = await agent.run(augmented_msg, context_str)
        return await _respond(
            answer=result.get("answer", ""),
            code=result.get("code", ""),
            file_path=result.get("file_path", ""),
            steps=result.get("steps", []),
            mode="react",
        )

    # Fallback: single ReAct agent with high step limit
    from services.agent_react import AgentReAct
    context_str = (
        f"## Project: {project.name}\n"
        f"Files: {', '.join(file_names) if file_names else '(empty)'}\n"
        f"Description: {project.description or ''}"
    )
    agent = AgentReAct(req.project_id, req.backend, max_steps=50)
    result = await agent.run(augmented_msg, context_str)
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

    async def event_stream():
        queue = asyncio.Queue()
        yield f"data: {json.dumps({'type': 'init', 'project': project.name})}\n\n"

        # Save user message
        db.add(Conversation(project_id=req.project_id, role="user", content=req.message))
        await db.commit()

        # Load conversation history for context
        conv_result = await db.execute(
            select(Conversation).where(Conversation.project_id == req.project_id)
                .order_by(Conversation.created_at.desc()).limit(10)
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
                disk_files = [f for f in pdir.rglob("*") if f.is_file()]
                has_files = len(disk_files) > 0
                file_names = [str(f.relative_to(pdir)) for f in disk_files[:50]]

        brain = AgentBrain(db)
        mode = await _detect_mode(req.message, has_files)

        yield f"data: {json.dumps({'type': 'mode', 'mode': mode})}\n\n"

        async def _emit(ev_type, **kw):
            await queue.put(({"type": ev_type, **kw}, False))

        async def _drain_queue():
            """Yield all queued events and stop when sentinel received."""
            while True:
                ev, done = await queue.get()
                if done:
                    break
                yield f"data: {json.dumps(ev)}\n\n"

        if mode in ("simple", "resume"):
            result = await brain.process_request(req.project_id, augmented_msg, backend=req.backend)
            explanation = result.get("explanation", "")
            if explanation:
                yield f"data: {json.dumps({'type': 'explanation', 'text': explanation})}\n\n"
            if result.get("code"):
                yield f"data: {json.dumps({'type': 'code', 'code': result['code'], 'file_path': result.get('file_path', '')})}\n\n"
            answer = explanation or f"{'Edited' if result.get('edit_mode') else 'Created'} {result.get('file_path', '')}"
        elif mode == "react":
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
                        agent.run(augmented_msg, context_str, step_callback=step_cb),
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
        else:
            answer = "Unknown mode — try rephrasing your request."

        # Save assistant reply
        if answer:
            db.add(Conversation(project_id=req.project_id, role="assistant", content=str(answer)))
            await db.commit()

        yield f"data: {json.dumps({'type': 'done', 'answer': answer})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

