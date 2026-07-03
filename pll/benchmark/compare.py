import json
import os
import sys

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

def run_benchmark():
    print(f"=== COMPACTNESS BENCHMARK (JSON vs PLL) ===")
    print(f"Tokenizer: {'tiktoken (cl100k_base)' if HAS_TIKTOKEN else 'Character Estimator (char/4)'}\n")
    
    report_lines = [
        "# Benchmark Compactness Report: JSON vs PLL",
        f"**Tokenizer**: `{'tiktoken (cl100k_base)' if HAS_TIKTOKEN else 'char_estimator'}`",
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
        report_lines.append("| | | | | |")  # spacing row
        
    report = "\n".join(report_lines)
    print(report)
    
    # Save report to artifacts or benchmark directory
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_file = os.path.join(out_dir, "benchmark_report.md")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport written to: {out_file}")

if __name__ == "__main__":
    run_benchmark()
