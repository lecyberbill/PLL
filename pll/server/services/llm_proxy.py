"""
LLM Proxy Service

Supports two backends:
   1. DeepSeek API (cloud) — https://api.deepseek.com/v1/chat/completions
   2. LM Studio (local) — http://localhost:1234/v1/chat/completions

Backend selection (in order of priority):
  - Request parameter `backend="deepseek"` or `backend="lmstudio"`
  - Env var `PLL_LLM_BACKEND=deepseek` or `PLL_LLM_BACKEND=lmstudio`
  - If Dp_API_KEY is set: deepseek, else: lmstudio

DeepSeek API key is read from env var `Dp_API_KEY`.
"""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import urlencode

# Load .env before reading config (in case config.py wasn't imported yet)
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

LM_STUDIO_URL = os.getenv("PLL_LM_URL", "http://localhost:1234/v1/chat/completions")
LM_STUDIO_MODELS_URL = os.getenv("PLL_LM_MODELS_URL", "http://localhost:1234/v1/models")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = os.getenv("Dp_API_KEY", "")
DEFAULT_BACKEND = os.getenv("PLL_LLM_BACKEND", "deepseek" if DEEPSEEK_API_KEY else "lmstudio")

# ---------- Few-shot examples ----------
FEW_SHOT_EXAMPLES = """
## EXAMPLE 1: Factorial (recursion)
```
fn factorial(n: num) -> num:
    if n <= 1:
        return 1
    return n * factorial(n - 1)

v result != factorial(5)
render str_concat("5! = ", str_from_num(result))
```

## EXAMPLE 2: List operations & forEach
```
fn sum_list(lst: list) -> num:
    v total != 0
    foreach val in lst:
        total != total + val
    return total

v numbers != list_new()
numbers != list_push(numbers, 10)
numbers != list_push(numbers, 20)
numbers != list_push(numbers, 30)
v s != sum_list(numbers)
render str_concat("Sum: ", str_from_num(s))
```

## EXAMPLE 3: Record / object usage
```
fn create_user(name: str, age: num):
    v u != {}
    u.name != name
    u.age != age
    return u

v alice != create_user("Alice", 30)
render str_concat(alice.name, " is ", str_from_num(alice.age), " years old")
```

## EXAMPLE 4: File read/write with user-agent interaction
```
# Read a config file and greet the user
v name != read_file("name.txt")
if str_length(name) == 0:
    name != "World"
render str_concat("Hello, ", name)
write_file("output.txt", str_concat("Greeted: ", name))
```

## EXAMPLE 5: While loop with string building
```
fn countdown(n: num):
    v result != ""
    while n > 0:
        result != str_concat(result, str_from_num(n), "...")
        n != n - 1
    result != str_concat(result, "GO!")
    return result

render countdown(5)
```
"""

# ---------------------------------------------------------------------------
# SYSTEM PROMPT — syntax reference + few-shot examples
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_PLL = f"""You are a PLL v2 code generator. PLL is a custom programming language for agentic workflows.

## PLL v2 SYNTAX REFERENCE

### Variables & Assignment
```
v name != "value"         # variable declaration
v count != 42
v flag != true
name != "new value"       # reassignment (same operator)
```

### Functions
```
fn add(a: num, b: num) -> num:
    return a + b

fn greet(name: str):
    render str_concat("Hello, ", name)
```

### Control Flow
```
if count > 10:
    render "big"
else:
    render "small"

while i < 10:
    i != i + 1

foreach item in my_list:
    render item
```

### Built-in Functions
```
str_concat(a, b)           # string concatenation (BINARY only)
str_length(s)              # string length (characters)
str_slice(s, start, end)   # substring
str_char_at(s, idx)        # character at index
str_to_num(s)              # string to number
str_from_num(n)            # number to string
list_new()                 # create empty list
list_push(list, item)      # add item to list (returns new list)
list_get(list, idx)        # get item at index
list_length(list)          # list size
read_file(path)            # read file content (returns string)
write_file(path, content)  # write content to file
```

### Important: str_concat is BINARY (2 args only)
For 3+ args, nest calls: str_concat(a, b, c, d) -> str_concat(str_concat(a, b), str_concat(c, d))

### Data Structures
```
v rec != {{}}              # empty record
v user != {{ "name": "Alice", "age": 30 }}
user.name != "Bob"         # field assignment

v lst != list_new()
lst != list_push(lst, 42)
v first != list_get(lst, 0)
```

### Records
```
v user != {{}}
user.name != "Alice"
render user.name
```

### Comments
```
# Single line comment
```

## CRITICAL RULES (must follow)
1. Use `!=` for ALL assignment. NEVER use `=` (PLL does NOT have `=`).
2. Always put `:` after `if`, `else`, `while`, `foreach`, `fn`.
3. Use 4-space indentation for blocks.
4. `str_concat` takes EXACTLY 2 arguments. Nest for 3+.
5. Builtins use snake_case: `str_concat`, not `strconcat` or `concat`.
6. Strings use double quotes only: "hello", not 'hello'.
7. Types: str, num, bool, list, record.
8. CRITICAL: Do NOT use Python syntax like `elif`, `def`, `print`, `range`, `in` (use `foreach`), `len()` (use `str_length`/`list_length`).
9. Generate ONLY the PLL code, NO markdown fences, NO explanations.

## COMPLETE EXAMPLES

{FEW_SHOT_EXAMPLES}
"""

