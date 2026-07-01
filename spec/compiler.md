# PLL v2 — Compiler Architecture

## Pipeline

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Source   │───→│  Lexer   │───→│  Parser  │───→│   Type   │───→│   Code   │
│  (.pll)   │    │          │    │          │    │  Checker │    │  Gen     │───→ Rust
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                     │
                                                     ↓
                                              ┌──────────┐
                                              │ Contract  │
                                              │  Checker  │
                                              └──────────┘
```

## 1. Lexer

```
Input:  PLL source text (UTF-8)
Output: Vec<Token>

Token = Ident(String)
      | Keyword(Keyword)
      | Str(String)
      | Num(f64)
      | Bool(bool)
      | Op(Op)
      | Delim(Delim)
      | Newline
      | Indent
      | Dedent
      | Eof

Keywords = "t" | "p" | "cap" | "contract" | "agent" | "fork" | "if"
         | "else" | "par" | "join" | "converge" | "ui" | "route"
         | "render" | "emit" | "v" | "r" | "c" | "msg" | "on"
         | "pre" | "post" | "invariant" | "constraint"
         | "input" | "db_set" | "db_get" | "merge" | "true" | "false"
         | "and" | "or" | "under"
```

### Indentation Handling

PLL uses indentation for scoping (like Python). The lexer emits
`Indent`/`Dedent` tokens based on column tracking.

### Token Efficiency Extension

In agent communication mode, tokens use a symbol table:
```
Header: SymbolTable { "summarize": 0, "Person": 1, ... }
Body:   [Op::VarDecl, 0, 1]  // 4 tokens instead of ~10
```

## 2. Parser

```
Input:  Vec<Token>
Output: Program (AST)

Algorithm: Recursive descent with 1-token lookahead.
Each statement starts with a keyword or ident.

Parser stages:
  1. Parse top-level statements
  2. Resolve indentation blocks
  3. Build AST nodes
  4. Collect symbol table (types, protocols, capabilities, contracts)
```

### Error Recovery

The parser uses a panic-mode recovery: skip to the next statement
boundary on parse error, collect diagnostics.

## 3. Type Checker

```
Input:  Program (unchecked AST)
Output: Program (checked AST) | Vec<TypeError>

Passes:
  1. Symbol collection    — gather all type/proto/cap/contract defs
  2. Name resolution      — resolve all Ident references
  3. Type inference       — assign types to all expressions
  4. Confidence tracking  — propagate confidence constraints
  5. Contract validation  — check pre/post/invariant well-formedness
  6. Capability check     — verify agent capabilities match usage
```

### Type Checking Rules

See `type_system.md` for formal rules. Key additions:

```
Transform constraint:
  a => T: EXTRACT(a, T)  →  requires cap(extract, T) available

Agent handler check:
  on M: ...  →  M must be a message in the agent's protocol

Contract binding:
  x under C  →  all free vars in C.pre must be resolvable at binding point
```

## 4. Code Generator (PLL → Rust)

```
Input:  Program (checked AST)
Output: Rust source code

Target: Rust 2024 edition

CodeGen passes:
  1. Type lowering     — PLL types → Rust structs + serde derives
  2. Belief lowering   — Belief<T> → runtime::Belief<T>
  3. Handler gen       — agent handlers → async functions
  4. Runtime wiring    — LLM calls → runtime::LLM trait impls
  5. Contract gen      — pre/post checks → assert!() / runtime checks
  6. UI gen            — ui blocks → axum router + HTML templates
```

### 4.1 Type Lowering

```rust
// PLL: t Person [name, age:num, email:belief<String>]
// Rust:
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
struct Person {
    name: Belief<String>,
    age: Belief<f64>,
    email: Belief<Belief<String>>,
}
```

### 4.2 Belief Runtime

```rust
// Core runtime type
pub struct Belief<T> {
    pub value: T,
    pub confidence: f64,
    pub provenance: Vec<ProvenanceStep>,
}

// Trait for LLM integration
#[async_trait]
pub trait LLM: Send + Sync {
    async fn generate(&self, prompt: &str, ctx: &Context) -> Result<String>;
    async fn extract<T: DeserializeOwned + JsonSchema>(
        &self, source: &str, schema: &str, ctx: &Context
    ) -> Result<T>;
    async fn similarity(&self, a: &str, b: &str) -> Result<f64>;
}
```

### 4.3 Handler Generation

```rust
// PLL agent handler:
// on Query: reply = payload => Response; emit reply

// Rust:
async fn handle_query(
    payload: Query,
    ctx: &AgentContext,
    llm: &dyn LLM,
) -> Result<Response> {
    let reply: Belief<Response> = Belief::transform(
        payload.into(),
        TransformMode::Typed::<Response>,
        llm,
        0.80,  // decay factor
    ).await?;
    ctx.emit(reply).await?;
    Ok(reply.value)
}
```

## 5. AOT Compilation vs Interpretation

| Mode | Use Case | Tradeoff |
|------|----------|----------|
| **AOT** (compile to Rust) | Production agents, embedded systems | Fast, small binary; longer build |
| **JIT** (compile at agent load) | Dynamic agent mesh | Flexible, slower startup |
| **Interpreted** (eval AST) | REPL, debugging, agent sandbox | Maximum flexibility, slowest |

### Bootstrap strategy:

```
Phase 1: PLL → Rust (AOT compiler written in Rust)
Phase 2: PLL → Rust (compiler rewritten in PLL, bootstrapped)
Phase 3: PLL → PLL VM (self-hosted runtime)
```

## 6. Project Structure (Rust Workspace)

```
pll/
├── Cargo.toml              # workspace root
├── crates/
│   ├── pll-core/           # Core types: Belief, Provenance, TypeRef
│   ├── pll-lexer/          # Lexer → Token stream
│   ├── pll-parser/         # Parser → AST
│   ├── pll-typeck/         # Type checker
│   ├── pll-codegen/        # PLL → Rust codegen
│   ├── pll-runtime/        # Runtime: Belief ops, LLM trait, DB, UI
│   └── pll-cli/            # CLI: compile, run, repl
├── spec/                   # Formal specifications
├── examples/               # Example PLL programs
└── tests/                  # Integration tests
```

## 7. Compiler Diagnostics

```
Diagnostic = Error { level: ErrorLevel, span: Span, msg: String, hint: Option<String> }
ErrorLevel = Error | Warning | Note | ConfidenceLow(f64)

Example:
  error[E001]: type mismatch: expected Person, got String
    ┌─ agent.pll:12:5
    │
 12 │     result = input => "summarize"
    │              ────────────────────
    │              │
    │              ╰── expected Person, found String
    │
    hint: add a typed transform: `input => Person`
```
