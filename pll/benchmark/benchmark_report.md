# Benchmark Compactness Report: JSON vs PLL
**Tokenizer**: `tiktoken (cl100k_base)`

## 1. System Prompt Size (First Exchange priming)
The system prompt defines how the LLM must call tools. PLL uses standard function syntax, whereas JSON requires verbose structural guidelines and schemas.

- **JSON System Prompt**: 1888 chars, **497 tokens**
- **PLL System Prompt**: 325 chars, **81 tokens**
- **First Exchange Savings (System Prompt)**: **83.7% less tokens**

## 2. Static Scenarios Comparison
Comparison of individual tool calling payload sizes.

| Scenario | Format | Chars | Tokens | Token Savings % |
| :--- | :--- | :---: | :---: | :---: |
| **1. Simple Read Call** | JSON | 71 | 22 | - |
| | **PLL** | **41** | **11** | **50.0%** |
| | | | | |
| **2. Simple Directory List** | JSON | 51 | 17 | - |
| | **PLL** | **21** | **6** | **64.7%** |
| | | | | |
| **3. Large Write Call (CSS)** | JSON | 457 | 182 | - |
| | **PLL** | **405** | **153** | **15.9%** |
| | | | | |
| **4. Large Write Call (JS + Escaped Templates)** | JSON | 515 | 142 | - |
| | **PLL** | **467** | **111** | **21.8%** |
| | | | | |
| **5. ReAct History (Cumulative overhead)** | JSON | 297 | 90 | - |
| | **PLL** | **226** | **62** | **31.1%** |
| | | | | |
| **6. Complex ReAct Stress Test (Multi-file refactor)** | JSON | 802 | 254 | - |
| | **PLL** | **531** | **137** | **46.1%** |
| | | | | |
## 3. Live LM Studio Generation (Simple Query)
**Query**: "vérifie le contenu du dossier public/ pour voir s'il y a des fichiers."

| Metric | JSON Mode | PLL Mode | PLL Savings % |
| :--- | :---: | :---: | :---: |
| **Input Tokens (Prompt)** | 600 | 124 | **79.3%** |
| **Output Tokens (Completion)** | 193 | 305 | **-58.0%** |
| **Total Tokens** | 793 | 429 | **45.9%** |
| **Generation Time** | 8.05s | 10.25s | **-27.4%** |

## 4. Live LM Studio Generation (Complex Stress Test)
**Query**: "You need to perform a full refactor: read public/index.html, public/js/app.js, public/css/style.css, then write a new dark theme style in public/css/theme.css, write a helper format function (formatTemp) and an input cleaning regex in public/js/utils.js, run 'npm run build', check if 'dist/index.html' exists, and return a final answer. Generate all the necessary tool calls sequentially in one go."

| Metric | JSON Mode | PLL Mode | PLL Savings % |
| :--- | :---: | :---: | :---: |
| **Input Tokens (Prompt)** | 671 | 195 | **70.9%** |
| **Output Tokens (Completion)** | 800 | 800 | **0.0%** |
| **Total Tokens** | 1471 | 995 | **32.4%** |
| **Generation Time** | 24.73s | 23.29s | **5.8%** |

### Output Samples (Stress Test)
**JSON Output**:
```json

```

**PLL Output**:
```pll

```