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
You are a PLL planning agent. Write a PLL program that decomposes the user's
request into independent subtasks. Output ONLY a PLL variable declaration
containing a list of subtask records:

v subtasks != [
    {description: "what to do", file: "target_file.py"},
    {description: "another task", file: "other.py"}
]

Rules:
- Each subtask produces one file (or a small set of files)
- Descriptions are concise (1 sentence max)
- max 5 subtasks
- Output ONLY the PLL code, no markdown, no explanations
- If the task is simple (1 file), return a single-element list
"""


class AgentCoordinator:
    def __init__(self, project_id: int, backend: str = ""):
        self.project_id = project_id
        self.backend = backend

    async def orchestrate(self, user_message: str, context: str = "") -> dict:
        subtasks = await self._plan(user_message, context)
        if not subtasks:
            agent = AgentReAct(self.project_id, self.backend)
            return await agent.run(user_message, context)

        results = []
        for i, subtask in enumerate(subtasks):
            agent = AgentReAct(self.project_id, self.backend)
            prompt = (
                f"# Subtask {i + 1}: {subtask['description']}\n"
                f"# File: {subtask.get('file', 'unknown')}\n"
                f"# Main task: {user_message[:200]}\n"
                f"# Previous: {results[-1]['result'][:200] if results else 'none'}"
            )
            result = await agent.run(prompt, context)
            results.append({
                "subtask": subtask["description"],
                "expected_file": subtask.get("file", ""),
                "result": result.get("answer", ""),
                "code": result.get("code", ""),
                "file_path": result.get("file_path", ""),
            })

        summary_lines = []
        for r in results:
            summary_lines.append(f"  - {r['subtask']}: {r['result'][:200]}")
        summary = "\n".join(summary_lines)

        return {
            "answer": f"Completed {len(results)} subtasks:\n{summary}",
            "subtasks": results,
            "code": results[-1].get("code", "") if results else "",
            "file_path": results[-1].get("file_path", "") if results else "",
        }

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
