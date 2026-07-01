"""Test the PLL-powered agentic /go endpoint."""
import urllib.request
import json
import sys

BASE = "http://127.0.0.1:8080"

def api(path, method="GET", data=None):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=180)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"HTTP {e.code}: {err}", file=sys.stderr)
        return None

# 1. Create project
print("=== Creating project ===")
proj = api("/api/projects", "POST", {"name": "FlaskTodo", "description": "PLL agent test"})
print(f"Project ID: {proj['id']}")
pid = proj["id"]

# 2. Call /go
print("\n=== Calling /api/agentic/go ===")
print("Message: Crée une API REST Flask pour une todo list...")
print("(waiting for LLM response, may take 30-60s)...\n")

result = api(f"/api/agentic/go", "POST", {
    "project_id": pid,
    "message": "Crée une API REST Flask pour une todo list avec create, read, update, delete, stockage en mémoire"
})

if result:
    print(f"\n=== Result ===")
    print(f"Mode: {result.get('mode', '?')}")
    print(f"Answer: {result.get('answer', '')[:500]}")
    print(f"Code: {result.get('code', '')[:500]}")
    print(f"File: {result.get('file_path', '')}")
    print(f"Files modified: {result.get('files_modified', [])}")
    if result.get('steps'):
        print(f"\nSteps ({len(result['steps'])}):")
        for s in result['steps']:
            print(f"  {s.get('step')}. {s.get('tool')}: {str(s.get('args', {}))[:100]}")
    if result.get('subtasks'):
        print(f"\nSubtasks ({len(result['subtasks'])}):")
        for s in result['subtasks']:
            print(f"  - {s.get('subtask', '')[:100]}")
else:
    print("FAILED - no result")
