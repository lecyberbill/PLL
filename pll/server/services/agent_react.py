"""
Agent ReAct — PLL-powered reasoning loop.

The agent thinks in PLL (concise inter-agent language)
and calls tools via JSON. Format per message:

    v task != ?("Break down: ...") => TaskList
    {"tool": "edit_artifact", "args": {"path": "app.py", "content": "..."}}
"""
import json
import re
import asyncio
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

## Tools

### write_file
Create or overwrite a file with full content.
{{"tool": "write_file", "args": {{"path": "src/app/page.tsx", "content": "..."}}}}

### read_file
Read a file from the project.
{{"tool": "read_file", "args": {{"path": "relative/path"}}}}

### delete_file
Delete a file.
{{"tool": "delete_file", "args": {{"path": "relative/path"}}}}

### list_dir
List directory contents.
{{"tool": "list_dir", "args": {{"path": "."}}}}

### glob_files
Find files matching a glob pattern.
{{"tool": "glob_files", "args": {{"pattern": "**/*.ts", "path": "."}}}}

### grep_files
Search file contents with regex.
{{"tool": "grep_files", "args": {{"pattern": "class ", "path": ".", "include": "*.ts"}}}}

### exec_shell
Execute a shell command (git, npm, etc.).
{{"tool": "exec_shell", "args": {{"cmd": "npm install"}}}}

### probe_path
Check if a file or directory exists on the filesystem. Accepts absolute paths (C:\...) or relative paths.
{{"tool": "probe_path", "args": {{"path": "D:\\project\\src"}}}}

### git_status
Check git status.

### git_commit
Stage all and commit with a message.

### git_init
Initialize git repo for this project.

### web_fetch
Fetch a URL and return content.
{{"tool": "web_fetch", "args": {{"url": "https://..."}}}}

### web_search
Search the web.
{{"tool": "web_search", "args": {{"query": "..."}}}}

