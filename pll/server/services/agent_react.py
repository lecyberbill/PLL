"""
[WFGY] Zone: SAFE | λ: 0.5 | Fallbacks: 4/AST, XML, Simple XML, Backticks Fallback | Action: Support backticks as string quotes in tool calling & scope file tools
"""
import json
import re
import asyncio
import ast
from services.llm_proxy import chat_completion

PLL_QUICK_REF = """
## PLL inter-agent language quick reference

### Variables & Beliefs
v name != "value"                     # declare variable
v plan != ?("Break down: ...") => list  # LLM belief/thought

### Tool calls (function call syntax)
read_file("app.py")                   # read a file
write_file("app.py", "content")       # write a file
list_dir(".")                         # list directory
exec_shell("npm install")             # run a command
probe_path("D:\\folder")             # check if path exists
run_pll("render \"hello\"")           # compile & execute PLL code
"""

def parse_write_file_fallback(call_str: str) -> dict | None:
    import re
    call_str_clean = call_str.strip()
    # Try triple backticks first
    m = re.match(r'^write_file\s*\(\s*["\']([^"\']+)["\']\s*,\s*`{3}([\s\S]*?)`{3}\s*\)', call_str_clean)
    if m:
        return {"tool": "write_file", "args_list": [m.group(1), m.group(2)]}
    # Try single backticks
    m = re.match(r'^write_file\s*\(\s*["\']([^"\']+)["\']\s*,\s*`([\s\S]*?)`\s*\)', call_str_clean)
    if m:
        return {"tool": "write_file", "args_list": [m.group(1), m.group(2)]}
    # Try triple double quotes
    m = re.match(r'^write_file\s*\(\s*["\']([^"\']+)["\']\s*,\s*"""([\s\S]*?)"""\s*\)', call_str_clean)
    if m:
        return {"tool": "write_file", "args_list": [m.group(1), m.group(2)]}
    # Try triple single quotes
    m = re.match(r'^write_file\s*\(\s*["\']([^"\']+)["\']\s*,\s*\'\'\'([\s\S]*?)\'\'\'\s*\)', call_str_clean)
    if m:
        return {"tool": "write_file", "args_list": [m.group(1), m.group(2)]}
    # Try normal double quotes
    m = re.match(r'^write_file\s*\(\s*["\']([^"\']+)["\']\s*,\s*"([\s\S]*?)"\s*\)', call_str_clean)
    if m:
        return {"tool": "write_file", "args_list": [m.group(1), m.group(2)]}
    # Try normal single quotes
    m = re.match(r'^write_file\s*\(\s*["\']([^"\']+)["\']\s*,\s*\'([\s\S]*?)\'\s*\)', call_str_clean)
    if m:
        return {"tool": "write_file", "args_list": [m.group(1), m.group(2)]}
    return None

def parse_pll_call(call_str: str) -> dict | None:
    call_str_clean = call_str.strip()
    try:
        tree = ast.parse(call_str_clean)
        if not tree.body:
            return None
        node = tree.body[0]
        call_node = None
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call_node = node.value
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call_node = node.value
        elif isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and isinstance(node.comparators[0], ast.Call):
            call_node = node.comparators[0]
        
        if not call_node:
            for subnode in ast.walk(node):
                if isinstance(subnode, ast.Call):
                    call_node = subnode
                    break
                    
        if call_node and isinstance(call_node.func, ast.Name):
            tool_name = call_node.func.id
            args_list = []
            for arg in call_node.args:
                if isinstance(arg, ast.Constant):
                    args_list.append(arg.value)
                elif isinstance(arg, ast.Str):
                    args_list.append(arg.s)
                elif isinstance(arg, ast.Num):
                    args_list.append(arg.n)
                else:
                    args_list.append(ast.unparse(arg) if hasattr(ast, 'unparse') else str(arg))
            return {"tool": tool_name, "args_list": args_list}
    except Exception:
        if call_str_clean.startswith("write_file"):
            parsed = parse_write_file_fallback(call_str_clean)
            if parsed:
                return parsed
        return None

