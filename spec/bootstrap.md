# PLL v2 — Bootstrapping & Self-Hosting Plan

## The Goal

A PLL compiler **written in PLL** that compiles itself.

This is the ultimate verification that the language is expressive enough
for any task — including language implementation.

## Three-Phase Bootstrap

### Phase 1: Rust Host (Current → MVP)

```
PLL source  ──→  Rust compiler (Rust)  ──→  Native binary
                 ┌──────────────┐
                 │ pll-compiler │  (written in Rust)
                 └──────────────┘
```

**Deliverables:**
- Lexer, parser, type checker, code gen in Rust
- Runtime library (Belief, LLM trait, etc.)
- CLI: `pll compile`, `pll run`, `pll repl`
- Agent protocol implementation

**Milestone:** PLL can compile itself from Rust-hosted compiler.

### Phase 2: Bootstrap (PLL Takes Over)

```

PLL source (compiler)  ──→  Rust compiler  ──→  pll-compiler (v1 binary)
                                 │
                                 ▼
PLL source (compiler v2)  ──→  pll-compiler v1  ──→  pll-compiler v2
```

**Deliverables:**
- Rewrite the compiler in PLL (lexer, parser, codegen)
- Use Phase 1 compiler to compile the PLL compiler
- Result: a native binary produced entirely from PLL sources

**Milestone:** `pll compile compiler.pll` produces a working compiler.

### Phase 3: Self-Hosted Runtime (PLL VM)

```
PLL source  ──→  PLL compiler (PLL)  ──→  PLL bytecode
                                              │
                                              ▼
                                         PLL VM
                                      (written in PLL)
```

**Deliverables:**
- PLL bytecode format (compact IR)
- PLL VM written in PLL
- No Rust dependency for execution

**Milestone:** PLL runs on PLL. Full self-hosting.

---

## Why Bootstrap?

| Reason | Explanation |
|--------|-------------|
| **Dogfooding** | If agents must use PLL, the compiler itself must be an agent |
| **Self-improvement** | An agent can modify its own compiler → recursive self-improvement |
| **Trust** | No opaque binary: the compiler is readable, auditable PLL code |
| **Portability** | PLL VM in PLL → run anywhere there's a minimal PLL runtime |
| **Meta-circularity** | `eval` becomes trivial: parse self, execute self |

## Incremental Path

Rather than a big rewrite, each compiler component is replaced one by one:

```
Phase 1a: PLL lexer written in PLL (parses token streams, tested against Rust lexer)
Phase 1b: PLL parser written in PLL  (produces AST, cross-validated)
Phase 1c: PLL type checker in PLL
Phase 1d: PLL codegen in PLL
```

At each step, the Rust compiler calls out to the PLL component for that stage.

## Self-Hosting Test

```pll
# The ultimate test — compile the compiler with itself:
# Step 1: Phase 1 compiler compiles the PLL compiler
$ pllc-rust compiler.pll -o pllc-v1

# Step 2: v1 compiles itself
$ pllc-v1 compiler.pll -o pllc-v2

# Step 3: Verify v1 and v2 produce identical binaries
$ diff <(pllc-v1 compiler.pll -o /dev/stdout) \
        <(pllc-v2 compiler.pll -o /dev/stdout)
```

## Identity Agent

The compiler itself is a PLL agent:

```pll
agent "pll-compiler":
    cap parse     [source:String]   -> [ast:Program]
    cap typecheck [ast:Program]     -> [checked:Program, errors:Error[]]
    cap codegen   [checked:Program] -> [output:RustSource, warnings:Warning[]]
    cap compile   [source:String]   -> [binary:Bytes]

    cap.cost: 0.0   # compiler is deterministic, zero LLM cost
    cap.requires: "rustc"   # still needs rustc as backend

    on parse:
        result = source => Program
        emit result

    on compile:
        ast     = parse(source)
        checked = typecheck(ast)
        rust    = codegen(checked)
        binary  = invoke_rustc(rust)   # eventually: PLL VM bytecode
        emit binary
```
