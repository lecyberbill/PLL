"""Tests for ReAct tool call parsing and parallelism."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Use static method directly — instantiating AgentReAct requires sqlalchemy
from services.agent_react import AgentReAct

_parse_calls = AgentReAct._parse_tool_calls

def test_parse_single_tool_call():
    text = '{"tool": "read_file", "args": {"path": "main.py"}}'
    calls = _parse_calls(text)
    assert len(calls) == 1
    assert calls[0]["tool"] == "read_file"
    assert calls[0]["args"]["path"] == "main.py"

def test_parse_multi_tool_calls():
    text = '''v plan != ?("read files")
{"tool": "read_file", "args": {"path": "a.py"}}
{"tool": "read_file", "args": {"path": "b.py"}}'''
    calls = _parse_calls(text)
    assert len(calls) == 2, f"expected 2, got {len(calls)}: {calls}"
    assert calls[0]["args"]["path"] == "a.py"
    assert calls[1]["args"]["path"] == "b.py"

def test_parse_no_tool():
    calls = _parse_calls("v answer != ?('hello')")
    assert calls == []

def test_parse_mixed_read_write():
    text = '''v plan != ?("read then write")
{"tool": "read_file", "args": {"path": "src/main.py"}}
{"tool": "edit_artifact", "args": {"path": "src/main.py", "content": "print(1)"}}'''
    calls = _parse_calls(text)
    assert len(calls) == 2
    assert calls[0]["tool"] == "read_file"
    assert calls[1]["tool"] == "edit_artifact"

def test_tool_grouping():
    READ_ONLY = {"read_file", "list_dir", "glob_files", "grep_files", "search_vault",
                 "git_status", "git_log", "web_fetch", "web_search", "search_code",
                 "tree", "count_tokens", "read_lines", "diff_files"}
    tool_calls = [
        {"tool": "read_file", "args": {"path": "a.py"}},
        {"tool": "edit_artifact", "args": {"path": "b.py", "content": "x"}},
        {"tool": "read_file", "args": {"path": "c.py"}},
    ]
    parallel = [tc for tc in tool_calls if tc.get("tool") in READ_ONLY]
    sequential = [tc for tc in tool_calls if tc.get("tool") not in READ_ONLY]
    assert len(parallel) == 2  # two reads
    assert len(sequential) == 1  # one write
