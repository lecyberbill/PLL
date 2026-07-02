# PLL Agentic IDE — Architecture & Documentation

## Vue d'ensemble

```
┌──────────────────────────────────────────────────────────────────┐
│                    PLAYGROUND (Navigateur)                       │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐  │
│  │  Monaco Editor           │  │  Agent Chat 🤖               │  │
│  │  .py .rs .js .pll ...   │  │  "Crée une API Flask"        │  │
│  │  (auto-détecté)          │  │  → DeepSeek génère du code   │  │
│  └──────────────────────────┘  │  → Écrit sur le disque       │  │
│                                 │  → Checkpoint dans vault     │  │
│                                 └──────────────────────────────┘  │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐  │
│  │  GCA Panel               │  │  Console / Bytecode / VFS    │  │
│  │  Agents, vault, handoff  │  │  Exécution WASM, logs        │  │
│  └──────────────────────────┘  └──────────────────────────────┘  │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP (fetch)
┌──────────────────────────▼───────────────────────────────────────┐
│                    SERVEUR FastAPI (Python)                       │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ REST API │ │ GCA      │ │ LLM      │ │ Filesystem + Exec │   │
│  │ 25+ routes│ │Orchestrer│ │ Proxy    │ │ read/write/copy   │   │
│  │ projets  │ │cycle GCA │ │DeepSeek  │ │ rm/mkdir/exec     │   │
│  │ fichiers │ │naissance │ │LM Studio │ │ (confirmé)         │   │
│  │ agents   │ │→mort     │ │          │ └──────────────────┘   │
│  │ packages │ │handoff   │ └────┬─────┘                       │
│  └──────────┘ └──────────┘      │                               │
│                                  ▼                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Agent Brain / ReAct Loop / Coordinator                   │   │
│  │  21 outils : fichiers, git, web, shell, Python, PLL      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────────┐   │
│  │ SQLite (DB)  │  │ projects/      │  │ Vault GCA          │   │
│  │ projets      │  │ code généré    │  │ checkpoints + RAG  │   │
│  │ artefacts    │  │ sur le disque  │  │ cerveau externe    │   │
│  │ agents       │  │                │  │                    │   │
│  └──────────────┘  └────────────────┘  └────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

## PLL — Inter-Agent Language

PLL is a compact probabilistic language designed for agent-to-agent communication. It's not a general-purpose programming language — it's the protocol agents use to exchange information, plan tasks, and document work.

### Syntax
```
# Commentaire
v x != 42                   # Déclaration (opérateur !=)
fn add(a: num, b: num) -> num:  # Fonction typée
    return a + b
if x > 10:                  # Condition
    render "grand"
else:
    render "petit"
while i < 10:               # Boucle
    i != i + 1
foreach item in list:       # Itération
    render item
```

### Builtins
`render`, `print`, `read_file`, `write_file`, `str_concat`, `str_length`, `str_slice`, `str_to_num`, `str_from_num`, `list_new`, `list_push`, `list_get`, `list_length`, `db_set`, `db_get`, `send`, `recv`

## Architecture Rust

```
                    ┌─────────────┐
                    │  pll-core   │  ← AST, tokens, spans
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │pll-lexer │ │pll-parser│ │pll-typeck│
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             ▼            ▼            │
        ┌──────────┐ ┌──────────┐      │
        │pll-bytecode│ │pll-vm   │      │
        │compiler+VM│ │(supprimé)      │
        └────┬─────┘                   │
             │                         ▼
             ▼                  ┌──────────┐
        ┌──────────┐            │pll-codegen│
        │pll-cli  │            └──────────┘
        │  run,    │
        │  check,  │
        │  compile │
        └──────────┘
```

## Fichiers clés

| Fichier | Rôle |
|---------|------|
| `server/main.py` | Point d'entrée FastAPI |
| `server/routes/agentic.py` | Endpoint `/api/agentic/go` |
| `server/services/agent_brain.py` | Agent brain (LLM, RAG, vault) |
| `server/services/agent_react.py` | ReAct loop + 21 outils |
| `server/services/agent_coordinator.py` | Coordinateur multi-agent |
| `server/services/llm_proxy.py` | Proxy DeepSeek/LM Studio |
| `server/services/gca_orchestrator.py` | Cycle GCA |
| `server/routes/git_routes.py` | Git integration |
| `server/routes/pll_exec.py` | PLL execution via Rust |
| `playground/index.js` | Frontend Monaco + agent chat |
| `playground/index.html` | Interface utilisateur |
| `playground/editor-setup.js` | Monaco + PLL grammar |
| `crates/pll-bytecode/src/compiler.rs` | Compilateur bytecode |
| `crates/pll-bytecode/src/vm.rs` | VM bytecode |
| `crates/pll-core/src/lib.rs` | Types AST |
| `crates/pll-lexer/src/lib.rs` | Tokenizer |
| `crates/pll-parser/src/lib.rs` | Parser |
| `crates/pll-cli/src/main.rs` | CLI (`pll run`, `pll check`) |
