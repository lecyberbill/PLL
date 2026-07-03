import json
import os
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError

# Try importing tiktoken, use simple char/4 estimation as fallback
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

def count_tokens(text: str) -> int:
    if HAS_TIKTOKEN:
        try:
            # Use cl100k_base (used by GPT-4, DeepSeek, etc.)
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            pass
    # Fallback approximation
    return max(1, len(text) // 4)

# Define realistic system prompts
JSON_SYSTEM_PROMPT = """You are an AI coding assistant. You can call tools by outputting a JSON object.
Available tools:
[
  {
    "name": "read_file",
    "description": "Read the contents of a file.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string", "description": "Path to the file"}
      },
      "required": ["path"]
    }
  },
  {
    "name": "write_file",
    "description": "Write or create a file with content.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string", "description": "Path to write"},
        "content": {"type": "string", "description": "Full file content"}
      },
      "required": ["path", "content"]
    }
  },
  {
    "name": "list_dir",
    "description": "List files in a directory.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string", "description": "Path to list"}
      },
      "required": ["path"]
    }
  },
  {
    "name": "exec_shell",
    "description": "Execute a shell command.",
    "parameters": {
      "type": "object",
      "properties": {
        "cmd": {"type": "string", "description": "Shell command to run"}
      },
      "required": ["cmd"]
    }
  },
  {
    "name": "final_answer",
    "description": "Call this to complete the task.",
    "parameters": {
      "type": "object",
      "properties": {
        "text": {"type": "string", "description": "Final result text"}
      },
      "required": ["text"]
    }
  }
]
Respond ONLY with a JSON tool call object, like: {"tool": "list_dir", "args": {"path": "src"}}"""

PLL_SYSTEM_PROMPT = """You are an AI assistant that thinks and acts in PLL.
Call tools using inline function syntax.
PLL Reference:
  list_dir("path")
  read_file("path")
  write_file("path", "content")
  exec_shell("cmd")
  final_answer("text")

Respond in PLL format. Example:
v plan != "list public files"
list_dir("public")"""

# Define standard scenarios
SCENARIOS = {
    "1. Simple Read Call": {
        "description": "A single read_file operation on a project component.",
        "pll": 'read_file("src/components/CVPreview.tsx")',
        "json": '{"tool": "read_file", "args": {"path": "src/components/CVPreview.tsx"}}'
    },
    "2. Simple Directory List": {
        "description": "Listing files inside a folder.",
        "pll": 'list_dir("public/js")',
        "json": '{"tool": "list_dir", "args": {"path": "public/js"}}'
    },
    "3. Large Write Call (CSS)": {
        "description": "Writing a complete CSS stylesheet. Note the escaping of newlines and double quotes in JSON.",
        "pll": '''write_file("public/css/style.css", """
.card {
    background: linear-gradient(135deg, #ffb6c1, #ff69b4);
    border-radius: 20px;
    padding: 2rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
    transition: all 0.3s ease;
}
.card:hover {
    transform: translateY(-5px);
    box-shadow: 0 15px 40px rgba(0, 0, 0, 0.3);
}
@media (max-width: 640px) {
    .card {
        padding: 1.5rem;
    }
}
""")''',
        "json": json.dumps({
            "tool": "write_file",
            "args": {
                "path": "public/css/style.css",
                "content": """.card {
    background: linear-gradient(135deg, #ffb6c1, #ff69b4);
    border-radius: 20px;
    padding: 2rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
    transition: all 0.3s ease;
}
.card:hover {
    transform: translateY(-5px);
    box-shadow: 0 15px 40px rgba(0, 0, 0, 0.3);
}
@media (max-width: 640px) {
    .card {
        padding: 1.5rem;
    }
}
"""
            }
        })
    },
    "4. Large Write Call (JS + Escaped Templates)": {
        "description": "Writing a Javascript file containing regexes, quotes, and backtick template literals.",
        "pll": '''write_file("public/js/app.js", """
const API_KEY = 'YOUR_API_KEY';
const BASE_URL = 'https://api.openweathermap.org/data/2.5/weather';

function getWeatherIcon(iconCode) {
    return `https://openweathermap.org/img/wn/${iconCode}@2x.png`;
}

async function fetchWeather(city) {
    const response = await fetch(`${BASE_URL}?q=${encodeURIComponent(city)}`);
    const data = await response.json();
    cityName.textContent = `${data.name}, ${data.sys.country}`;
}
""")''',
        "json": json.dumps({
            "tool": "write_file",
            "args": {
                "path": "public/js/app.js",
                "content": """const API_KEY = 'YOUR_API_KEY';
const BASE_URL = 'https://api.openweathermap.org/data/2.5/weather';

function getWeatherIcon(iconCode) {
    return `https://openweathermap.org/img/wn/${iconCode}@2x.png`;
}

async function fetchWeather(city) {
    const response = await fetch(`${BASE_URL}?q=${encodeURIComponent(city)}`);
    const data = await response.json();
    cityName.textContent = `${data.name}, ${data.sys.country}`;
}
"""
            }
        })
    },
    "5. ReAct History (Cumulative overhead)": {
        "description": "Cumulative payload after a 3-step conversation (ReAct loop carrying history).",
        "pll": """User: vérifie le dossier public/
Asst: v path != "public"
list_dir("public")
Result: public/ contains index.html, css/
Asst: read_file("public/css/style.css")
Result: .card { color: red; }
Asst: final_answer("Style verified.")""",
        "json": """User: vérifie le dossier public/
Asst: {"tool": "list_dir", "args": {"path": "public"}}
Result: public/ contains index.html, css/
Asst: {"tool": "read_file", "args": {"path": "public/css/style.css"}}
Result: .card { color: red; }
Asst: {"tool": "final_answer", "args": {"text": "Style verified."}}"""
    }
}

def query_local_llm(system: str, prompt: str) -> tuple:
    """Send request to LM Studio. Returns (response_text, duration_seconds, input_tokens, output_tokens)."""
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 500
    }
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        "http://localhost:1234/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    start_time = time.time()
    try:
        with urlopen(req, timeout=45) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            duration = time.time() - start_time
            choice = res_data["choices"][0]["message"]["content"]
            usage = res_data.get("usage", {})
            in_tokens = usage.get("prompt_tokens", count_tokens(system + prompt))
            out_tokens = usage.get("completion_tokens", count_tokens(choice))
            return choice, duration, in_tokens, out_tokens
    except URLError as e:
        raise RuntimeError(f"Could not connect to LM Studio at localhost:1234. Make sure LM Studio is running and a model is loaded. Details: {e}")

