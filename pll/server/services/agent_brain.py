"""
Agent Brain Service

Connects the GCA lifecycle with LLM-powered code generation.

Learning mechanisms:
  1. FEW-SHOT — complete PLL examples in the system prompt
  2. SELF-REVIEW LOOP — the LLM reviews and fixes its own code
  3. RAG VAULT — retrieves similar successful examples from past generations

When a user asks for something:
  1. Load project context + retrieve similar vault examples (RAG)
  2. Ensure/create an active Primary agent
  3. LLM generates PLL code (with self-review)
  4. Code saved as artifact + checkpoint to vault
  5. Over time, the vault becomes a rich corpus of PLL examples
"""
import re
import os
import json
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import Project, Artifact, AgentSession, GCAVault
from services.llm_proxy import generate_pll_code, chat_completion
from services.gca_orchestrator import GCAOrchestrator
from config import PROJECTS_DIR


AGENTIC_SYSTEM_PROMPT = """You are an AI coding assistant. You think in PLL (compact inter-agent language) but output code in the target language.

PLL is for your internal reasoning:
  v task != user_message => TaskPlan         # break down the task
  v files != ?("Check existing files")        # review context
  v code != ?("Generate Python Flask CRUD")   # create target code

When the user asks you to CREATE new code:
- First think in PLL about what to build
- Then generate a complete file from scratch
- Start with a comment: # file: filename.ext (replace with the correct filename/extension)
- Then the full file content

When the user asks you to EDIT existing code:
- Read the CURRENT FILE content provided below
- Understand what needs to change
- Output the COMPLETE updated file (never a diff)

Rules:
- Output ONLY the file content, no explanation
- The user's project files are listed below with their content"""


_PENDING_PREFIX = "PENDING_CLARIFY::"

CLARIFY_SYSTEM_PROMPT = """You are a collaborative coding assistant. Before generating code, decide if the user's request is specific enough.

If the request is clear and complete — you know exactly what language, framework, storage, and endpoints to generate — respond with exactly: OK

If the request is too vague or missing critical details, respond with exactly:
QUESTION: <your question here>

Examples:
- "Crée une API Flask" -> QUESTION: Quel type de stockage ? (memoire, SQLite, PostgreSQL)
- "Ajoute une page d'accueil" -> QUESTION: En HTML brut ou avec un framework (React, Vue, Jinja) ?
- "Fais un CRUD utilisateurs" -> QUESTION: Quel langage/framework ? Quels champs pour l'utilisateur ?
- "Crée une API REST Flask pour todos avec SQLite" -> OK (specifique, clair)
- "Hello world en Python" -> OK (simple, aucun doute)
"""


