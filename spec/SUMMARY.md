# PLL v2 — Specification Index

## Source of Truth

| File | Status | Description |
|------|--------|-------------|
| **`core_spec.md`** | **Stable** | Consolidated grammar + types + AST + eval model (supersedes v1 docs) |
| `compiler.md` | Draft | Pipeline, codegen, project structure |
| `agent_protocol.md` | Draft | Agent mesh, wire protocol, discovery, safety |
| `bootstrap.md` | Draft | Self-hosting plan, 3-phase bootstrap |
| `grammar.ebnf` | Legacy | Superseded by core_spec.md |
| `type_system.md` | Legacy | Superseded by core_spec.md |
| `ast.md` | Legacy | Superseded by core_spec.md |

## Quick Reference

```
Core Spec   → spec/core_spec.md       (grammar, types, AST, eval — single file)
Compiler    → spec/compiler.md        (how it becomes Rust)
Protocol    → spec/agent_protocol.md  (how agents talk)
Bootstrap   → spec/bootstrap.md       (how it eats itself)
Roadmap     → ROADMAP.md              (implementation phases)
```

## Next Steps

See `ROADMAP.md` for the implementation plan.
