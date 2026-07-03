# PLL — Agentic IDE & Inter-Agent Language

**PLL** (Probabilistic Language for LLMs) is both a programming language designed for agent-to-agent communication and an Agentic IDE that lets you build software through natural language conversation.

> [!NOTE]
> **PLL was entirely designed and written by AI developer agents for AI developer agents.** The human user did not intervene in the syntax or grammar design. It is a language born from autonomous agentic pair-programming.

```
User talks to Agent → Agent plans in PLL → Rust compiles & executes → Code is written
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (Browser)                │
│  Monaco Editor  ←→  Agent Chat  ←→  VFS Tree       │
└──────────────────────────┬──────────────────────────┘
                           │ HTTP REST
┌──────────────────────────▼──────────────────────────┐
│                Python Server (FastAPI)               │
│  Routes · Agent Brain · ReAct Loop · Coordinator    │
│  LLM Proxy (DeepSeek/LM Studio) · Git · Packages   │
└──────────────────────────┬──────────────────────────┘
                           │ subprocess
┌──────────────────────────▼──────────────────────────┐
│              Rust CLI (pll-cli)                      │
│  Lexer → Parser → Type Checker → Codegen            │
│  → Bytecode Compiler → Bytecode VM                  │
│  Builtins: read_file, write_file, render, db, etc.  │
└─────────────────────────────────────────────────────┘
```

## Quick Start

```bash
cd pll/server
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8080
```

Open **http://127.0.0.1:8080** in your browser. Create a project and start chatting with the agent.

## Features

### 🤖 Agentic IDE
- **Natural language coding**: "Create a Flask CRUD API with SQLite" → working code
- **Clarification**: agent asks questions when your request is vague
- **Multi-language output**: Python, Rust, JavaScript, Go, HTML, and 30+ more
- **21 tools**: read/write files, git, web fetch, search, shell, Python/PLL execution
- **Agent-to-agent PLL protocol**: compact inter-agent communication

### ⚡ PLL Language (Rust)
- Complete pipeline: Lexer → Parser → Type Checker → Bytecode Compiler → VM
- **6800+ lines of Rust** across 11 crates
- Builtins: `render`, `print`, `read_file`, `write_file`, `str_concat`, `db_set/get`
- Control flow: `if/else`, `while`, `foreach`, functions with recursion
- Data types: numbers, strings, booleans, lists, records
- Run via CLI: `pll run file.pll` or `pll run --bc file.pll` (bytecode)

### 🖥️ Frontend
- Monaco Editor with dark theme and PLL syntax highlighting
- Tree-based file manager with expand/collapse
- Git status bar (branch, changes, ahead/behind)
- Resizable panes between editor and results
- 30+ language auto-detection

### 🔧 Developer Features
- **Disk mode**: projects point to real filesystem directories
- **DB mode**: virtual projects stored in SQLite
- **Git integration**: init, commit (auto message via LLM), push, pull, status
- **GCA** (Generational Context Architecture): agent lifecycle with checkpoints
- **Package system**: PLL package registry

## CLI Reference

```bash
pll run file.pll        # Parse + typecheck + run via VM
pll run --bc file.pll   # Same but via bytecode
pll check file.pll      # Parse + typecheck only
pll compile file.pll    # Generate Rust code
pll tokens file.pll     # Show token stream
pll ast file.pll        # Show parsed AST
pll repl                # Interactive REPL
```

## Project Structure

```
pll/
├── server/              # Python FastAPI backend
│   ├── routes/          # REST API endpoints
│   ├── services/        # Agent brain, LLM proxy, GCA
│   └── playground/      # Frontend (HTML/JS/CSS)
├── crates/              # Rust crates
│   ├── pll-core/        # AST types, tokens
│   ├── pll-lexer/       # Tokenizer
│   ├── pll-parser/      # Parser
│   ├── pll-typeck/      # Type checker
│   ├── pll-codegen/     # Rust code generator
│   ├── pll-bytecode/    # Bytecode compiler + VM
│   ├── pll-runtime/     # Builtins (render, fs, db)
│   ├── pll-cli/         # CLI binary
│   ├── pll-wasm/        # WASM bindings (browser)
│   └── pll-wire/        # Agent wire protocol
└── target/release/      # Compiled binary
    └── pll-cli.exe      # CLI (pre-built, ~1.5MB)
```

## Build from Source

```bash
cd pll
cargo build --release -p pll-cli
```

Requires Rust 2021 edition.

## Status

Le projet est en phase de consolidation active. Le pipeline Rust compile et fonctionne, le serveur Python et le frontend sont opérationnels. Voir `ROADMAP.md` pour les prochaines étapes.