def map_args(tool: str, args_list: list) -> dict:
    args = {}
    if tool == "write_file":
        if len(args_list) >= 1: args["path"] = args_list[0]
        if len(args_list) >= 2: args["content"] = args_list[1]
    elif tool in ("read_file", "delete_file", "list_dir", "probe_path", "list_symbols"):
        if len(args_list) >= 1: args["path"] = args_list[0]
    elif tool == "glob_files":
        if len(args_list) >= 1: args["pattern"] = args_list[0]
        if len(args_list) >= 2: args["path"] = args_list[1]
    elif tool == "grep_files":
        if len(args_list) >= 1: args["pattern"] = args_list[0]
        if len(args_list) >= 2: args["path"] = args_list[1]
        if len(args_list) >= 3: args["include"] = args_list[2]
    elif tool in ("exec_shell", "start_task"):
        if len(args_list) >= 1: args["cmd"] = args_list[0]
    elif tool == "web_fetch":
        if len(args_list) >= 1: args["url"] = args_list[0]
    elif tool == "web_search":
        if len(args_list) >= 1: args["query"] = args_list[0]
    elif tool == "final_answer":
        if len(args_list) >= 1: args["text"] = args_list[0]
    elif tool == "rename_file":
        if len(args_list) >= 1: args["old_path"] = args_list[0]
        if len(args_list) >= 2: args["new_path"] = args_list[1]
    elif tool == "zip_project":
        if len(args_list) >= 1: args["output"] = args_list[0]
    elif tool == "replace_content":
        if len(args_list) >= 1: args["path"] = args_list[0]
        if len(args_list) >= 2: args["target"] = args_list[1]
        if len(args_list) >= 3: args["replacement"] = args_list[2]
    elif tool in ("get_task_status", "kill_task"):
        if len(args_list) >= 1: args["task_id"] = args_list[0]
    elif tool == "ask_expert":
        if len(args_list) >= 1: args["prompt"] = args_list[0]
    elif tool in ("run_pll", "exec_pll"):
        if len(args_list) >= 1: args["code"] = args_list[0]
    return args

TOOL_DESCRIPTIONS = f"""
{PLL_QUICK_REF}

## Tools

### write_file(path, content)
Create or overwrite a file with full content. Use triple quotes for multi-line content.
write_file("src/app/page.tsx", "content...")

### read_file(path)
Read a file from the project.
read_file("relative/path")

### delete_file(path)
Delete a file.
delete_file("relative/path")

### list_dir(path)
List directory contents.
list_dir(".")

### glob_files(pattern, path)
Find files matching a glob pattern.
glob_files("**/*.ts", ".")

### grep_files(pattern, path, include)
Search file contents with regex.
grep_files("class ", ".", "*.ts")

### exec_shell(cmd)
Execute a shell command (git, npm, etc.).
exec_shell("npm install")

### probe_path(path)
Check if a file or directory exists.
probe_path("D:\\\\project\\\\src")

### web_fetch(url)
Fetch a URL and return content.
web_fetch("https://...")

### web_search(query)
Search the web.
web_search("query...")

### replace_content(path, target, replacement)
Replace a UNIQUE occurrence of target with replacement in a file. Very useful to edit files without rewriting them entirely.
replace_content("path/to/file.py", "def old_func():", "def new_func():")

### start_task(cmd)
Start a background task/process and return a task ID.
start_task("python server.py")

### get_task_status(task_id)
Get running state and stdout/stderr logs of a background task.
get_task_status("task123")

### kill_task(task_id)
Terminate a running background task.
kill_task("task123")

### list_tasks()
List all active background tasks.
list_tasks()

### list_symbols(path)
List all classes, functions, and methods defined in a code file.
list_symbols("src/parser.py")

### ask_expert(prompt)
Ask another expert AI model for advice, a second opinion, or a code review.
ask_expert("Why does this test fail? [code snippet]")

### run_pll(code)
Compile and execute a snippet of PLL code locally. Use this to do deterministic mathematical calculations or logical validations. Returns output stdout and stderr.
run_pll("v a != 5\nrender str_from_num(a)")

### final_answer(text)
Call this when the task is complete.
final_answer("Done.")
"""


