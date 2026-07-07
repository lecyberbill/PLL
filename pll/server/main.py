"""
PLL Server — FastAPI backend for the PLL Language IDE

Serves:
  - Static files for the playground (HTML/JS/CSS/WASM)
  - REST API for project/file management (artifacts, agents)
  - GCA orchestrator for agent lifecycle management
  - Package registry
"""
import os
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import config
from database import init_db

from routes.artifacts import router as artifacts_router
from routes.agents import router as agents_router
from routes.gca import router as gca_router
from routes.packages import router as packages_router
from routes.llm import router as llm_router
from routes.agentic import router as agentic_router
from routes.fs import router as fs_router
from routes.exec import router as exec_router
from routes.react import router as react_router
from routes.git_routes import router as git_router
from routes.pll_exec import router as pll_exec_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="PLL Language Server",
    version="2.0.0",
    description="PLL v2 — IDE Backend with GCA Orchestrator, Package Registry, and Artifact Storage",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(artifacts_router)
app.include_router(agents_router)
app.include_router(gca_router)
app.include_router(packages_router)
app.include_router(llm_router)
app.include_router(agentic_router)
app.include_router(fs_router)
app.include_router(exec_router)
app.include_router(react_router)
app.include_router(git_router)
app.include_router(pll_exec_router)

PLAYGROUND = os.path.abspath(config.PLAYGROUND_DIR)


@app.get("/")
async def serve_root():
    index_path = os.path.join(PLAYGROUND, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return JSONResponse({"detail": "Not Found"}, status_code=404)


@app.get("/{full_path:path}")
async def serve_static(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    file_path = os.path.normpath(os.path.join(PLAYGROUND, full_path))
    if not file_path.startswith(PLAYGROUND):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    if os.path.isfile(file_path):
        ext = os.path.splitext(full_path)[1].lower()
        media_type = {"ttf": "font/ttf", "woff": "font/woff", "woff2": "font/woff2",
                      "otf": "font/otf", "eot": "application/vnd.ms-fontobject"}.get(ext)
        return FileResponse(file_path, media_type=media_type)
    index_path = os.path.join(PLAYGROUND, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return JSONResponse({"detail": "Not Found"}, status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
