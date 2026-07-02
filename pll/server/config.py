import os
from pathlib import Path

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

DATABASE_URL = os.getenv("PLL_DATABASE_URL", "sqlite+aiosqlite:///pll_server.db")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
PLAYGROUND_DIR = os.path.join(os.path.dirname(__file__), "..", "playground")
AGENTS_DIR = os.path.join(os.path.dirname(__file__), "agents")
PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")
HOST = os.getenv("PLL_HOST", "127.0.0.1")
PORT = int(os.getenv("PLL_PORT", "8080"))

# Google Custom Search
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CX = os.getenv("GOOGLE_CX", "")
