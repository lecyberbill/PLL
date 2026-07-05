"""
Agent Coordinator — breaks complex tasks into subtasks using PLL planning.

Flow:
1. Planner agent writes a PLL plan (list of subtask records)
2. Each subtask is dispatched to a PLL-speaking ReAct worker
3. Results are merged with PLL-like summary
"""
import json
import re
from services.llm_proxy import chat_completion
from services.agent_react import AgentReAct

PLL_PLANNER_SYSTEM = """
You are a PLL planning agent. Decompose the user's request into subtasks.
Output ONLY a PLL variable declaration containing a list of subtask records,
with EXACTLY ONE file per subtask, and its required capability:

v subtasks != [
    {description: "what to do", file: "path/to/file.ts", capability: "StorageCap"},
    {description: "another task", file: "path/to/other.ts", capability: "UiCap"}
]

Capabilities available:
- StorageCap: specialized in database schemas, models, migrations, local/remote storage, query optimization.
- UiCap: specialized in frontend pages, React/Vue components, CSS/Tailwind layouts, user experience, responsiveness.
- NetworkCap: specialized in API endpoints, SSE streams, network protocols, middleware, fetch clients.
- LogicCap: specialized in business rules, algorithms, utility functions, data transformations.

Rules:
- ONE file per subtask — never bundle multiple files together.
- File paths are relative to project root (e.g. src/app/page.tsx, NOT project-name/src/...)
- Max 12 subtasks.
- Descriptions are concise (1 sentence max).
- Output ONLY the PLL code, no markdown, no explanations.
- If the task is simple (1 file), return a single-element list.
"""


