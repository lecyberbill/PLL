"""Tests for SSE streaming event format (no server dependency)."""
import json

def test_step_event():
    ev = json.dumps({"type": "step", "step": 1, "total": 5, "tool": "read_file", "result": "content"})
    p = json.loads(ev)
    assert p["type"] == "step" and p["step"] == 1 and p["tool"] == "read_file"

def test_done_event():
    ev = json.dumps({"type": "done", "answer": "Done."})
    p = json.loads(ev)
    assert p["type"] == "done" and p["answer"] == "Done."

def test_code_event():
    ev = json.dumps({"type": "code", "code": "print(1)", "file_path": "main.py"})
    p = json.loads(ev)
    assert p["type"] == "code" and p["file_path"] == "main.py"

def test_init_event():
    ev = json.dumps({"type": "init", "project": "test"})
    p = json.loads(ev)
    assert p["type"] == "init" and p["project"] == "test"

def test_sse_line_format():
    """Simulate SSE data: prefix parsing."""
    raw = 'data: {"type":"step","step":1}\n\n'
    for line in raw.split("\n"):
        if line.startswith("data: "):
            ev = json.loads(line[6:])
            assert ev["type"] == "step" and ev["step"] == 1