# ---------------------------------------------------------------------------
# SELF-REVIEW PROMPT — ask the LLM to check its own code
# ---------------------------------------------------------------------------
SELF_REVIEW_PROMPT = """Review this PLL v2 code for errors. Check ALL of these rules:

1. Assignment uses `!=`, not `=` (most common error!)
2. `if`, `else`, `while`, `foreach`, `fn` must end with `:`
3. Indentation is exactly 4 spaces per level
4. `str_concat` takes exactly 2 arguments (nest for 3+)
5. Builtins use snake_case (str_concat, str_length, etc.)
6. Strings use double quotes, not single quotes
7. No Python syntax: no `elif`, `def`, `print`, `range`, `len()`
8. `foreach` syntax: `foreach var in list:` not `for var in list:` or `for each var in list:`

If there are ANY errors, return ONLY the corrected code with NO explanations.
If the code is PERFECTLY correct, return exactly: OK

CODE TO REVIEW:
```pll
{code}
```
"""


async def chat_completion(
    messages: list[dict],
    system_prompt: str = SYSTEM_PROMPT_PLL,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    model: str = "",
    backend: str = "",
) -> dict:
    """Send a chat completion request to the configured LLM backend (with cache)."""
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    backend = backend or DEFAULT_BACKEND

    if backend == "deepseek":
        return await _call_deepseek(full_messages, temperature, max_tokens, model)
    else:
        return await _call_lmstudio(full_messages, temperature, max_tokens, model)


async def _call_deepseek(messages, temperature, max_tokens, model=""):
    if not DEEPSEEK_API_KEY:
        raise ValueError(
            "DeepSeek API key not found. Set Dp_API_KEY environment variable."
        )
    body = json.dumps({
        "model": model or "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode("utf-8")
    req = Request(
        DEEPSEEK_API_URL, data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
        method="POST",
    )
    try:
        resp = urlopen(req, timeout=120)
        data = json.loads(resp.read().decode("utf-8"))
        choice = data["choices"][0]
        return {"response": choice["message"]["content"],
                "usage": data.get("usage", {}), "backend": "deepseek"}
    except URLError as e:
        raise ConnectionError(f"Cannot reach DeepSeek API: {e.reason}") from e
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Unexpected DeepSeek API response: {e}") from e


async def _call_lmstudio(messages, temperature, max_tokens, model=""):
    body = json.dumps({
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode("utf-8")
    if model:
        body = json.dumps({
            "model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens, "stream": False,
        }).encode("utf-8")
    req = Request(
        LM_STUDIO_URL, data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        resp = urlopen(req, timeout=120)
        data = json.loads(resp.read().decode("utf-8"))
        choice = data["choices"][0]
        return {"response": choice["message"]["content"],
                "usage": data.get("usage", {}), "backend": "lmstudio"}
    except URLError as e:
        raise ConnectionError(
            f"Cannot reach LM Studio at {LM_STUDIO_URL}. "
            f"Error: {e.reason}"
        ) from e
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Unexpected LM Studio response: {e}") from e


NEUTRAL_CODEGEN_PROMPT = """You are a code generator. Generate clean, working code in the requested language.
Start with a comment: # file: filename.ext
then the code. Output ONLY the code, no markdown fences, no explanations."""


async def generate_pll_code(
    user_request: str,
    context: str = "",
    temperature: float = 0.15,
    backend: str = "",
    max_retries: int = 0,
    language: str = "python",
) -> str:
    """Generate code from a natural language request.

    For PLL: uses PLL-specific system prompt + self-review.
    For other languages: uses neutral codegen prompt, no self-review.
    """
    prompt = f"Generate {language} code for: {user_request}"
    if context:
        prompt += f"\n\nRelevant context from previous work:\n{context}"
    prompt += (
        "\n\nOutput ONLY the code. NO markdown fences. NO explanations.\n"
        "Start with: # file: filename.ext  (replace with the real filename and extension)"
    )

    system = SYSTEM_PROMPT_PLL if language == "pll" else NEUTRAL_CODEGEN_PROMPT
    result = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=system,
        temperature=temperature,
        backend=backend,
    )
    code = _clean_code(result["response"])

    # Self-review only for PLL code
    if max_retries > 0 and language == "pll":
        code = await _self_review_loop(code, max_retries, backend, temperature)

    return code


async def _self_review_loop(
    code: str, max_retries: int, backend: str, temperature: float
) -> str:
    """Ask the LLM to review its own generated code and fix errors."""
    for attempt in range(max_retries):
        review_prompt = SELF_REVIEW_PROMPT.format(code=code)
        review = await chat_completion(
            messages=[{"role": "user", "content": review_prompt}],
            temperature=0.1,  # low temperature for review
            backend=backend,
        )
        reviewed = review["response"].strip()
        if reviewed == "OK":
            break
        fixed = _clean_code(reviewed)
        if fixed and fixed != code:
            code = fixed
        else:
            break
    return code


def _clean_code(raw: str) -> str:
    """Strip markdown fences and whitespace from LLM output."""
    code = raw.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1] if "\n" in code else code[3:]
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()
    return code
