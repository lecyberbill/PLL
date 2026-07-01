"""
Agent ReAct — PLL-powered reasoning loop.

The agent thinks in PLL (concise inter-agent language)
and calls tools via JSON. Format per message:

    v task != ?("Break down: ...") => TaskList
    {"tool": "edit_artifact", "args": {"path": "app.py", "content": "..."}}
"""
import json
import re
from services.llm_proxy import chat_completion

PLL_QUICK_REF = """
## PLL inter-agent language quick reference

### Variables & Beliefs
v name != "value"                     # declare variable
v plan != ?("Break down: ...") => list  # LLM belief/thought
v code != user_message => "Python"      # semantic transform

### Control flow (colon + newline + indent)
if condition:
    v next != ?("analyze result")

### Semantic operators
v score != a ~ b                       # similarity (0.0-1.0)
v clean != code => "Fix syntax errors"  # LLM transform

### JSON tool call (always after PLL thinking lines)
{"tool": "edit_artifact", "args": {"path": "app.py", "content": "..."}}
"""

TOOL_DESCRIPTIONS = f"""
{PLL_QUICK_REF}

## Available tools (respond with JSON after PLL thinking)

### read_file
Read a file from disk.
{{"tool": "read_file", "args": {{"path": "relative/path"}}}}
Returns the file content.

### write_file
Write content to a file on disk.
{{"tool": "write_file", "args": {{"path": "relative/path", "content": "..."}}}}

### edit_artifact
Save a file to the project (DB + disk).
{{"tool": "edit_artifact", "args": {{"path": "file.py", "content": "..."}}}}

### delete_file
Delete a file.
{{"tool": "delete_file", "args": {{"path": "relative/path"}}}}

### rename_file
Rename/move a file.
{{"tool": "rename_file", "args": {{"old_path": "a.py", "new_path": "b.py"}}}}

### list_dir
List directory contents.
{{"tool": "list_dir", "args": {{"path": "."}}}}

### glob_files
Find files matching a glob pattern.
{{"tool": "glob_files", "args": {{"pattern": "**/*.py", "path": "."}}}}

### grep_files
Search file contents with regex.
{{"tool": "grep_files", "args": {{"pattern": "pattern", "path": ".", "include": "*.py"}}}}

### search_vault
Search the GCA vault for relevant past work.
{{"tool": "search_vault", "args": {{"query": "..."}}}}

### final_answer
Call this when you are done.
{{"tool": "final_answer", "args": {{"text": "Task complete."}}}}
### git_status
Check repository status (branch, modified files, untracked).
{{"tool": "git_status", "args": {{}}}}
### git_commit
Stage all changes and commit with a message (auto-generated if empty).
{{"tool": "git_commit", "args": {{"message": "optional commit message"}}}}
### git_push
Push commits to remote.
{{"tool": "git_push", "args": {{}}}}
### git_log
Show recent commits.
{{"tool": "git_log", "args": {{"count": 5}}}}
### git_init
Initialize a new git repository for this project.
{{"tool": "git_init", "args": {{}}}}
### git_remote
Set the remote origin URL for this project's git repo.
{{"tool": "git_remote", "args": {{"url": "https://github.com/user/repo.git", "branch": "main"}}}}
### git_clone
Clone a remote repository into this project (project must be empty).
{{"tool": "git_clone", "args": {{"url": "https://github.com/user/repo.git"}}}}
### exec_pll
Execute PLL code directly (compile + run via Rust VM). Returns output from render statements.
{{"tool": "exec_pll", "args": {{"code": "render str_concat(\"hello\", \" world\")"}}}}
### web_fetch
Fetch a URL and return its content (HTML or text).
{{"tool": "web_fetch", "args": {{"url": "https://example.com"}}}}
### web_search
Search the web via DuckDuckGo and return top results.
{{"tool": "web_search", "args": {{"query": "Flask CRUD tutorial"}}}}
### edit_file
Replace a specific string in a file (no need to rewrite the whole file).
{{"tool": "edit_file", "args": {{"path": "app.py", "old": "old text", "new": "new text"}}}}
### exec_python
Execute a Python snippet and return its output.
{{"tool": "exec_python", "args": {{"code": "print(2 + 2)"}}}}
### exec_shell
Execute a shell command directly (no two-phase confirmation).
{{"tool": "exec_shell", "args": {{"cmd": "dir /b"}}}}
### diff_files
Compare two files and show the diff.
{{"tool": "diff_files", "args": {{"a": "old.py", "b": "new.py"}}}}
### search_code
Find functions, classes, or symbols by name across the project.
{{"tool": "search_code", "args": {{"name": "create_todo", "path": "."}}}}
### tree
Show the full directory tree of the project.
{{"tool": "tree", "args": {{"path": "."}}}}
### count_tokens
Estimate how many tokens a file would cost (for LLM context budgeting).
{{"tool": "count_tokens", "args": {{"path": "main.py"}}}}
### read_lines
Read specific line range from a file (avoids loading the whole file).
{{"tool": "read_lines", "args": {{"path": "main.py", "start": 1, "end": 50}}}}
### zip_project
Package the entire project into a zip archive.
{{"tool": "zip_project", "args": {{"output": "backup.zip"}}}}
"""