class AgentCoordinator:
    def __init__(self, project_id: int, backend: str = ""):
        self.project_id = project_id
        self.backend = backend

    @staticmethod
    def _get_capability_instructions(capability: str) -> str:
        inst = {
            "StorageCap": (
                "You are specialized in database design, schemas, models, migrations, local/remote storage, "
                "query optimization, and CRUD operations. Implement robust data-access functions, "
                "proper SQL/ORM mappings, and handle database sessions or files carefully."
            ),
            "UiCap": (
                "You are specialized in user interface, layouts, React/Vue components, styling, responsiveness, "
                "accessibility, and frontend logic. Follow modern UI best practices, use curated CSS variables, "
                "and ensure clean interactive elements."
            ),
            "NetworkCap": (
                "You are specialized in network protocols, API routing, endpoints, SSE streaming, middleware, "
                "fetch requests, and security headers. Create clean, restful endpoints, validate inputs, "
                "and handle CORS and errors correctly."
            ),
            "LogicCap": (
                "You are specialized in business rules, complex algorithms, utility functions, state management, "
                "and data structures. Implement clean, modular logic, optimize runtime performance, and add unit tests."
            )
        }
        return inst.get(capability, inst["LogicCap"])

    async def orchestrate(self, user_message: str, context: str = "") -> dict:
        subtasks = await self._plan(user_message, context)
        if not subtasks:
            agent = AgentReAct(self.project_id, self.backend)
            return await agent.run(user_message, context)

        results = []
        for i, subtask in enumerate(subtasks):
            raw_path = subtask.get("file", "")
            capability = subtask.get("capability", "LogicCap")
            cap_instructions = self._get_capability_instructions(capability)
            
            agent = AgentReAct(self.project_id, self.backend, max_steps=20)
            prompt = (
                f"# Capability required: {capability}\n"
                f"# Specialization Instructions:\n# {cap_instructions}\n\n"
                f"# Subtask {i + 1}/{len(subtasks)}: {subtask['description']}\n"
                f"# Target file: {raw_path}\n"
                f"# IMPORTANT: Write the file at EXACTLY this relative path (no extra directory prefix).\n"
                f"# Main task: {user_message[:300]}\n"
                f"# RULES:\n"
                f"# 1. Write the COMPLETE file content in ONE edit_artifact call — never create empty files.\n"
                f"# 2. Call final_answer when done. DO NOT continue planning.\n"
                f"# 3. Keep it focused: just implement this one subtask.\n"
                f"# Previous subtask result: {results[-1]['result'][:200] if results else 'none'}"
            )
            result = await agent.run(prompt, context)
            
            parts = raw_path.replace("\\", "/").split("/")
            if len(parts) > 1 and parts[0] not in ("src", "app", "lib", "components", "public", "."):
                clean_path = "/".join(parts[1:])
            else:
                clean_path = raw_path
            results.append({
                "subtask": subtask["description"],
                "expected_file": clean_path,
                "capability": capability,
                "result": result.get("answer", ""),
                "code": result.get("code", ""),
                "file_path": result.get("file_path", ""),
            })

        summary_lines = []
        for r in results:
            summary_lines.append(f"  - {r['subtask']}: {r['result']}")
        summary = "\n".join(summary_lines)

        # Post-generation validation: fix empty files and missing deps
        fix_needed = await self._validate_and_fix(user_message, context)
        if fix_needed:
            results.append({
                "subtask": "Fix validation issues",
                "expected_file": "",
                "result": fix_needed,
                "code": "",
                "file_path": "",
            })

        return {
            "answer": f"Completed {len(results)} subtasks:\n{summary}",
            "subtasks": results,
            "code": results[-1].get("code", "") if results else "",
            "file_path": results[-1].get("file_path", "") if results else "",
        }

    async def _validate_and_fix(self, user_message: str, context: str) -> str:
        """Check project for empty files and missing deps, fix them with a ReAct pass."""
        from database import async_session
        from models import Artifact
        from sqlalchemy import select
        import json

        async with async_session() as db:
            files = await db.execute(
                select(Artifact).where(Artifact.project_id == self.project_id)
            )
            files = files.scalars().all()

        empty_files = [f.path for f in files if not f.content.strip()]
        if not empty_files:
            return ""

        agent = AgentReAct(self.project_id, self.backend, max_steps=15)
        fix_prompt = (
            f"The following files are EMPTY (0 bytes): {', '.join(empty_files)}\n"
            f"Main task: {user_message[:300]}\n"
            f"Fill each empty file with COMPLETE working content. "
            f"If package.json is empty, add proper dependencies (next, react, react-dom, typescript, tailwindcss). "
            f"Write ALL content in ONE edit_artifact call per file."
        )
        result = await agent.run(fix_prompt, context)
        return result.get("answer", "Validation fixes applied.")

    async def _plan(self, user_message: str, context: str) -> list[dict]:
        ctx = f"Context:\n{context[:500]}" if context else ""
        prompt = f"{ctx}\n\nUser request: {user_message}"
        result = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=PLL_PLANNER_SYSTEM,
            temperature=0.2,
            backend=self.backend,
        )
        response = result["response"]

        # Extract the PLL v subtasks != [...] pattern
        m = re.search(r'v\s+subtasks\s*!=\s*(\[.*\])', response, re.DOTALL)
        if m:
            pll_list = m.group(1)
            # Convert PLL records {key: val} to JSON {"key": val}
            json_str = re.sub(
                r'(\w+)\s*:\s*('
                r'"[^"]*"|'     # double-quoted string
                r"'[^']*'|"     # single-quoted string
                r'\d+\.?\d*|'   # number
                r'true|false|'  # bool
                r'\[.*?\]|'     # nested list
                r'\{.*?\}'      # nested record
                r')',
                r'"\1": \2',
                pll_list,
                flags=re.DOTALL,
            )
            # Fix single-quoted strings to double-quoted
            json_str = re.sub(r"'([^']*)'", r'"\1"', json_str)
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, list) and len(parsed) >= 1:
                    return parsed[:5]
            except json.JSONDecodeError:
                pass

        # Fallback: try raw JSON array
        fallback = re.search(r'\[.*\]', response, re.DOTALL)
        if fallback:
            try:
                parsed = json.loads(fallback.group())
                if isinstance(parsed, list) and len(parsed) >= 1:
                    return parsed[:5]
            except json.JSONDecodeError:
                pass

        return []
