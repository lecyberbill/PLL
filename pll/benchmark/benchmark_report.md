# Benchmark Compactness Report: JSON vs PLL
**Tokenizer**: `tiktoken (cl100k_base)`

## 1. System Prompt Size (First Exchange priming)
The system prompt defines how the LLM must call tools. PLL uses standard function syntax, whereas JSON requires verbose structural guidelines and schemas.

- **JSON System Prompt**: 1600 chars, **421 tokens**
- **PLL System Prompt**: 304 chars, **75 tokens**
- **First Exchange Savings (System Prompt)**: **82.2% less tokens**

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
## 3. Live LM Studio Generation Results
**Query**: "vérifie le contenu du dossier public/ pour voir s'il y a des fichiers."

| Metric | JSON Mode | PLL Mode | PLL Savings % |
| :--- | :---: | :---: | :---: |
| **Input Tokens (Prompt)** | 513 | 117 | **77.2%** |
| **Output Tokens (Completion)** | 71 | 92 | **-29.6%** |
| **Total Tokens** | 584 | 209 | **64.2%** |
| **Generation Time** | 4.94s | 4.77s | **3.4%** |

### Output Samples
**JSON Output**:
```json


{"tool": "list_dir", "args": {"path": "public"}}
```

**PLL Output**:
```pll


v plan != "list public files"
list_dir("public")
```