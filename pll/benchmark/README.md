# PLL vs JSON: Tool Calling Compactness and Reliability Benchmark

This directory contains the benchmark suite designed to compare **PLL (Probabilistic LLM Language)** tool calling syntax against standard **JSON** format.

The primary objective of PLL is to reduce token overhead, bypass escape sequence errors, and improve execution reliability for LLM agents, especially when running on local, resource-constrained **Small Language Models (SLMs)**.

---

## 1. Methodology

The benchmark compares JSON and PLL across three dimensions:
1.  **System Prompt Footprint**: The size of the context instructions required to prime the LLM.
2.  **Static Payload Analysis**: Size comparisons of typical tool call payloads (reads, listings, writes, and history).
3.  **Live LM Studio Generation (Qwen-AgentWorld-35B)**: Real-world generation time, token counts, and syntax reliability under high cognitive load (Complex Stress Test).

---

## 2. Key Findings

### 2.1 System Prompt Footprint (First Exchange Priming)
Defining tool parameters and formatting rules in JSON schema is highly verbose. In contrast, PLL's function-like inline syntax is lightweight.
*   **JSON System Prompt**: 1,888 characters (**497 tokens**)
*   **PLL System Prompt**: 325 characters (**81 tokens**)
*   **Prompt Compression**: **-83.7% tokens saved** *on the first exchange (and carried over every step in the ReAct history).*

### 2.2 Static Payload Comparison
PLL triple-quotes (`"""`) eliminate the need to escape backslashes, double quotes, and newlines in file write operations.

| Scenario | JSON Chars (Tokens) | PLL Chars (Tokens) | Token Savings % |
| :--- | :---: | :---: | :---: |
| **1. Simple Read Call** | 71 (22) | 41 (11) | **-50.0%** |
| **2. Simple Directory List** | 51 (17) | 21 (6) | **-64.7%** |
| **3. Large Write (CSS)** | 457 (182) | 405 (153) | **-15.9%** |
| **4. Large Write (JS + Templates)** | 515 (142) | 467 (111) | **-21.8%** |
| **5. ReAct History (3-step loop)** | 297 (90) | 226 (62) | **-31.1%** |
| **6. Complex Stress Test (Multi-tool)** | 802 (254) | 531 (137) | **-46.1%** |

---

## 3. Live LLM Execution & Reliability Results
Tested against a local instance of **Qwen-AgentWorld-35B** (LM Studio, temperature 0.1, max output tokens 4096).

### 3.1 Scenario: Complex Refactoring Stress Test
The LLM is prompted to perform a multi-file refactor: read 3 files, write 2 new source files containing template literals and regexes, execute a build command, check path existence, and output the final answer.

| Metric | JSON Mode | PLL Mode | PLL Advantage |
| :--- | :---: | :---: | :---: |
| **Input Tokens (Prompt + System)** | 671 | 195 | **-70.9%** |
| **Output Tokens (Generation)** | 4,096 (truncated) | 3,027 (completed) | **-26.1%** |
| **Total Transaction Tokens** | 4,767 | 3,222 | **-32.4%** |
| **Syntax Success Rate** | 60.0% | **80.0%** | **+20.0% reliability** |
| **Total Wasted Tokens (Failed runs)** | 9,521 | **4,291** | **5,230 tokens saved** |
| **Average Generation Time** | 136.4s | **96.5s** | **-29.3%** (~40s saved) |

---

## 4. Deep Insights & Analysis

### 4.1 Escaping tax & JSON parsing failures
Local models (7B - 35B) frequently fail when generating long JSON payloads containing code because they struggle to escape quotes (`\"`) and newlines (`\n`) consistently. 
*   In the **JSON Stress Test**, the model repeatedly hit the output limit or outputted malformed braces, failing 2 out of 5 runs.
*   In **PLL Mode**, the model wrote code naturally inside standard triple quotes (`"""`). It successfully generated the entire 8-step sequence in 4 out of 5 runs, with an average output size of only 3,027 tokens (compared to JSON's 4,096+ truncated output).

### 4.2 Cumulative ReAct loop savings
Because ReAct agents must carry the conversation history at every step, any token savings in early steps scale quadratically. Saving **476 tokens on prompt priming** plus **~1,000 tokens on outputs** prevents context window saturation on local hosts and drastically speeds up inference.

### 4.3 Program-Aided Reasoning (Augmenting SLMs with the Rust VM)
LLMs are notoriously weak at performing deterministic computations (like complex mathematical recursions, floating-point arithmetic, or sorting algorithms) inside their neural networks. 
By generating a lightweight PLL script and offloading it to the native **Rust VM** (or browser WebAssembly runtime), a small local model (e.g. 7B) can guarantee 100% mathematical accuracy. 

Unlike Python execution (which requires heavy OS-level sandboxing to prevent security breaches), the PLL VM is a secure, sandboxed environment by design, allowing secure computation delegation even on client-side hosts. This offsets the cognitive gap between small local models and frontier APIs (like Claude Opus) for computational tasks.

---

## 5. Running the Benchmarks Locally

### Prerequisite
Install dependencies:
```bash
pip install tiktoken
```

### Run Static and Live Sizing Tests
Ensure LM Studio is running on `http://localhost:1234` with a model loaded, then run:
```bash
python compare.py --live
```

### Run Multi-iteration Reliability Tests
To measure syntax success rates, run:
```bash
python reliability_test.py
```
Outputs are written to `benchmark_report.md` and `reliability_report.md`.