class AgentReAct:
    def __init__(self, project_id: int, backend: str = "", max_steps: int = 15):
        self.project_id = project_id
        self.backend = backend
        self.max_steps = max_steps
        self.history = []
        self._tool_cache = {}
        self._allowed_dir = None

        from services.agent_brain import AgentBrain
        from services.gca_orchestrator import GCAOrchestrator
        from database import async_session
        self._session_factory = async_session
        self._agent_brain_cls = AgentBrain
        self._orch_cls = GCAOrchestrator

    async def _project_dir(self):
        """Return the allowed directory for this project, or None (use BASE_DIR)."""
        if self._allowed_dir:
            return self._allowed_dir
        from database import async_session
        from models import Project
        async with async_session() as db:
            project = await db.get(Project, self.project_id)
            if project and project.disk_path:
                from pathlib import Path
                self._allowed_dir = Path(project.disk_path).resolve()
            else:
                self._allowed_dir = None
        return self._allowed_dir

    async def _assert_allowed(self, path_str: str, action: str = "") -> str | None:
        """Check path is within project scope. Return None if OK, or a permission message."""
        from routes.fs import _resolve
        try:
            fp = _resolve(path_str)
            allowed = await self._project_dir()
            if allowed and not str(fp.resolve()).startswith(str(allowed)):
                return (f"__NEED_PERMISSION__: The path '{path_str}' is outside the project "
                        f"directory ({allowed}). Ask the user: 'Allow writing to {path_str}?'")
            return None
        except Exception as e:
            return f"ERROR: {e}"

    async def _call_llm(self, system: str, messages: list[dict]) -> str:
        result = await chat_completion(
            messages=messages,
            system_prompt=system,
            temperature=0.15,
            backend=self.backend,
        )
        return result["response"]

    async def _execute_tool(self, tool: str, args: dict) -> str:
        from database import async_session
        handler = getattr(self, f"_tool_{tool}", None)
        if not handler:
            return f"ERROR: Unknown tool '{tool}'"
        try:
            async with async_session() as db:
                brain = self._agent_brain_cls(db)
                result = await handler(brain, args)
            return result
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_read_file(self, brain, args: dict) -> str:
        path = args.get("path", "")
        from routes.fs import _resolve
        try:
            fp = _resolve(path)
            allowed = await self._project_dir()
            if allowed and not str(fp.resolve()).startswith(str(allowed)):
                return f"ERROR: Path '{path}' is outside the project directory"
            if not fp.is_file():
                return f"ERROR: File not found: {path}"
            content = fp.read_text(encoding="utf-8")
            return f"Content of {path}:\n```\n{content}\n```"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_write_file(self, brain, args: dict) -> str:
        path = args.get("path", "")
        content = args.get("content", "")
        from routes.fs import _resolve
        # Scope to project directory if available
        allowed = await self._project_dir()
        fp = _resolve(path)
        if allowed and not str(fp.resolve()).startswith(str(allowed)):
            return f"ERROR: Path '{path}' is outside the project directory"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Written {len(content)} bytes to {path}"

    async def _tool_edit_artifact(self, brain, args: dict) -> str:
        pid = args.get("project_id") or self.project_id
        path = args.get("path", "")
        content = args.get("content", "")
        await brain._save_artifact(pid, path, content)
        return f"Saved artifact {path} (project {pid})"

    async def _tool_delete_file(self, brain, args: dict) -> str:
        path = args.get("path", "")
        from routes.fs import _resolve
        fp = _resolve(path)
        if not fp.exists():
            return f"ERROR: Not found: {path}"
        if fp.is_file():
            fp.unlink()
        else:
            import shutil
            shutil.rmtree(fp)
        return f"Deleted {path}"

    async def _tool_rename_file(self, brain, args: dict) -> str:
        old = args.get("old_path", "")
        new = args.get("new_path", "")
        from routes.fs import _resolve
        old_fp = _resolve(old)
        new_fp = _resolve(new)
        if not old_fp.exists():
            return f"ERROR: Not found: {old}"
        new_fp.parent.mkdir(parents=True, exist_ok=True)
        old_fp.rename(new_fp)
        return f"Renamed {old} -> {new}"

    async def _tool_list_dir(self, brain, args: dict) -> str:
        path = args.get("path", ".")
        from routes.fs import _resolve
        fp = _resolve(path)
        if not fp.is_dir():
            return f"ERROR: Not a directory: {path}"
        entries = []
        for child in sorted(fp.iterdir()):
            t = "dir" if child.is_dir() else "file"
            entries.append(f"  [{t}] {child.name}")
        result = "\n".join(entries)
        return f"Contents of {path}:\n{result}" if entries else f"{path} is empty"

    async def _tool_glob_files(self, brain, args: dict) -> str:
        pattern = args.get("pattern", "*")
        path = args.get("path", ".")
        from routes.fs import _resolve
        root = _resolve(path)
        files = []
        for fpath in sorted(root.rglob(pattern)):
            rel = str(fpath.relative_to(root.parent))
            files.append(f"  {rel} ({'dir' if fpath.is_dir() else 'file'})")
        if not files:
            return f"No files matching '{pattern}' in {path}"
        return f"Glob '{pattern}' ({len(files)}):\n" + "\n".join(files)

    async def _tool_grep_files(self, brain, args: dict) -> str:
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        include = args.get("include", "")
        import re as re_mod
        from routes.fs import _resolve
        root = _resolve(path)
        try:
            regex = re_mod.compile(pattern, re_mod.IGNORECASE)
        except Exception as e:
            return f"ERROR: Invalid regex: {e}"
        matches = []
        for fpath in sorted(root.rglob("*")):
            if not fpath.is_file():
                continue
            if include and not fpath.match(include):
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.split("\n"), 1):
                if regex.search(line):
                    rel = str(fpath.relative_to(root.parent))
                    matches.append(f"  {rel}:{i}  {line.strip()[:120]}")
        if not matches:
            return f"No matches for '{pattern}' in {path}"
        return f"Grep '{pattern}' ({len(matches)} matches):\n" + "\n".join(matches[:50])

    async def _tool_search_vault(self, brain, args: dict) -> str:
        pid = args.get("project_id") or self.project_id
        query = args.get("query", "")
        examples = await brain._retrieve_similar_examples(pid, query, top_k=5)
        if not examples:
            return "No relevant vault entries found."
        lines = [f"Vault results for '{query}':"]
        for ex in examples:
            lines.append(f"  - {ex['key']}: {ex['request'][:80]}")
        return "\n".join(lines)

    async def _tool_run_command(self, brain, args: dict) -> str:
        cmd = args.get("command", "")
        if not cmd:
            return "ERROR: No command specified"
        from routes.exec import propose_command, ExecProposeRequest
        try:
            prop = await propose_command(ExecProposeRequest(command=cmd))
            return f"Command proposed: {prop}"
        except Exception as e:
            return f"ERROR proposing command: {e}"

    async def _tool_final_answer(self, brain, args: dict) -> str:
        text = args.get("text", "")
        return f"__FINAL__:{text}"

    async def _tool_git_status(self, brain, args: dict) -> str:
        from routes.git_routes import _git, _git_dir
        from database import async_session
        async with async_session() as db:
            from models import Project
            project = await db.get(Project, self.project_id)
            if not project:
                return "ERROR: Project not found"
            git_dir = _git_dir(project)
            if not (git_dir / ".git").exists():
                return "Not a git repository. Use git_init to create one."
            branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=git_dir)
            status = _git("status", "--porcelain", cwd=git_dir)
            diff = _git("diff", "--stat", cwd=git_dir)
            lines = [f"Branch: {branch['out']}", ""]
            if status["out"]:
                lines.append("Changes:")
                lines.append(status["out"])
            if diff["out"]:
                lines.append("")
                lines.append(diff["out"])
            else:
                lines.append("(clean working tree)")
            return "\n".join(lines)

    async def _tool_git_commit(self, brain, args: dict) -> str:
        from routes.git_routes import _git, _git_dir
        from database import async_session
        async with async_session() as db:
            from models import Project
            project = await db.get(Project, self.project_id)
            if not project:
                return "ERROR: Project not found"
            git_dir = _git_dir(project)
            if not (git_dir / ".git").exists():
                return "Not a git repository. Use git_init first."
            _git("add", "-A", cwd=git_dir)
            msg = args.get("message", "")
            if not msg:
                diff = _git("diff", "--cached", cwd=git_dir)
                if diff["ok"] and diff["out"]:
                    from services.llm_proxy import chat_completion
                    llm = await chat_completion(
                        messages=[{"role": "user", "content": f"Write a git commit message for:\n{diff['out'][:2000]}"}],
                        system_prompt="Short commit message (max 72 chars). Output ONLY the message.",
                        temperature=0.1,
                    )
                    msg = llm["response"].strip().split("\n")[0][:200]
                else:
                    return "Nothing to commit."
            r = _git("commit", "-m", msg, cwd=git_dir)
            if r["ok"]:
                return f"Committed: {msg}"
            return f"Commit failed: {r['err']}"

    async def _tool_git_push(self, brain, args: dict) -> str:
        from routes.git_routes import _git, _git_dir
        from database import async_session
        async with async_session() as db:
            from models import Project
            project = await db.get(Project, self.project_id)
            if not project:
                return "ERROR: Project not found"
            git_dir = _git_dir(project)
            if not (git_dir / ".git").exists():
                return "Not a git repository. Use git_init first."
            r = _git("push", cwd=git_dir)
            if r["ok"]:
                return f"Pushed: {r['out']}"
            # Try setting upstream
            branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=git_dir)
            r2 = _git("push", "--set-upstream", "origin", branch["out"], cwd=git_dir)
            if r2["ok"]:
                return f"Pushed (upstream set): {r2['out']}"
            return f"Push failed: {r2['err']}"

    async def _tool_git_init(self, brain, args: dict) -> str:
        from routes.git_routes import _git, _git_dir, _ensure_repo
        from database import async_session
        async with async_session() as db:
            from models import Project
            project = await db.get(Project, self.project_id)
            if not project:
                return "ERROR: Project not found"
            git_dir = _git_dir(project)
            git_dir.mkdir(parents=True, exist_ok=True)
            if (git_dir / ".git").exists():
                return "Already a git repository."
            _ensure_repo(git_dir)
            return "Git repository initialized."

    async def _tool_git_remote(self, brain, args: dict) -> str:
        from routes.git_routes import _git, _git_dir
        from database import async_session
        async with async_session() as db:
            from models import Project
            project = await db.get(Project, self.project_id)
            if not project:
                return "ERROR: Project not found"
            git_dir = _git_dir(project)
            if not (git_dir / ".git").exists():
                return "Not a git repository. Use git_init first."
            url = args.get("url", "")
            if not url:
                return "ERROR: No URL provided."
            branch = args.get("branch", "main")
            _git("remote", "remove", "origin", cwd=git_dir)
            r = _git("remote", "add", "origin", url, cwd=git_dir)
            if not r["ok"]:
                return f"ERROR: {r['err']}"
            _git("branch", "-M", branch, cwd=git_dir)
            return f"Remote origin set to {url} on branch {branch}."

    async def _tool_git_clone(self, brain, args: dict) -> str:
        from routes.git_routes import _git, _git_dir
        from database import async_session
        async with async_session() as db:
            from models import Project
            project = await db.get(Project, self.project_id)
            if not project:
                return "ERROR: Project not found"
            git_dir = _git_dir(project)
            url = args.get("url", "")
            if not url:
                return "ERROR: No URL provided."
            if git_dir.exists() and list(git_dir.iterdir()):
                return "ERROR: Project directory is not empty."
            git_dir.mkdir(parents=True, exist_ok=True)
            r = _git("clone", url, ".", cwd=git_dir)
            if not r["ok"]:
                return f"Clone failed: {r['err']}"
            return f"Cloned {url} successfully."

    async def _tool_exec_pll(self, brain, args: dict) -> str:
        code = args.get("code", "")
        if not code:
            return "ERROR: No PLL code provided."
        import subprocess, tempfile, os
        from pathlib import Path
        binary = None
        here = Path(__file__).resolve().parent.parent.parent
        for c in [here / "target" / "release" / "pll-cli.exe", here / "target" / "release" / "pll-cli"]:
            if c.exists():
                binary = str(c.resolve())
                break
        if not binary:
            return "ERROR: pll-cli binary not found"
        allowed = await self._project_dir()
        cwd = str(allowed) if allowed else None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".pll", delete=False, encoding="utf-8") as f:
                f.write(code)
                tmp_path = f.name
            r = subprocess.run([binary, "run", "--bc", tmp_path], capture_output=True, text=True, timeout=30, cwd=cwd)
            os.unlink(tmp_path)
            if r.returncode != 0:
                err = r.stderr.strip()[:500]
                return f"PLL error: {err}" if err else "PLL execution failed"
            out = r.stdout.strip()
            return out or "(no output)"
        except subprocess.TimeoutExpired:
            return "ERROR: PLL execution timed out"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_web_fetch(self, brain, args: dict) -> str:
        url = args.get("url", "")
        if not url:
            return "ERROR: No URL provided"
        import urllib.request
        try:
            resp = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "PLL-Agent/1.0"}), timeout=30)
            data = resp.read().decode("utf-8", errors="replace")
            return data[:5000] + ("..." if len(data) > 5000 else "")
        except Exception as e:
            return f"ERROR fetching {url}: {e}"

    async def _tool_web_search(self, brain, args: dict) -> str:
        query = args.get("query", "")
        if not query:
            return "ERROR: No search query"
        import urllib.request, urllib.parse, re
        try:
            # Try DuckDuckGo Lite (lighter HTML, less blocking)
            url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}"
            resp = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15)
            html = resp.read().decode("utf-8", errors="replace")
            results = []
            for m in re.finditer(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
                title = re.sub(r'<[^>]+>', "", m.group(2)).strip()
                link = m.group(1)
                if title and len(title) > 15 and "duckduckgo.com" not in link and "google" not in link:
                    results.append(f"  - {title}\n    {link}")
                    if len(results) >= 5:
                        break
            if results:
                return "\n".join(results)
            # Fallback: fetch search results from textise dot iitty
            return "Search completed but no specific results extracted. Try web_fetch directly."
        except Exception as e:
            return f"ERROR searching: {e}"

    async def _tool_edit_file(self, brain, args: dict) -> str:
        path = args.get("path", "")
        old = args.get("old", "")
        new = args.get("new", "")
        if not path or not old:
            return "ERROR: path and old are required"
        from routes.fs import _resolve
        try:
            fp = _resolve(path)
            if not fp.is_file():
                return f"ERROR: File not found: {path}"
            content = fp.read_text(encoding="utf-8")
            if old not in content:
                return f"ERROR: String not found in {path}"
            new_content = content.replace(old, new, 1)
            fp.write_text(new_content, encoding="utf-8")
            return f"Replaced in {path}: {len(old)} chars -> {len(new)} chars"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_exec_python(self, brain, args: dict) -> str:
        code = args.get("code", "")
        if not code:
            return "ERROR: No Python code provided"
        import subprocess, tempfile, os
        allowed = await self._project_dir()
        cwd = str(allowed) if allowed else None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(code)
                tmp_path = f.name
            r = subprocess.run(["python", tmp_path], capture_output=True, text=True, timeout=15, cwd=cwd)
            os.unlink(tmp_path)
            out = r.stdout.strip()
            err = r.stderr.strip()[:500]
            if r.returncode != 0:
                return f"Python error: {err}" if err else "Python execution failed"
            return out or "(no output)"
        except subprocess.TimeoutExpired:
            return "ERROR: Python execution timed out"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_exec_shell(self, brain, args: dict) -> str:
        cmd = args.get("cmd", "")
        if not cmd:
            return "ERROR: No command provided"
        import subprocess
        allowed = await self._project_dir()
        cwd = str(allowed) if allowed else None
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=cwd)
            out = r.stdout.strip()[:3000]
            err = r.stderr.strip()[:500]
            if r.returncode != 0 and not out:
                return f"Shell error (code {r.returncode}): {err}"
            return out or "(no output)"
        except subprocess.TimeoutExpired:
            return "ERROR: Command timed out (30s)"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_diff_files(self, brain, args: dict) -> str:
        a = args.get("a", "")
        b = args.get("b", "")
        if not a or not b:
            return "ERROR: a and b paths required"
        from routes.fs import _resolve
        try:
            fa, fb = _resolve(a), _resolve(b)
            if not fa.is_file():
                return f"ERROR: File not found: {a}"
            if not fb.is_file():
                return f"ERROR: File not found: {b}"
            ca, cb = fa.read_text(encoding="utf-8"), fb.read_text(encoding="utf-8")
            if ca == cb:
                return "Files are identical."
            import difflib
            diff = difflib.unified_diff(ca.splitlines(), cb.splitlines(),
                                         fromfile=a, tofile=b, lineterm="")
            return "\n".join(list(diff)[:50])
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_search_code(self, brain, args: dict) -> str:
        name = args.get("name", "")
        path = args.get("path", ".")
        if not name:
            return "ERROR: No symbol name provided"
        from routes.fs import _resolve
        import re
        root = _resolve(path)
        if not root.is_dir():
            return f"ERROR: Not a directory: {path}"
        skip_dirs = {".venv", "__pycache__", "node_modules", ".git", "target", ".pytest_cache", "migrations"}
        results = []
        patterns = [
            rf"fn\s+{re.escape(name)}\b",
            rf"def\s+{re.escape(name)}\b",
            rf"class\s+{re.escape(name)}\b",
            rf"async\s+def\s+{re.escape(name)}\b",
            rf"fun\s+{re.escape(name)}\b",
            rf"t\s+{re.escape(name)}\b",
            rf"const\s+{re.escape(name)}\b",
            rf"let\s+{re.escape(name)}\b",
        ]
        compiled = re.compile("|".join(patterns), re.IGNORECASE)
        for fpath in root.rglob("*"):
            if any(p in fpath.parts for p in skip_dirs):
                continue
            if not fpath.is_file():
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.split("\n"), 1):
                if compiled.search(line):
                    rel = str(fpath.relative_to(root.parent))
                    results.append(f"  {rel}:{i}  {line.strip()[:120]}")
                    if len(results) >= 20:
                        return "\n".join(results)
        return "\n".join(results[:20]) if results else f"Symbol '{name}' not found."

    async def _tool_tree(self, brain, args: dict) -> str:
        path = args.get("path", ".")
        from routes.fs import _resolve
        root = _resolve(path)
        if not root.is_dir():
            return f"ERROR: Not a directory: {path}"
        skip = {".venv", "__pycache__", "node_modules", ".git", "target", ".pytest_cache", ".mypy_cache"}
        lines = [f"📁 {root.name}"]
        def _walk(dir_path: Path, prefix: str = ""):
            entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            entries = [e for e in entries if e.name not in skip]
            for i, entry in enumerate(entries):
                is_last = i == len(entries) - 1
                connector = "└── " if is_last else "├── "
                if entry.is_dir():
                    lines.append(f"{prefix}{connector}📁 {entry.name}/")
                    ext = "    " if is_last else "│   "
                    if len(lines) < 80:
                        _walk(entry, prefix + ext)
                elif entry.is_file():
                    size = entry.stat().st_size
                    label = entry.name
                    if size > 1024 * 1024:
                        label = f"{entry.name} ({size // (1024*1024)}MB)"
                    elif size > 1024:
                        label = f"{entry.name} ({size // 1024}KB)"
                    elif size > 0:
                        label = f"{entry.name} ({size}B)"
                    lines.append(f"{prefix}{connector}📄 {label}")
        _walk(root)
        return "\n".join(lines[:80]) + ("\n..." if len(lines) > 80 else "")

    async def _tool_count_tokens(self, brain, args: dict) -> str:
        path = args.get("path", "")
        if not path:
            return "ERROR: No path provided"
        from routes.fs import _resolve
        try:
            fp = _resolve(path)
            if not fp.exists():
                return f"ERROR: Not found: {path}"
            if fp.is_dir():
                total = 0
                files = 0
                for f in fp.rglob("*"):
                    if f.is_file():
                        try:
                            total += len(f.read_text(encoding="utf-8"))
                            files += 1
                        except Exception:
                            pass
                est = total // 4
                return f"Directory: {files} files, {total} chars (~{est} tokens)"
            text = fp.read_text(encoding="utf-8")
            chars = len(text)
            est = chars // 4
            return f"{path}: {chars} chars, ~{est} tokens (est. {est * 2} GPT-4 tokens)"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_read_lines(self, brain, args: dict) -> str:
        path = args.get("path", "")
        start = args.get("start", 1)
        end = args.get("end", None)
        if not path:
            return "ERROR: No path provided"
        from routes.fs import _resolve
        try:
            fp = _resolve(path)
            if not fp.is_file():
                return f"ERROR: Not found: {path}"
            lines = fp.read_text(encoding="utf-8").split("\n")
            total = len(lines)
            s = max(1, int(start)) - 1
            e = min(total, int(end) if end else total)
            selected = lines[s:e]
            result = "\n".join(
                f"{s + i + 1:>6}  {line}"
                for i, line in enumerate(selected)
            )
            return result[:3000] + (f"\n... ({total - e} more lines)" if e < total else "")
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_zip_project(self, brain, args: dict) -> str:
        output = args.get("output", "project.zip")
        from routes.fs import _resolve
        import zipfile
        try:
            root = _resolve(".")
            zip_path = _resolve(output)
            with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(root.rglob("*")):
                    if f.is_file() and ".git" not in f.parts and "__pycache__" not in f.parts:
                        arcname = str(f.relative_to(root))
                        zf.write(str(f), arcname)
            size = zip_path.stat().st_size
            return f"Created {output} ({size} bytes, {size//1024}KB)"
        except Exception as e:
            return f"ERROR: {e}"
        system = (
            "You are an AI coding assistant that thinks in PLL.\n"
            "PLL is a compact inter-agent language for planning, reasoning, AND execution.\n\n"
            "Use exec_pll for deterministic operations (read/write files, data transforms):\n"
            '  {"tool": "exec_pll", "args": {"code": "v c != read_file(\\\"app.py\\\")\\nrender c"}}\n\n'
            "PLL builtins available in exec_pll:\n"
            "  read_file(path) -> str   write_file(path, content)\n"
            "  render(value)            print(value)\n"
            "  str_concat(a, b)         str_length(s)\n"
            "  str_from_num(n)          str_to_num(s)\n"
            "  db_set(k, v)             db_read(k)\n\n"
            "FORMAT for each response:\n"
            "1. PLL thinking lines (variables, beliefs, transforms)\n"
            "2. Then exactly one tool call (JSON or exec_pll)\n\n"
            "Example:\n"
            'v task != "Read project files" => TaskPlan\n'
            '{"tool": "exec_pll", "args": {"code": "v files != read_file(\\\"main.py\\\")\\nrender files"}}\n\n'
            "PLL operators:\n"
            '  v x != "text"           - variable declaration\n'
            '  v x != ?("prompt")      - LLM belief (thinking step)\n'
            "  v x != input => Type     - semantic transform\n\n"
            f"{TOOL_DESCRIPTIONS}\n"
            f"Project ID: {self.project_id}\n"
            f"{context}"
        )

        messages = [{"role": "user", "content": user_message}]
        steps = []
        current_code = ""
        current_file = ""

        for step in range(self.max_steps):
            response = await self._call_llm(system, messages)
            messages.append({"role": "assistant", "content": response})

            tool_call = self._parse_tool_call(response)
            if not tool_call:
                return {"answer": response, "steps": steps, "code": response, "file_path": ""}

            tool = tool_call.get("tool", "")
            args = tool_call.get("args", {})

            if tool == "final_answer":
                text = args.get("text", response)
                return {"answer": text, "steps": steps, "code": current_code, "file_path": current_file}

            if tool in ("edit_artifact", "write_file"):
                current_code = args.get("content", "")
                current_file = args.get("path", "")

            result = await self._execute_tool(tool, args)
            steps.append({"step": step + 1, "tool": tool, "args": args, "result": result[:300]})

            messages.append({"role": "user", "content": f"Result:\n{result}\n\nContinue thinking in PLL, then call next tool:"})

            if len(messages) > 12:
                messages = [messages[0]] + messages[-10:]

        return {"answer": "Max steps reached without final answer.", "steps": steps, "code": current_code, "file_path": current_file}

    @staticmethod
    def _parse_tool_call(text: str) -> dict | None:
        text = text.strip().strip("`").strip()
        start = text.find('{')
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:i + 1]
                        try:
                            obj = json.loads(candidate)
                            if "tool" in obj:
                                return obj
                        except json.JSONDecodeError:
                            pass
                        break
        return None