class AgentBrain:
    """The 'intelligence' layer that connects LLM, GCA, and PLL execution."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.orch = GCAOrchestrator(db)

    async def clarify_if_needed(self, message: str, context: str, backend: str = "") -> dict:
        """Check if the request needs clarification. Returns {"needs": False} or {"needs": True, "question": "..."}."""
        prompt = (
            f"User request: {message}\n\n"
            f"Project context:\n{context[:800]}\n\n"
            "Respond with OK if clear enough, or QUESTION: <your question> if more info needed."
        )
        result = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=CLARIFY_SYSTEM_PROMPT,
            temperature=0.1,
            backend=backend,
        )
        resp = result["response"].strip()
        if resp.upper().startswith("QUESTION:"):
            q = resp[9:].strip().strip('"').strip("'")
            return {"needs": True, "question": q}
        return {"needs": False}

    @staticmethod
    def _pending_key(data: dict) -> str:
        """Encode pending clarification state for current_state."""
        return _PENDING_PREFIX + json.dumps(data)

    @staticmethod
    def _parse_pending(state: str) -> dict | None:
        """Decode pending clarification from current_state."""
        if state.startswith(_PENDING_PREFIX):
            try:
                return json.loads(state[len(_PENDING_PREFIX):])
            except json.JSONDecodeError:
                return None
        return None

    async def process_request(
        self,
        project_id: int,
        user_message: str,
        backend: str = "",
        target_file: str = "",
    ) -> dict:
        project = await self.db.get(Project, project_id)
        if not project:
            raise ValueError("Project not found")

        context = await self._build_context(project_id)
        rag_examples = await self._retrieve_similar_examples(
            project_id, user_message, top_k=5
        )
        agent = await self._get_or_create_primary(project_id, user_message)

        # Let the LLM decide: explore/converse or generate code
        resume_mode = False
        # If user mentions a file path, force GENERATE mode (not exploration)
        import re as _re_path
        if _re_path.search(r'[a-zA-Z]:\\(?:[^\\]+\\)*(?:[^\\]+)?|/(?:[^/]+/)*(?:[^/]+)?\.[a-zA-Z]+', user_message):
            resume_mode = False
        else:
            try:
                confirm = await chat_completion(
                    messages=[{"role": "user", "content": (
                        f"Message: {user_message[:200]}\n\n"
                        f"EXPLORE = user wants ideas, explanations, greetings, conversation, small talk, project review, status updates, or requests to wait/stop.\n"
                        f"GENERATE = explicitly requests creating, editing, fixing, or modifying code files.\n\n"
                        f"Think step-by-step about the intent, then output the final choice as either <intent>EXPLORE</intent> or <intent>GENERATE</intent>.\n\n"
                        f"Examples:\n"
                        f'  - "hello" -> Thought: Greeting. Choice: <intent>EXPLORE</intent>\n'
                        f'  - "attend je debug et on se reparle" -> Thought: Casual notice telling me to wait. Choice: <intent>EXPLORE</intent>\n'
                        f'  - "de ton côté pas eu de difficulté ?" -> Thought: Small talk / question. Choice: <intent>EXPLORE</intent>\n'
                        f'  - "ajoute une route à app.py" -> Thought: Edit code file. Choice: <intent>GENERATE</intent>'
                    )}],
                    system_prompt="Classify the user intent. Output either EXPLORE or GENERATE within the <intent> tag.",
                    temperature=0.05,
                    backend=backend,
                )
                resp = confirm["response"].upper().strip()
                import re as _re_intent
                match = _re_intent.search(r'<intent>(EXPLORE|GENERATE)</intent>', resp)
                if match:
                    resume_mode = (match.group(1) == "EXPLORE")
                else:
                    resume_mode = "EXPLORE" in resp or not ("GENERATE" in resp)
            except Exception:
                resume_mode = True  # fallback: assume conversation on error

        if not target_file and not resume_mode:
            target_file = self._detect_target(user_message, agent, context["files"])
        edit_mode = bool(target_file)

        if resume_mode:
            # Include ALL file contents for project takeover
            full_project = ""
            for f in context["files"]:
                fpath = f if isinstance(f, str) else (f.path if hasattr(f, 'path') else f.get('path', ''))
                fcontent = f if isinstance(f, str) else (f.content if hasattr(f, 'content') else f.get('content', ''))
                lang = self._detect_language(fpath)
                full_project += f"\n--- {fpath} ({lang}) ---\n{fcontent}\n"

            # Add any files only on disk (not in DB) — only for DB mode, disk mode already has all
            if not bool(project.disk_path):
                disk_files_bare = await self._list_disk(project_id)
                known_paths = {f.path if hasattr(f, 'path') else f.get('path', '') for f in context["files"]}
                for df in disk_files_bare:
                    if df["path"] not in known_paths:
                        content = await self._read_disk(project_id, df["path"])
                        if content:
                            lang = self._detect_language(df["path"])
                            full_project += f"\n--- {df['path']} ({lang}) [disk only] ---\n{content}\n"

            context["files_summary"] = (
                f"## Project: {project.name}\n"
                f"Description: {project.description or '(none)'}\n"
                f"Total files: {len(context['files'])}\n"
                + (full_project or "  (no files yet)")
            )
            edit_mode = False  # resume is not an edit

        elif edit_mode:
            existing_record = next((f for f in context["files"] if (f.path if hasattr(f, 'path') else f.get('path', '')) == target_file), None)
            if existing_record:
                existing_content = existing_record.content if hasattr(existing_record, 'content') else existing_record.get('content', '')
            else:
                content_from_disk = await self._read_disk(project_id, target_file)
                existing_content = content_from_disk or ""
            if existing_content:
                context["files_summary"] = (
                    f"  ** EDITING: {target_file} **\n"
                    f"--- CURRENT CONTENT of {target_file} ---\n{existing_content}\n"
                    f"--- END OF CURRENT CONTENT ---\n"
                    + context["files_summary"]
                )

        # Conversation history in PLL format (compact, parseable by agents)
        conversation_history = ""
        if agent.current_state and "::" in agent.current_state:
            conv_parts = agent.current_state.split("::")
            lines = ["v history != ["]
            for p in conv_parts[-4:]:
                lines.append(f'    "{{ {p.strip()} }}",')
            lines.append("]")
            conversation_history = "\n".join(lines)
            if conversation_history:
                conversation_history = "\n## Agent conversation history (PLL):\n" + conversation_history

        rag_context = ""
        if rag_examples:
            rag_context = "Similar past examples from vault:\n\n" + "\n\n".join(
                f"--- Example: {ex['key']} ---\nRequest: {ex['request']}\nCode:\n{ex['code']}"
                for ex in rag_examples
            )

        full_context = (
            f"{context['files_summary']}\n\n"
            f"{conversation_history}\n\n"
            f"{rag_context}"
        )

        if resume_mode:
            explanation = await chat_completion(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=(
                    "You are a senior developer reviewing a project. "
                    "Analyze the code files below and answer the user's question clearly. "
                    "Be specific: mention file names, function names, and key logic. "
                    "If they ask to resume work, suggest the next steps."
                ) + f"\n\n{full_context}",
                temperature=0.3,
                backend=backend,
            )
            code = ""
            file_path = ""
            files_modified = []
            response_text = explanation["response"]

            agent.current_state = f"Review: {user_message[:80]}"
            agent.updated_at = datetime.now(timezone.utc)

            return {
                "code": code,
                "file_path": file_path,
                "files_modified": files_modified,
                "edit_mode": False,
                "explanation": response_text,
                "agent_info": {
                    "session_id": agent.id,
                    "generation": agent.generation,
                    "status": agent.status,
                },
            }

        code = await generate_pll_code(
            user_request=user_message,
            context=full_context,
            temperature=0.15 if not edit_mode else 0.1,
            max_retries=2,
            backend=backend,
            language=self._detect_language(target_file or user_message),
        )

        lang = self._detect_language(target_file or user_message)
        file_path = target_file or self._extract_filename(code) or self._suggest_filename(user_message, lang)
        artifact = await self._save_artifact(project_id, file_path, code)

        agent.status = "working"
        action_desc = f"Edited {file_path}" if edit_mode else f"Created {file_path}"
        prev = agent.current_state or ""
        if len(prev) > 500:
            prev_parts = prev.split("::")
            prev = "::".join(prev_parts[-3:])
        new_state = f"{action_desc}: {user_message[:80]}"
        agent.current_state = f"{prev}::{new_state}" if prev else new_state
        agent.updated_at = datetime.now(timezone.utc)

        tags_list = self._extract_keywords(user_message)
        vault_key = f"{'edit' if edit_mode else 'gen'}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pll"
        vault_content = (
            f"v vault_entry != {{\n"
            f"    request: \"{user_message.replace('\"', '\\\"')}\",\n"
            f"    file: \"{file_path}\",\n"
            f"    code: \"\"\"{code}\"\"\",\n"
            f"    agent: \"session {agent.id} gen {agent.generation}\",\n"
            f"    tags: [{', '.join(f'\"{t}\"' for t in tags_list)}],\n"
            f"    mode: \"{'edit' if edit_mode else 'create'}\"\n"
            f"}}\n"
        )
        await self.orch.checkpoint(
            project_id, agent.id,
            key=vault_key,
            content=vault_content,
            current_state=f"{'Edited' if edit_mode else 'Generated'} {file_path}",
        )

        return {
            "code": code,
            "file_path": file_path,
            "files_modified": [file_path],
            "edit_mode": edit_mode,
            "explanation": "",
            "agent_info": {
                "session_id": agent.id,
                "generation": agent.generation,
                "status": agent.status,
            },
        }

    EDIT_KEYWORDS = ["edit", "modifie", "change", "update", "fix", "corrige", "ajoute", "remplace", "rename"]

    @staticmethod
    def _detect_target(message: str, agent, files) -> str:
        msg_lower = message.lower()
        for keyword in AgentBrain.EDIT_KEYWORDS:
            if keyword in msg_lower:
                break
        else:
            return ""
        # Try to extract filename from message
        for f in files:
            fpath = f.path if hasattr(f, 'path') else f.get('path', '')
            fname_lower = fpath.lower()
            if fname_lower in msg_lower or fname_lower.replace(".", " ").replace("_", " ") in msg_lower:
                return fpath
        # Fallback: last edited file from agent state
        if agent.current_state:
            for part in agent.current_state.split("::"):
                for prefix in ("Edited ", "Created "):
                    if part.strip().startswith(prefix):
                        fname = part.strip()[len(prefix):].split(":")[0].strip()
                        if fname:
                            return fname
        return ""

    @staticmethod
    def _detect_language(text: str) -> str:
        lower = text.lower()
        # Comprehensive language detection: language name, framework, or extension
        lang_map = [
            # (keyword, language_name)
            ("python", "python"), ("flask", "python"), ("django", "python"), ("fastapi", "python"),
            ("javascript", "javascript"), ("js", "javascript"), ("express", "javascript"),
            ("node", "javascript"), ("vue", "javascript"), ("svelte", "javascript"),
            ("typescript", "typescript"), ("ts", "typescript"), ("react", "typescript"),
            ("angular", "typescript"), ("deno", "typescript"), ("next", "typescript"),
            ("rust", "rust"), ("cargo", "rust"),
            ("golang", "go"), ("go ", "go"), ("gin", "go"),
            ("java", "java"), ("spring", "java"), ("kotlin", "kotlin"), ("swift", "swift"),
            ("ruby", "ruby"), ("rails", "ruby"), ("sinatra", "ruby"),
            ("php", "php"), ("laravel", "php"), ("symfony", "php"),
            ("c++", "cpp"), ("cpp", "cpp"), ("csharp", "csharp"), ("c#", "csharp"),
            ("dotnet", "csharp"), ("html", "html"), ("css", "css"), ("scss", "css"),
            ("sql", "sql"), ("postgresql", "sql"), ("mysql", "sql"),
            ("shell", "bash"), ("bash", "bash"), ("zsh", "bash"), ("powershell", "powershell"),
            ("pll", "pll"), ("r", "r"), ("dart", "dart"), ("flutter", "dart"),
            ("lua", "lua"), ("haskell", "haskell"), ("scala", "scala"),
            ("perl", "perl"), ("elixir", "elixir"), ("clojure", "clojure"),
            ("solidity", "solidity"), ("zig", "zig"), ("nim", "nim"),
            # Extensions (fallback)
            (".py", "python"), (".rs", "rust"), (".js", "javascript"), (".ts", "typescript"),
            (".pll", "pll"), (".html", "html"), (".css", "css"), (".json", "json"),
            (".go", "go"), (".java", "java"), (".cpp", "cpp"), (".rb", "ruby"),
            (".php", "php"), (".swift", "swift"), (".kt", "kotlin"), (".rs", "rust"),
            (".r", "r"), (".dart", "dart"), (".lua", "lua"), (".hs", "haskell"),
            (".scala", "scala"), (".pl", "perl"), (".ex", "elixir"), (".clj", "clojure"),
            (".sol", "solidity"), (".zig", "zig"), (".sh", "bash"), (".ps1", "powershell"),
            (".sql", "sql"), (".vue", "javascript"), (".svelte", "javascript"),
        ]
        for keyword, lang in lang_map:
            if keyword in lower:
                return lang
        return "python"

    async def chat(self, project_id: int, user_message: str) -> str:
        """Conversational chat with RAG context from the vault."""
        context = await self._build_context(project_id)
        rag = await self._retrieve_similar_examples(project_id, user_message, top_k=3)
        rag_str = ""
        if rag:
            rag_str = "\n## Relevant past work:\n" + "\n".join(
                f"- {ex['key']}: {ex['request'][:80]}"
                for ex in rag
            )
        system_msg = (
            AGENTIC_SYSTEM_PROMPT
            + f"\n\n## Project: {context['project_name']}\n"
            + f"## Files:\n{context['files_summary']}\n"
            + f"## Vault:\n{context['vault_summary']}"
            + rag_str
        )
        result = await chat_completion(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=system_msg,
            temperature=0.5,
        )
        return result["response"]

    # ------------------------------------------------------------------
    # RAG: Retrieve similar examples from vault
    # ------------------------------------------------------------------
    async def _retrieve_similar_examples(
        self, project_id: int, query: str, top_k: int = 5
    ) -> list[dict]:
        """Simple keyword-based RAG: find vault entries matching the query."""
        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        result = await self.db.execute(
            select(GCAVault)
            .where(GCAVault.project_id == project_id)
            .order_by(GCAVault.created_at.desc())
            .limit(100)
        )
        entries = result.scalars().all()

        scored = []
        for entry in entries:
            content_lower = entry.content.lower()
            score = sum(1 for kw in keywords if kw in content_lower)
            if score > 0:
                # Extract request and code from vault entry
                request = self._extract_vault_field(entry.content, "**Request:**")
                code = self._extract_vault_code(entry.content)
                scored.append({
                    "score": score,
                    "key": entry.key,
                    "request": request or "(no request)",
                    "code": code or "(no code)",
                    "content": entry.content,
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from a query."""
        stop_words = {
            "the", "a", "an", "in", "on", "at", "to", "for", "of", "with",
            "and", "or", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "can", "could", "shall", "should", "may", "might", "must",
            "create", "make", "write", "get", "set", "use", "need", "want",
            "une", "un", "une", "des", "du", "de", "la", "le", "les",
            "ce", "cette", "ces", "mon", "ton", "son", "ma", "ta", "sa",
            "je", "tu", "il", "elle", "nous", "vous", "ils", "elles",
            "est", "sont", "dans", "pour", "avec", "sur", "par", "pas",
            "qui", "que", "quoi", "dont", "ou", "et", "mais", "donc",
            "car", "ni", "or",
        }
        words = re.findall(r'[a-zA-Z_]\w{2,}', text.lower())
        return list(set(w for w in words if w not in stop_words))[:15]

    @staticmethod
    def _extract_vault_field(content: str, field: str) -> str:
        # New PLL format: field: "..."
        field_prefix = field.rstrip(":")
        match = re.search(rf'{re.escape(field_prefix)}:\s*"([^"]*)"', content)
        if match:
            return match.group(1)
        # Old markdown format: **Field:** value
        for line in content.split("\n"):
            if line.startswith(field):
                return line[len(field):].strip()
        return ""

    @staticmethod
    def _extract_vault_code(content: str) -> str:
        # PLL vault format: code: """..."""
        match = re.search(r'code:\s*"""(.+?)"""', content, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Fallback: old markdown format
        match = re.search(r'```pll\n(.*?)```', content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------
    async def _build_context(self, project_id: int) -> dict:
        project = await self.db.get(Project, project_id)
        if not project:
            return {"project_name": "?", "files_summary": "", "vault_summary": "", "files": [], "vault_entries": []}

        is_disk = bool(project.disk_path)
        vault_result = await self.db.execute(
            select(GCAVault)
            .where(GCAVault.project_id == project_id)
            .order_by(GCAVault.created_at.desc())
            .limit(10)
        )
        vault_entries = vault_result.scalars().all()

        if is_disk:
            # Disk mode: list from filesystem, no Artifact records
            disk_files = await self._list_disk(project_id)
            sources = disk_files
            files_summary = "\n".join(
                f"  [disk] {f['path']} ({f['size']} bytes)" for f in disk_files
            ) or "  (empty project)"
            # Populate files list with actual content for context
            files = []
            full_contents = ""
            for df in disk_files[:15]:
                content = await self._read_disk(project_id, df["path"])
                if content is not None:
                    files.append({"path": df["path"], "content": content})
                    full_contents += f"\n--- {df['path']} ---\n{content[:2000]}\n"
            if full_contents:
                files_summary += "\n\n## Project files content:\n" + full_contents
        else:
            # DB mode: from Artifact table
            files_result = await self.db.execute(
                select(Artifact).where(Artifact.project_id == project_id)
            )
            files = files_result.scalars().all()
            files_summary = "\n".join(
                f"  {f.path} ({len(f.content)} chars)" for f in files
            ) or "  (no files yet)"

        vault_summary = "\n".join(
            f"  [{v.created_at.strftime('%H:%M')}] {v.key}: "
            f"{v.content[:100].strip()}"
            for v in vault_entries
        ) or "  (empty)"

        return {
            "project_name": project.name,
            "files_summary": files_summary,
            "vault_summary": vault_summary,
            "files": files,
            "vault_entries": vault_entries,
        }

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------
    async def _get_or_create_primary(self, project_id: int, objective: str) -> AgentSession:
        result = await self.db.execute(
            select(AgentSession).where(
                AgentSession.project_id == project_id,
                AgentSession.agent_type == "primary",
                AgentSession.status != "dead",
            )
        )
        agent = result.scalar_one_or_none()
        if agent:
            return agent
        primary, _ = await self.orch.init_cycle(project_id, objective)
        return primary

    async def _save_artifact(self, project_id: int, path: str, content: str):
        """Save file to project. Disk mode = filesystem only. DB mode = Artifact + filesystem."""
        import re as _re
        file_markers = list(_re.finditer(r'^#\s*file:\s*(\S+)', content, _re.MULTILINE))
        print(f"[PLL_SAVE] _save_artifact: path='{path}', content_len={len(content)}, markers={len(file_markers)}")
        if len(file_markers) > 1:
            parts = _re.split(r'^#\s*file:\s*\S+\s*\r?\n?', content, flags=_re.MULTILINE)
            for i, marker in enumerate(file_markers):
                sub_path = marker.group(1)
                sub_content = parts[i + 1].strip() if i + 1 < len(parts) else ""
                if sub_content:
                    await self._save_artifact(project_id, sub_path, sub_content)
            return {"path": path, "mode": "multi-split", "count": len(file_markers)}
        # Strip single file header if present
        content = _re.sub(r'^#\s*file:\s*\S+\s*\r?\n?', '', content, count=1)

        project = await self.db.get(Project, project_id)
        is_disk = bool(project and project.disk_path)

        # Always write to disk
        await self._write_disk(project_id, path, content)

        if is_disk:
            return {"path": path, "mode": "disk"}

        # DB mode: also save to Artifact table
        result = await self.db.execute(
            select(Artifact).where(
                Artifact.project_id == project_id,
                Artifact.path == path,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.content = content
            existing.updated_at = datetime.now(timezone.utc)
            artifact = existing
        else:
            artifact = Artifact(
                project_id=project_id, path=path, content=content,
            )
            self.db.add(artifact)
        await self.db.commit()
        await self.db.refresh(artifact)
        return artifact

    async def _disk_path(self, project_id: int) -> Path:
        project = await self.db.get(Project, project_id)
        base = Path(PROJECTS_DIR) if isinstance(PROJECTS_DIR, str) else PROJECTS_DIR
        if not project:
            return base / str(project_id)
        if project.disk_path:
            return Path(project.disk_path).resolve()
        return base / str(project_id)

    async def _write_disk(self, project_id: int, path: str, content: str):
        pdir = await self._disk_path(project_id)
        pdir.mkdir(parents=True, exist_ok=True)
        file_path = pdir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    async def _read_disk(self, project_id: int, path: str) -> str | None:
        pdir = await self._disk_path(project_id)
        file_path = pdir / path
        if file_path.exists() and file_path.is_file():
            return file_path.read_text(encoding="utf-8")
        return None

    async def _list_disk(self, project_id: int) -> list[dict]:
        pdir = await self._disk_path(project_id)
        if not pdir.exists():
            return []
        entries = []
        for child in sorted(pdir.rglob("*")):
            if child.is_file():
                entries.append({
                    "name": child.name,
                    "path": str(child.relative_to(pdir)),
                    "size": child.stat().st_size,
                })
        return entries

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_filename(code: str) -> str | None:
        for line in code.strip().split("\n")[:5]:
            raw = line.strip()
            # Strip common comment markers
            for marker in ("# ", "// ", "<!-- ", "-->", "-- ", "% ", ";"):
                raw = raw.removeprefix(marker).removesuffix(marker)
            raw = raw.strip()
            for prefix in ("file:", "filename:"):
                if raw.lower().startswith(prefix):
                    name = raw[len(prefix):].strip().strip('"').strip("'")
                    if name and "." in name and not name.startswith("."):
                        return name
        return None

    @staticmethod
    def _suggest_filename(request: str, language: str = "python") -> str:
        ext_map = {"python": ".py", "javascript": ".js", "typescript": ".ts",
                   "rust": ".rs", "go": ".go", "java": ".java", "pll": ".pll",
                   "html": ".html", "css": ".css", "ruby": ".rb"}
        ext = ext_map.get(language, ".py")
        words = re.findall(r'[a-zA-Z]\w+', request)
        keywords = [w for w in words if w.lower() not in {
            "the", "a", "an", "create", "make", "write", "get", "une",
            "function", "that", "this", "with", "and", "pour", "dans",
        }]
        stem = "_".join(keywords[:3]).lower() if keywords else "generated"
        return f"{stem}{ext}"