def run_benchmark(live_mode=False):
    print(f"=== COMPACTNESS BENCHMARK (JSON vs PLL) ===")
    print(f"Tokenizer: {'tiktoken (cl100k_base)' if HAS_TIKTOKEN else 'Character Estimator (char/4)'}")
    
    # Calculate System Prompt Sizes
    json_sys_chars = len(JSON_SYSTEM_PROMPT)
    pll_sys_chars = len(PLL_SYSTEM_PROMPT)
    json_sys_tokens = count_tokens(JSON_SYSTEM_PROMPT)
    pll_sys_tokens = count_tokens(PLL_SYSTEM_PROMPT)
    sys_savings = ((json_sys_tokens - pll_sys_tokens) / json_sys_tokens) * 100
    
    report_lines = [
        "# Benchmark Compactness Report: JSON vs PLL",
        f"**Tokenizer**: `{'tiktoken (cl100k_base)' if HAS_TIKTOKEN else 'char_estimator'}`",
        "",
        "## 1. System Prompt Size (First Exchange priming)",
        "The system prompt defines how the LLM must call tools. PLL uses standard function syntax, whereas JSON requires verbose structural guidelines and schemas.",
        "",
        f"- **JSON System Prompt**: {json_sys_chars} chars, **{json_sys_tokens} tokens**",
        f"- **PLL System Prompt**: {pll_sys_chars} chars, **{pll_sys_tokens} tokens**",
        f"- **First Exchange Savings (System Prompt)**: **{sys_savings:.1f}% less tokens**",
        "",
        "## 2. Static Scenarios Comparison",
        "Comparison of individual tool calling payload sizes.",
        "",
        "| Scenario | Format | Chars | Tokens | Token Savings % |",
        "| :--- | :--- | :---: | :---: | :---: |"
    ]
    
    for name, data in SCENARIOS.items():
        pll_text = data["pll"]
        json_text = data["json"]
        
        pll_chars = len(pll_text)
        json_chars = len(json_text)
        
        pll_tokens = count_tokens(pll_text)
        json_tokens = count_tokens(json_text)
        
        savings_pct = ((json_tokens - pll_tokens) / json_tokens) * 100
        
        report_lines.append(f"| **{name}** | JSON | {json_chars} | {json_tokens} | - |")
        report_lines.append(f"| | **PLL** | **{pll_chars}** | **{pll_tokens}** | **{savings_pct:.1f}%** |")
        report_lines.append("| | | | | |")
        
    if live_mode:
        print("\n[LIVE MODE] Ping local LM Studio instance...")
        user_query = "vérifie le contenu du dossier public/ pour voir s'il y a des fichiers."
        try:
            print("Sending query in JSON format...")
            json_resp, json_dur, json_in, json_out = query_local_llm(JSON_SYSTEM_PROMPT, user_query)
            
            print("Sending query in PLL format...")
            pll_resp, pll_dur, pll_in, pll_out = query_local_llm(PLL_SYSTEM_PROMPT, user_query)
            
            live_in_savings = ((json_in - pll_in) / json_in) * 100
            live_out_savings = ((json_out - pll_out) / json_out) * 100
            
            report_lines.extend([
                "## 3. Live LM Studio Generation Results",
                f"**Query**: \"{user_query}\"",
                "",
                "| Metric | JSON Mode | PLL Mode | PLL Savings % |",
                "| :--- | :---: | :---: | :---: |",
                f"| **Input Tokens (Prompt)** | {json_in} | {pll_in} | **{live_in_savings:.1f}%** |",
                f"| **Output Tokens (Completion)** | {json_out} | {pll_out} | **{live_out_savings:.1f}%** |",
                f"| **Total Tokens** | {json_in + json_out} | {pll_in + pll_out} | **{((json_in+json_out)-(pll_in+pll_out))/(json_in+json_out)*100:.1f}%** |",
                f"| **Generation Time** | {json_dur:.2f}s | {pll_dur:.2f}s | **{((json_dur-pll_dur)/json_dur)*100:.1f}%** |",
                "",
                "### Output Samples",
                "**JSON Output**:",
                "```json",
                json_resp,
                "```",
                "",
                "**PLL Output**:",
                "```pll",
                pll_resp,
                "```"
            ])
            print("Live generation completed successfully!")
        except Exception as e:
            print(f"\n[WARNING] Live generation failed: {e}")
            report_lines.extend([
                "## 3. Live LM Studio Generation Results",
                "_Live generation skipped or failed to connect to LM Studio (localhost:1234)._"
            ])
    else:
        report_lines.extend([
            "## 3. Live LM Studio Generation Results",
            "_Run the script with `--live` flag to execute live generations on a running local LM Studio instance._"
        ])
        
    report = "\n".join(report_lines)
    print("\n" + report)
    
    # Save report to artifacts or benchmark directory
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_file = os.path.join(out_dir, "benchmark_report.md")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport written to: {out_file}")

if __name__ == "__main__":
    live = "--live" in sys.argv
    run_benchmark(live_mode=live)