class AgentReAct:
    ACTIVE_TASKS = {}

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

    async def _resolve_path(self, path_str: str):
        """Resolve a path relative to the project directory, with fallback and safety checks. Returns a Path object."""
        from pathlib import Path
        allowed = await self._project_dir()
        if allowed:
            fp = Path(path_str)
            if not fp.is_absolute():
                fp = (allowed / path_str).resolve()
            else:
                fp = fp.resolve()
            if not fp.is_relative_to(allowed.resolve()):
                raise ValueError(f"Path '{path_str}' is outside the project directory")
            return fp
        else:
            from routes.fs import _resolve
            return _resolve(path_str)

    async def _assert_allowed(self, path_str: str, action: str = "") -> str | None:
        """Check path is within project scope. Return None if OK, or a permission message."""
        from pathlib import Path
        fp = Path(path_str).resolve()
        allowed = await self._project_dir()
        if allowed:
            allowed_resolved = Path(allowed).resolve()
            if not fp.is_relative_to(allowed_resolved):
                return (f"__NEED_PERMISSION__: The path '{path_str}' is outside the project "
                        f"directory ({allowed}). Ask the user: 'Allow writing to {path_str}'?")
        return None

    @staticmethod
    def _parse_tool_calls(text: str) -> list[dict]:
        """Parse ALL PLL function calls or XML tool calls from text. Returns list of {tool, args} dicts."""
        calls = []
        known_tools = {
            "write_file", "read_file", "delete_file", "list_dir", "glob_files", 
            "grep_files", "exec_shell", "probe_path", "web_fetch", "web_search", 
            "final_answer", "rename_file", "zip_project", "replace_content",
            "start_task", "get_task_status", "kill_task", "list_tasks", "list_symbols", "ask_expert"
        }

        # 1. Fallback: Parse XML-style tool calls (e.g. from DeepSeek or internal formats)
        if "<tool_call>" in text:
            import re as _re
            pattern = _re.compile(r'<tool_call>(.*?)</tool_call>', _re.DOTALL)
            for match in pattern.finditer(text):
                block = match.group(1)
                name_match = _re.search(r'<tool_name>(.*?)</tool_name>', block)
                if not name_match:
                    continue
                tool_name = name_match.group(1).strip()
                if tool_name in known_tools:
                    params = {}
                    param_block_match = _re.search(r'<parameters>(.*?)</parameters>', block, _re.DOTALL)
                    if param_block_match:
                        param_block = param_block_match.group(1)
                        for p_match in _re.finditer(r'<([^>]+)>(.*?)</\1>', param_block, _re.DOTALL):
                            params[p_match.group(1).strip()] = p_match.group(2).strip()
                    calls.append({"tool": tool_name, "args": params})
            if calls:
                return calls

        # 2. Fallback: Parse direct simple XML tags for known tools (e.g. <read_file>path</read_file>)
        import re as _re
        for tool in known_tools:
            pattern = _re.compile(rf'<{tool}(?:\s+([^>]*))?>([\s\S]*?)</{tool}>', _re.IGNORECASE)
            for match in pattern.finditer(text):
                attrs_str = match.group(1) or ""
                inner_content = match.group(2).strip()
                args = {}
                if attrs_str:
                    path_attr = _re.search(r'path=["\']([^"\']+)["\']', attrs_str)
                    if path_attr:
                        args["path"] = path_attr.group(1)
                    cmd_attr = _re.search(r'cmd=["\']([^"\']+)["\']', attrs_str)
                    if cmd_attr:
                        args["cmd"] = cmd_attr.group(1)
                path_tag = _re.search(r'<path>([\s\S]*?)</path>', inner_content, _re.IGNORECASE)
                content_tag = _re.search(r'<content>([\s\S]*?)</content>', inner_content, _re.IGNORECASE)
                if path_tag:
                    args["path"] = path_tag.group(1).strip()
                if content_tag:
                    args["content"] = content_tag.group(1)
                if tool == "write_file" and "content" not in args:
                    if "path" in args:
                        args["content"] = inner_content
                    else:
                        lines = [line for line in inner_content.splitlines() if line.strip()]
                        if lines:
                            first_line = lines[0].strip()
                            if (first_line.startswith("/") or first_line.startswith("./") or 
                                _re.search(r'^[a-zA-Z0-9_\-\.\/]+$', first_line)):
                                args["path"] = first_line
                                args["content"] = "\n".join(inner_content.splitlines()[1:])
                            else:
                                args["path"] = first_line
                                args["content"] = "\n".join(inner_content.splitlines()[1:])
                if not args and inner_content:
                    if tool in ("read_file", "delete_file", "list_dir", "probe_path"):
                        args["path"] = inner_content
                    elif tool == "exec_shell":
                        args["cmd"] = inner_content
                    elif tool == "final_answer":
                        args["text"] = inner_content
                if args:
                    calls.append({"tool": tool, "args": args})

        if calls:
            return calls

        text_len = len(text)
        i = 0
        while i < text_len:
            found_tool = None
            found_pos = -1
            for tool in known_tools:
                pos = text.find(tool + "(", i)
                if pos >= 0 and (found_pos == -1 or pos < found_pos):
                    found_pos = pos
                    found_tool = tool
            
            if found_tool is None:
                break
                
            pos = found_pos + len(found_tool) + 1
            depth = 1
            in_quote = None  # None, '"', "'", '"""', "'''", '`', '```'
            quote_esc = False
            
            while pos < text_len and depth > 0:
                char = text[pos]
                if not in_quote:
                    if text[pos:pos+3] == '"""':
                        in_quote = '"""'
                        pos += 2
                    elif text[pos:pos+3] == "'''":
                        in_quote = "'''"
                        pos += 2
                    elif text[pos:pos+3] == '```':
                        in_quote = '```'
                        pos += 2
                    elif char == '"':
                        in_quote = '"'
                    elif char == "'":
                        in_quote = "'"
                    elif char == '`':
                        in_quote = '`'
                    elif char == '(':
                        depth += 1
                    elif char == ')':
                        depth -= 1
                else:
                    if quote_esc:
                        quote_esc = False
                    elif char == '\\':
                        quote_esc = True
                    elif in_quote == '"""' and text[pos:pos+3] == '"""':
                        in_quote = None
                        pos += 2
                    elif in_quote == "'''" and text[pos:pos+3] == "'''":
                        in_quote = None
                        pos += 2
                    elif in_quote == '```' and text[pos:pos+3] == '```':
                        in_quote = None
                        pos += 2
                    elif char == in_quote:
                        in_quote = None
                pos += 1
                
            if depth == 0:
                call_candidate = text[found_pos:pos]
                parsed = parse_pll_call(call_candidate)
                if parsed and parsed["tool"] in known_tools:
                    mapped_args = map_args(parsed["tool"], parsed["args_list"])
                    calls.append({"tool": parsed["tool"], "args": mapped_args})
                i = pos
            else:
                i = found_pos + 1
                
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
            fp = await self._resolve_path(path)
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
        try:
            fp = await self._resolve_path(path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
            return f"Written {len(content)} bytes to {path}"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_delete_file(self, args: dict) -> str:
        path = args.get("path", "")
        try:
            fp = await self._resolve_path(path)
            if not fp.exists():
                return f"ERROR: Not found: {path}"
            if fp.is_file():
                fp.unlink()
            else:
                import shutil
                shutil.rmtree(fp)
            return f"Deleted {path}"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_rename_file(self, args: dict) -> str:
        old = args.get("old_path", "")
        new = args.get("new_path", "")
        try:
            old_fp = await self._resolve_path(old)
            new_fp = await self._resolve_path(new)
            if not old_fp.exists():
                return f"ERROR: Not found: {old}"
            new_fp.parent.mkdir(parents=True, exist_ok=True)
            old_fp.rename(new_fp)
            return f"Renamed {old} -> {new}"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_list_dir(self, args: dict) -> str:
        path = args.get("path", ".")
        try:
            fp = await self._resolve_path(path)
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
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_glob_files(self, args: dict) -> str:
        pattern = args.get("pattern", "*")
        path = args.get("path", ".")
        try:
            root = await self._resolve_path(path)
            files = []
            for fpath in sorted(root.rglob(pattern)):
                rel = str(fpath.relative_to(root.parent))
                files.append(f"  {rel} ({'dir' if fpath.is_dir() else 'file'})")
            if not files:
                return f"No files matching '{pattern}' in {path}"
            return f"Glob '{pattern}' ({len(files)}):\n" + "\n".join(files)
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_grep_files(self, args: dict) -> str:
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        include = args.get("include", "")
        import re as re_mod
        try:
            root = await self._resolve_path(path)
            regex = re_mod.compile(pattern, re_mod.IGNORECASE)
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
        except Exception as e:
            return f"ERROR: {e}"
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

    async def _tool_run_pll(self, args: dict) -> str:
        return await self._tool_exec_pll(args)

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
            r = subprocess.run([binary, "run", "--bc", tmp_path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, cwd=cwd)
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
        try:
            fp = await self._resolve_path(path)
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
            r = subprocess.run(["python", tmp_path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, cwd=cwd)
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
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, cwd=cwd)
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
        try:
            fp = await self._resolve_path(path)
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
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_diff_files(self, args: dict) -> str:
        a = args.get("a", "")
        b = args.get("b", "")
        if not a or not b:
            return "ERROR: a and b paths required"
        try:
            fa = await self._resolve_path(a)
            fb = await self._resolve_path(b)
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
        import re
        try:
            root = await self._resolve_path(path)
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
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_tree(self, args: dict) -> str:
        path = args.get("path", ".")
        try:
            root = await self._resolve_path(path)
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
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_count_tokens(self, args: dict) -> str:
        path = args.get("path", "")
        if not path:
            return "ERROR: No path provided"
        try:
            fp = await self._resolve_path(path)
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
        try:
            fp = await self._resolve_path(path)
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
        import zipfile
        try:
            root = await self._resolve_path(".")
            zip_path = await self._resolve_path(output)
            with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(root.rglob("*")):
                    if f.is_file() and ".git" not in f.parts and "__pycache__" not in f.parts:
                        arcname = str(f.relative_to(root))
                        zf.write(str(f), arcname)
            size = zip_path.stat().st_size
            return f"Created {output} ({size} bytes, {size//1024}KB)"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_replace_content(self, args: dict) -> str:
        path = args.get("path", "")
        target = args.get("target", "")
        replacement = args.get("replacement", "")
        if not path or not target:
            return "ERROR: Missing path or target"
        try:
            fp = await self._resolve_path(path)
            if not fp.is_file():
                return f"ERROR: File {path} not found"
            
            # Check permissions
            err = await self._assert_allowed(str(fp), "write")
            if err:
                return err

            content = fp.read_text(encoding="utf-8")
            count = content.count(target)
            if count == 0:
                return "ERROR: Target content not found in file"
            if count > 1:
                return f"ERROR: Target content is not unique (found {count} occurrences). Please specify more unique context."
            
            new_content = content.replace(target, replacement)
            fp.write_text(new_content, encoding="utf-8")
            return f"SUCCESS: Substring replaced successfully in {path}"
        except Exception as e:
            return f"ERROR: {e}"

    async def _tool_start_task(self, args: dict) -> str:
        cmd = args.get("cmd", "")
        if not cmd:
            return "ERROR: No command specified"
        import uuid, subprocess, time, sys
        from pathlib import Path
        
        task_id = str(uuid.uuid4())[:8]
        proj_dir = await self._project_dir()
        cwd = str(proj_dir) if proj_dir else None
        
        # We will write logs to a file in the project dir named .task_{task_id}.log
        log_file_path = proj_dir / f".task_{task_id}.log" if proj_dir else Path(f".task_{task_id}.log")
        
        try:
            # Open file for writing logs
            log_file = open(log_file_path, "w", encoding="utf-8")
            proc = subprocess.Popen(
                cmd,
                shell=True,
                cwd=cwd,
                stdout=log_file,
                stderr=log_file,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            
            AgentReAct.ACTIVE_TASKS[task_id] = {
                "proc": proc,
                "log_path": log_file_path,
                "log_file": log_file,
                "cmd": cmd,
                "started_at": time.time()
            }
            return f"SUCCESS: Background task started with ID: {task_id}"
        except Exception as e:
            return f"ERROR starting task: {e}"

    async def _tool_get_task_status(self, args: dict) -> str:
        task_id = args.get("task_id", "")
        if not task_id:
            return "ERROR: No task_id specified"
        task = AgentReAct.ACTIVE_TASKS.get(task_id)
        if not task:
            return f"ERROR: Task {task_id} not found"
        
        proc = task["proc"]
        poll = proc.poll()
        status = "RUNNING" if poll is None else f"EXITED (code {poll})"
        
        # Read latest logs from the log file
        log_content = ""
        try:
            # Flush file handle
            task["log_file"].flush()
            # Read from file
            log_path = task["log_path"]
            if log_path.exists():
                log_content = log_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            log_content = f"(Could not read logs: {e})"
            
        # Limit log output to last 2000 chars to avoid context overflow
        if len(log_content) > 2000:
            log_content = "...\n" + log_content[-2000:]
            
        return (
            f"Task ID: {task_id}\n"
            f"Command: {task['cmd']}\n"
            f"Status: {status}\n"
            f"Logs:\n{log_content}"
        )

    async def _tool_kill_task(self, args: dict) -> str:
        task_id = args.get("task_id", "")
        if not task_id:
            return "ERROR: No task_id specified"
        task = AgentReAct.ACTIVE_TASKS.get(task_id)
        if not task:
            return f"ERROR: Task {task_id} not found"
        
        proc = task["proc"]
        import sys
        try:
            if sys.platform == "win32":
                import signal
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            proc.terminate()
            proc.wait(timeout=2)
            status = "TERMINATED"
        except Exception:
            proc.kill()
            status = "KILLED"
            
        try:
            task["log_file"].close()
            # Clean up log file
            if task["log_path"].exists():
                task["log_path"].unlink()
        except Exception:
            pass
            
        AgentReAct.ACTIVE_TASKS.pop(task_id, None)
        return f"SUCCESS: Task {task_id} has been {status}"

    async def _tool_list_tasks(self, args: dict) -> str:
        if not AgentReAct.ACTIVE_TASKS:
            return "No background tasks currently running."
        results = []
        # Clean up any dead processes
        for tid, task in list(AgentReAct.ACTIVE_TASKS.items()):
            poll = task["proc"].poll()
            status = "RUNNING" if poll is None else f"EXITED (code {poll})"
            results.append(f"  - ID: {tid} | Command: {task['cmd']} | Status: {status}")
        return "Active Background Tasks:\n" + "\n".join(results)

    async def _tool_list_symbols(self, args: dict) -> str:
        path = args.get("path", "")
        if not path:
            return "ERROR: No path specified"
        try:
            fp = await self._resolve_path(path)
            if not fp.is_file():
                return f"ERROR: File {path} not found"
                
            # Check permissions
            err = await self._assert_allowed(str(fp), "read")
            if err:
                return err

            content = fp.read_text(encoding="utf-8")
            
            # If python file, use AST
            if path.endswith(".py"):
                import ast
                try:
                    tree = ast.parse(content)
                    symbols = []
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            symbols.append(f"Class: {node.name} (Line {node.lineno})")
                        elif isinstance(node, ast.FunctionDef):
                            symbols.append(f"Function: {node.name} (Line {node.lineno})")
                        elif isinstance(node, ast.AsyncFunctionDef):
                            symbols.append(f"Async Function: {node.name} (Line {node.lineno})")
                    if symbols:
                        return f"Symbols in {path}:\n" + "\n".join(symbols)
                    return f"No classes or functions found in {path}"
                except Exception as e:
                    return f"AST parse error in Python file {path}: {e}"
            
            # For other languages (Rust, PLL, JS), simple regex or line-by-line function search
            import re
            lines = content.splitlines()
            symbols = []
            for i, line in enumerate(lines, 1):
                # Match Rust fn, PLL fn, JS function
                m = re.match(r'^\s*(?:fn|function|class)\s+([a-zA-Z_][a-zA-Z0-9_]*)', line)
                if m:
                    symbols.append(f"Symbol: {m.group(1)} (Line {i})")
            if symbols:
                return f"Symbols in {path}:\n" + "\n".join(symbols)
            return f"No symbols found in {path}"
        except Exception as e:
            return f"ERROR listing symbols: {e}"

    async def _tool_ask_expert(self, args: dict) -> str:
        prompt = args.get("prompt", "")
        if not prompt:
            return "ERROR: No prompt specified"
        try:
            from services.llm_proxy import chat_completion
            system = "You are a senior software development expert. Answer the developer's question concisely with clear recommendations."
            result = await chat_completion(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system,
                temperature=0.2,
                backend=self.backend,
            )
            return f"Expert Advice:\n{result.get('response', '')}"
        except Exception as e:
            return f"ERROR calling expert: {e}"

    async def run(self, user_message: str, context: str = "", step_callback=None) -> dict:
        """ReAct loop. step_callback(steps_list, step_info, current_step, max_steps) is called after each tool execution for SSE."""
        system = (
            "You are an AI coding assistant that thinks and acts in PLL.\n\n"
            "PLL is for planning AND action — call tools using function syntax: list_dir(\"path\").\n"
            "You can also respond with plain text when answering a question.\n\n"
            "CRITICAL: Do NOT use XML tags like <tool_call>, <tool_name>, or <parameters>.\n"
            "Do NOT use JSON or other formats for tool calling. Call tools ONLY using pure inline PLL function syntax, e.g. list_dir(\"path\").\n\n"
            "PLL quick reference:\n"
            '  v x != "text"               - variable\n'
            '  v x != ?("prompt")          - LLM belief\n'
            '  list_dir(".")               - tool call\n'
            '  write_file("path", "...")   - write file\n'
            '  read_file("path")           - read file\n\n'
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
            first_call_pos = text_before_call.find("<tool_call>")
            known_tools = {
                "write_file", "read_file", "delete_file", "list_dir", "glob_files", 
                "grep_files", "exec_shell", "probe_path", "web_fetch", "web_search", 
                "final_answer", "rename_file", "zip_project", "replace_content",
                "start_task", "get_task_status", "kill_task", "list_tasks", "list_symbols", "ask_expert"
            }
            for tool in known_tools:
                pos = text_before_call.find(tool + "(")
                if pos >= 0 and (first_call_pos == -1 or pos < first_call_pos):
                    first_call_pos = pos
            if first_call_pos >= 0:
                text_before_call = text_before_call[:first_call_pos].strip()
            if text_before_call and not text_before_call.startswith('v '):
                accumulated_answer = text_before_call

            tool_calls = self._parse_tool_calls(response)
            if not tool_calls:
                final = {"answer": response, "steps": steps, "code": response, "file_path": ""}
                if accumulated_answer:
                    final["thinking"] = accumulated_answer
                return final


            # Group tools: run independent (read) tools in parallel, sequential ones one by one
            READ_ONLY = {"read_file", "list_dir", "glob_files", "grep_files", "search_vault",
                         "git_status", "git_log", "web_fetch", "web_search", "search_code",
                         "tree", "count_tokens", "read_lines", "diff_files", "list_symbols",
                         "get_task_status", "list_tasks", "ask_expert"}

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
            all_results = []

            if parallel_tools:
                async def _run_one(tc):
                    tool, args = tc.get("tool", ""), tc.get("args", {})
                    result = await self._execute_tool(tool, args)
                    return {"tool": tool, "args": args, "result": result}

                parallel_results = await asyncio.gather(*[_run_one(tc) for tc in parallel_tools])
                for pr in parallel_results:
                    step_result_clipped = pr["result"][:300] + ("..." if len(pr["result"]) > 300 else "")
                    steps.append({"step": step + 1, "tool": pr["tool"], "args": pr["args"], "result": step_result_clipped, "thinking": accumulated_answer})
                    all_results.append(f"Tool {pr['tool']} result:\n{pr['result']}")
                    if step_callback:
                        await step_callback(steps, {"thinking": accumulated_answer, "tool": pr["tool"], "args": pr["args"], "result": step_result_clipped}, step + 1, self.max_steps)

            for tc in sequential_tools:
                tool, args = tc.get("tool", ""), tc.get("args", {})
                result = await self._execute_tool(tool, args)
                result_clipped = result[:300] + ("..." if len(result) > 300 else "")
                step_info = {"tool": tool, "args": args, "result": result_clipped, "thinking": accumulated_answer}
                steps.append({"step": step + 1, **step_info})
                all_results.append(f"Tool {tool} result:\n{result}")
                if step_callback:
                    await step_callback(steps, step_info, step + 1, self.max_steps)

            last_result = "\n\n".join(all_results) if all_results else "done"
            messages.append({"role": "user", "content": f"Result:\n{last_result}\n\nContinue thinking in PLL. If you have finished the user's request, call final_answer(text). Otherwise, call the next tool:"})

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