### final_answer
Call this when the task is complete.
{{"tool": "final_answer", "args": {{"text": "Done."}}}}
"""


class AgentReAct:
    def __init__(self, project_id: int, backend: str = "", max_steps: int = 15):
        self.project_id = project_id
        self.backend = backend
        self.max_steps = max_steps
        self.history = []
        self._tool_cache = {}
        self._allowed_dir = None

        from database import async_session
        self._session_factory = async_session

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
        fp = _resolve(path_str)
        allowed = await self._project_dir()
        if allowed and not str(fp.resolve()).startswith(str(allowed)):
            return (f"__NEED_PERMISSION__: The path '{path_str}' is outside the project "
                    f"directory ({allowed}). Ask the user: 'Allow writing to {path_str}'?")
        return None

    @staticmethod
    def _parse_tool_calls(text: str) -> list[dict]:
        """Parse ALL JSON tool calls from text. Returns list of {tool, args} dicts."""
        calls = []
        text = text.strip().strip("`").strip()
        start = 0
        while True:
            start = text.find('{', start)
            if start < 0:
                break
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
                                calls.append(obj)
                        except json.JSONDecodeError:
                            pass
                        start = i + 1
                        break
            else:
                break
        return calls

    async def _call_llm(self, system: str, messages: list[dict]) -> str:
        result = await chat_completion(
            messages=messages,
            system_prompt=system,
            temperature=0.15,
            backend=self.backend,
        )
        return result["response"]

    async def _execute_tool(self, tool: str, args: dict) -> str:
        handler = getattr(self, f"_tool_{tool}", None)
        if not handler:
            return f"ERROR: Unknown tool '{tool}'"
        try:
            result = await handler(args)
            return result
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_read_file(self, args: dict) -> str:
        path = args.get("path", "")
        try:
            allowed = await self._project_dir()
            if allowed:
                fp = (allowed / path).resolve()
                if not str(fp).startswith(str(allowed)):
                    return f"ERROR: Path '{path}' is outside the project directory"
            else:
                from routes.fs import _resolve
                fp = _resolve(path)
            if not fp.is_file():
                return f"ERROR: File not found: {path}"
            content = fp.read_text(encoding="utf-8")
            return f"Content of {path}:\n```\n{content}\n```"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_write_file(self, args: dict) -> str:
        path = args.get("path", "")
        content = args.get("content", "")
        if not content.strip():
            return f"ERROR: Refusing to write empty file '{path}'. Provide complete content."
        import re as _re
        file_markers = list(_re.finditer(r'^#\s*file:\s*(\S+)', content, _re.MULTILINE))
        if len(file_markers) > 1:
            results = []
            parts = _re.split(r'^#\s*file:\s*\S+\s*\r?\n?', content, flags=_re.MULTILINE)
            for i, marker in enumerate(file_markers):
                fpath = marker.group(1)
                fcontent = parts[i + 1].strip() if i + 1 < len(parts) else ""
                if fcontent:
                    sub = await self._tool_write_file({"path": fpath, "content": fcontent})
                    results.append(sub)
            msg = "\n".join(results) if results else "ERROR: no valid files extracted"
            print(f"[PLL_REACT] Split {len(file_markers)} files from '{path}': {msg[:100]}")
            return msg
        # Strip single file header if present
        content = _re.sub(r'^#\s*file:\s*\S+\s*\r?\n?', '', content, count=1)
        # Resolve relative to project directory, not BASE_DIR
        allowed = await self._project_dir()
        if allowed:
            fp = (allowed / path).resolve()
            if not str(fp).startswith(str(allowed)):
                return f"ERROR: Path '{path}' is outside the project directory"
        else:
            from routes.fs import _resolve
            fp = _resolve(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"Written {len(content)} bytes to {path}"

    async def _tool_delete_file(self, args: dict) -> str:
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

    async def _tool_rename_file(self, args: dict) -> str:
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

    async def _tool_list_dir(self, args: dict) -> str:
        path = args.get("path", ".")
        allowed = await self._project_dir()
        if allowed:
            fp = (allowed / path).resolve()
        else:
            from routes.fs import _resolve
            fp = _resolve(path)
        if not fp.is_dir():
            return f"ERROR: Not a directory: {path}"
        entries = []
        for child in sorted(fp.iterdir()):
            if child.name.startswith("."):
                continue
            t = "dir" if child.is_dir() else "file"
            entries.append(f"  [{t}] {child.name}")
        result = "\n".join(entries)
        return f"Contents of {path}:\n{result}" if entries else f"{path} is empty"

    async def _tool_glob_files(self, args: dict) -> str:
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

    async def _tool_grep_files(self, args: dict) -> str:
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

    async def _tool_search_vault(self, args: dict) -> str:
        pid = args.get("project_id") or self.project_id
        query = args.get("query", "")
        examples = await brain._retrieve_similar_examples(pid, query, top_k=5)
        if not examples:
            return "No relevant vault entries found."
        lines = [f"Vault results for '{query}':"]
        for ex in examples:
            lines.append(f"  - {ex['key']}: {ex['request'][:80]}")
        return "\n".join(lines)

    async def _tool_publish_package(self, args: dict) -> str:
        """Publish a GCA vault entry as a PLL package."""
        name = args.get("name", "")
        if not name:
            return "ERROR: package name is required"
        from database import async_session
        async with async_session() as db:
            from models import Package, GCAVault
            from sqlalchemy import select
            existing = await db.execute(select(Package).where(Package.name == name))
            if existing.scalar_one_or_none():
                return f"ERROR: Package '{name}' already exists"
            version = args.get("version", "0.1.0")
            description = args.get("description", "Published from GCA vault")
            author = args.get("author", "PLL Agent")
            source = args.get("source", "")
            if not source and self.project_id:
                vault_result = await db.execute(
                    select(GCAVault).where(GCAVault.project_id == self.project_id)
                        .order_by(GCAVault.created_at.desc()).limit(3)
                )
                entries = vault_result.scalars().all()
                if entries:
                    source = "\n\n".join(f"# {e.key}\n{e.content}" for e in entries)
            pkg = Package(name=name, version=version, description=description,
                          author=author, source_content=source)
            db.add(pkg)
            await db.commit()
            return f"Package '{name}' v{version} published ({len(source)} chars)."

    async def _tool_run_command(self, args: dict) -> str:
        cmd = args.get("command", "")
        if not cmd:
            return "ERROR: No command specified"
        from routes.exec import propose_command, ExecProposeRequest
        try:
            prop = await propose_command(ExecProposeRequest(command=cmd))
            return f"Command proposed: {prop}"
        except Exception as e:
            return f"ERROR proposing command: {e}"

    async def _tool_final_answer(self, args: dict) -> str:
        text = args.get("text", "")
        return f"__FINAL__:{text}"

    async def _tool_git_status(self, args: dict) -> str:
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

    async def _tool_git_commit(self, args: dict) -> str:
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

    async def _tool_git_push(self, args: dict) -> str:
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

    async def _tool_git_init(self, args: dict) -> str:
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

    async def _tool_git_remote(self, args: dict) -> str:
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

    async def _tool_git_clone(self, args: dict) -> str:
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

    async def _tool_exec_pll(self, args: dict) -> str:
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

    async def _tool_web_fetch(self, args: dict) -> str:
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

    async def _tool_web_search(self, args: dict) -> str:
        query = args.get("query", "")
        if not query:
            return "ERROR: No search query"
        import urllib.request, urllib.parse, json, re
        from config import GOOGLE_API_KEY, GOOGLE_CX

        # Google Custom Search (when credentials configured)
        if GOOGLE_API_KEY and GOOGLE_CX:
            try:
                url = f"https://www.googleapis.com/customsearch/v1?key={urllib.parse.quote(GOOGLE_API_KEY)}&cx={urllib.parse.quote(GOOGLE_CX)}&q={urllib.parse.quote(query)}"
                resp = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "PLL-Agent/1.0"}), timeout=15)
                data = json.loads(resp.read().decode())
                items = data.get("items", [])
                if items:
                    results = []
                    for item in items[:5]:
                        title = item.get("title", "")
                        link = item.get("link", "")
                        snippet = item.get("snippet", "")[:200]
                        results.append(f"  - {title}\n    {link}\n    {snippet}")
                    return "\n".join(results)
            except Exception as e:
                return f"Google search error: {e}"

        # Fallback: DuckDuckGo Lite
        try:
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
            return "No search results found."
        except Exception as e:
            return f"Search error: {e}"

    async def _tool_edit_file(self, args: dict) -> str:
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

    async def _tool_exec_python(self, args: dict) -> str:
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

    async def _tool_exec_shell(self, args: dict) -> str:
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

    async def _tool_probe_path(self, args: dict) -> str:
        """Check if a path exists (file or directory). Accepts absolute or relative paths."""
        path = args.get("path", "")
        if not path:
            return "ERROR: No path provided"
        from pathlib import Path
        fp = Path(path).resolve()
        if not fp.exists():
            return f"Path does not exist: {path}"
        if fp.is_dir():
            entries = [e.name for e in fp.iterdir() if not e.name.startswith(".")]
            children = "\n".join(f"  {'📁' if (fp/e).is_dir() else '📄'} {e}" for e in sorted(entries)[:30])
            extra = f"\n  ... and {len(entries) - 30} more" if len(entries) > 30 else ""
            return f"📁 Directory: {fp}\n{children}{extra}"
        else:
            size = fp.stat().st_size
            return f"📄 File: {fp} ({size} bytes)"

    async def _tool_diff_files(self, args: dict) -> str:
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

    async def _tool_search_code(self, args: dict) -> str:
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

    async def _tool_tree(self, args: dict) -> str:
        path = args.get("path", ".")
        allowed = await self._project_dir()
        if allowed:
            from pathlib import Path
            root = (allowed / path).resolve()
        else:
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

    async def _tool_count_tokens(self, args: dict) -> str:
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

    async def _tool_read_lines(self, args: dict) -> str:
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

    async def _tool_zip_project(self, args: dict) -> str:
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

    async def run(self, user_message: str, context: str = "", step_callback=None) -> dict:
        """ReAct loop. step_callback(steps_list, step_info, current_step, max_steps) is called after each tool execution for SSE."""
        system = (
            "You are an AI coding assistant that thinks in PLL.\n\n"
            "PLL is for planning — follow PLL with a JSON tool call.\n"
            "You can also respond with plain text (no PLL, no tool) when answering a question.\n\n"
            "IMPORTANT: The tool names below (write_file, probe_path, etc.) are BUILT-IN COMMANDS.\n"
            "When the user says \"use probe_path\" or \"call write_file\", they mean the built-in tool,\n"
            "NOT a file to create. Never write a file whose name matches a built-in tool.\n\n"
            "PLL quick reference:\n"
            '  v x != "text"           - variable\n'
            '  v x != ?("prompt")      - LLM belief\n'
            '  {"tool": "...", "args": {...}}  - tool call\n\n'
            "Rules:\n"
            "- Write COMPLETE file content in one write_file call (never empty then edit).\n"
            "- Prefer writing multiple files in parallel (multiple tool calls per response).\n"
            "- Call final_answer only when ALL work is finished.\n\n"
            f"{TOOL_DESCRIPTIONS}\n"
            f"Project ID: {self.project_id}\n"
            f"{context}"
        )

        messages = [{"role": "user", "content": user_message}]
        steps = []
        current_code = ""
        current_file = ""
        accumulated_answer = ""

        for step in range(self.max_steps):
            response = await self._call_llm(system, messages)
            messages.append({"role": "assistant", "content": response})

            # Extract text before the first tool call as thinking/answer
            text_before_call = response.strip()
            first_brace = text_before_call.find('{"tool":')
            if first_brace >= 0:
                text_before_call = text_before_call[:first_brace].strip()
            if text_before_call and not text_before_call.startswith('v ') and not text_before_call.startswith('{'):
                accumulated_answer = text_before_call

            tool_calls = self._parse_tool_calls(response)
            if not tool_calls:
                final = {"answer": response, "steps": steps, "code": response, "file_path": ""}
                if accumulated_answer:
                    final["thinking"] = accumulated_answer
                return final

            # If agent has meaningful text AND also tool calls, respond with the text now
            # But only after at least one tool has been executed (don't cut off first response)
            if accumulated_answer and len(steps) > 0:
                final = {"answer": accumulated_answer, "steps": steps, "code": current_code, "file_path": current_file}
                if step_callback:
                    await step_callback(steps, {"tool": "final_answer", "args": {}, "result": accumulated_answer}, step + 1, self.max_steps)
                return final

            # Group tools: run independent (read) tools in parallel, sequential ones one by one
            READ_ONLY = {"read_file", "list_dir", "glob_files", "grep_files", "search_vault",
                         "git_status", "git_log", "web_fetch", "web_search", "search_code",
                         "tree", "count_tokens", "read_lines", "diff_files"}

            for tool_call in tool_calls:
                tool = tool_call.get("tool", "")
                args = tool_call.get("args", {})

                if tool == "final_answer":
                    text = args.get("text", response)
                    if step_callback:
                        await step_callback(steps, {"tool": tool, "args": args, "result": text}, step + 1, self.max_steps)
                    return {"answer": text, "steps": steps, "code": current_code, "file_path": current_file}

                if tool in ("edit_artifact", "write_file"):
                    current_code = args.get("content", "")
                    current_file = args.get("path", "")

            # Run independent tools in parallel
            parallel_tools = [tc for tc in tool_calls if tc.get("tool") in READ_ONLY]
            sequential_tools = [tc for tc in tool_calls if tc.get("tool") not in READ_ONLY]
            last_result = "done"

            if parallel_tools:
                async def _run_one(tc):
                    tool, args = tc.get("tool", ""), tc.get("args", {})
                    result = await self._execute_tool(tool, args)
                    return {"tool": tool, "args": args, "result": result[:300]}

                parallel_results = await asyncio.gather(*[_run_one(tc) for tc in parallel_tools])
                for pr in parallel_results:
                    steps.append({"step": step + 1, **pr, "thinking": accumulated_answer})
                    last_result = pr["result"]
                    if step_callback:
                        await step_callback(steps, {"thinking": accumulated_answer, **pr}, step + 1, self.max_steps)

            for tc in sequential_tools:
                tool, args = tc.get("tool", ""), tc.get("args", {})
                result = await self._execute_tool(tool, args)
                step_info = {"tool": tool, "args": args, "result": result[:300], "thinking": accumulated_answer}
                steps.append({"step": step + 1, **step_info})
                last_result = step_info["result"]
                if step_callback:
                    await step_callback(steps, step_info, step + 1, self.max_steps)

            messages.append({"role": "user", "content": f"Result:\n{last_result}\n\nContinue thinking in PLL, then call next tool:"})

            if len(messages) > 12:
                messages = [messages[0]] + messages[-10:]

        final = {"answer": "Max steps reached without final answer.", "steps": steps, "code": current_code, "file_path": current_file}
        if accumulated_answer:
            final["thinking"] = accumulated_answer
        return final

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
