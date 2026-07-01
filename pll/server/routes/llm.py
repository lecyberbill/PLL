from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from services.llm_proxy import chat_completion, generate_pll_code

router = APIRouter(prefix="/api/llm", tags=["LLM Proxy"])


class ChatRequest(BaseModel):
    messages: list[dict]
    system_prompt: str = ""
    temperature: float = 0.2
    max_tokens: int = 4096
    backend: str = ""  # "deepseek" | "lmstudio" | "" (auto)


class ChatResponse(BaseModel):
    response: str
    usage: dict = {}
    backend: str = ""


@router.post("/chat", response_model=ChatResponse)
async def llm_chat(req: ChatRequest):
    """Forward a chat completion to DeepSeek or LM Studio."""
    try:
        result = await chat_completion(
            messages=req.messages,
            system_prompt=req.system_prompt,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            backend=req.backend,
        )
        return ChatResponse(**result)
    except ConnectionError as e:
        raise HTTPException(503, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


class GenerateRequest(BaseModel):
    prompt: str
    context: str = ""
    backend: str = ""


@router.post("/generate")
async def llm_generate(req: GenerateRequest):
    """Generate PLL code from a natural language prompt."""
    try:
        code = await generate_pll_code(req.prompt, req.context, backend=req.backend)
        return {"code": code, "backend": req.backend or "auto"}
    except ConnectionError as e:
        raise HTTPException(503, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/status")
async def llm_status():
    """Check which backends are available."""
    status = {"deepseek": False, "lmstudio": False}

    # Check DeepSeek key
    import os
    if os.getenv("Dp_API_KEY"):
        status["deepseek"] = True

    # Check LM Studio
    from urllib.request import urlopen
    from urllib.error import URLError
    try:
        resp = urlopen("http://localhost:1234/v1/models", timeout=2)
        status["lmstudio"] = True
    except URLError:
        pass

    default = os.getenv("PLL_LLM_BACKEND", "lmstudio")
    return {"available": status, "default": default}
