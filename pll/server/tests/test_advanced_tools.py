import pytest
import sys, os
from pathlib import Path
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.agent_react import AgentReAct

class DummyAgent(AgentReAct):
    def __init__(self, tmp_dir):
        super().__init__(project_id=1, backend="test", max_steps=5)
        self._allowed_dir = Path(tmp_dir).resolve()
    
    async def _project_dir(self):
        return self._allowed_dir

@pytest.mark.anyio
async def test_replace_content(tmp_path):
    agent = DummyAgent(tmp_path)
    file_path = tmp_path / "hello.py"
    file_path.write_text("def my_func():\n    print('Hello World')\n", encoding="utf-8")
    
    # 1. Successful replace
    res = await agent._tool_replace_content({
        "path": "hello.py",
        "target": "print('Hello World')",
        "replacement": "print('Hello PLL')"
    })
    assert "SUCCESS" in res
    assert "print('Hello PLL')" in file_path.read_text(encoding="utf-8")

    # 2. Target not found
    res = await agent._tool_replace_content({
        "path": "hello.py",
        "target": "print('Non existent')",
        "replacement": "x"
    })
    assert "ERROR" in res

    # 3. Not unique target
    file_path.write_text("a\na\n", encoding="utf-8")
    res = await agent._tool_replace_content({
        "path": "hello.py",
        "target": "a",
        "replacement": "b"
    })
    assert "not unique" in res

@pytest.mark.anyio
async def test_background_task_runner(tmp_path):
    agent = DummyAgent(tmp_path)
    
    # Start a simple ping or echo task
    cmd = "python -c \"import time; print('start'); time.sleep(1); print('end')\""
    res = await agent._tool_start_task({"cmd": cmd})
    assert "SUCCESS" in res
    task_id = res.split("ID: ")[1].strip()
    
    # Check running status
    status_res = await agent._tool_get_task_status({"task_id": task_id})
    assert "RUNNING" in status_res
    
    # Wait for completion or kill
    await asyncio.sleep(0.5)
    kill_res = await agent._tool_kill_task({"task_id": task_id})
    assert "SUCCESS" in kill_res

@pytest.mark.anyio
async def test_list_symbols(tmp_path):
    agent = DummyAgent(tmp_path)
    file_path = tmp_path / "code.py"
    file_path.write_text("class MyClass:\n    pass\n\ndef my_function():\n    pass\n", encoding="utf-8")
    
    res = await agent._tool_list_symbols({"path": "code.py"})
    assert "Class: MyClass" in res
    assert "Function: my_function" in res

@pytest.mark.anyio
async def test_run_pll(tmp_path):
    agent = DummyAgent(tmp_path)
    res = await agent._tool_run_pll({
        "code": "render \"test run pll output\"\n"
    })
    assert "test run pll output" in res

@pytest.mark.anyio
async def test_native_pll_parsing():
    text = """
I am going to check the files in the directory.
```pll
v content != read_file("src/main.rs")
write_file("backup.rs", content)
```
Let me know if this looks good.
"""
    calls = AgentReAct._parse_tool_calls(text)
    assert len(calls) == 2
    assert calls[0]["tool"] == "read_file"
    assert calls[0]["args"]["path"] == "src/main.rs"
    assert calls[1]["tool"] == "write_file"
    assert calls[1]["args"]["path"] == "backup.rs"
    assert calls[1]["args"]["content"] == "content"


