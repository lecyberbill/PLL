# PLL v2 — Probabilistic Type System

## Philosophy

Every value in PLL is a **belief** — not a certainty. Determinism is a special case
where confidence = 1.0. The type system propagates uncertainty explicitly.

---

## 1. Core Types

### 1.1 Primitive Types

| Type | Domain | Default Confidence | Semantics |
|------|--------|-------------------|-----------|
| `String` | `UTF-8` | 1.0 | Probabilistic string (may have noise) |
| `num` | `f64` | 1.0 | Real number with uncertainty |
| `bool` | `[0.0, 1.0]` | 1.0 | Continuous truth value (not binary) |
| `belief<T>` | `T × [0,1]` | — | A value paired with confidence |
| `dist<T>` | `T → [0,1]` | — | Probability distribution over T |
| `stream<T>` | lazy `T[]` | 1.0 | Lazy/infinite sequence |
| `event` | timestamp + payload | 1.0 | Temporal event |

### 1.2 Structural Types (user-defined via `t`)

```pll
t Person [name, age:num, email:belief<String>]
```

Compiles to a struct where every field carries confidence metadata.

### 1.3 Parametric / Higher-Kinded

```pll
t Result[T] [value:belief<T>, error:belief<String>?]
t Batch[T] [items:T[], confidence:num]
```

---

## 2. The Belief Monad

Every value `x: T` is actually `Belief<T>` internally:

```rust
struct Belief<T> {
    value: T,
    confidence: f64,          // [0.0, 1.0]
    provenance: Vec<Step>,    // derivation trace
    distribution: Option<Dist<T>>,  // optional full distribution
}
```

### 2.1 Confidence Algebra

| Operation | Formula | Description |
|-----------|---------|-------------|
| Identity | `c(a → a) = 1.0` | No transformation |
| Propagation | `c(a → b) = c(a) · c(op)` | Confidence decays through operations |
| Merge | `c(a ∧ b) = min(c(a), c(b))` | AND combination |
| Union | `c(a ∨ b) = max(c(a), c(b))` | OR combination |
| Weighted | `c(a ⊕ b) = w·c(a) + (1-w)·c(b)` | Weighted average |
| Product | `c(a × b) = c(a) · c(b)` | Independent combination |

### 2.2 Decay Factors by Operation

| Operation | Decay | Rationale |
|-----------|-------|-----------|
| `?("text")` | `1.0` | Direct initialization |
| `a => "prompt"` | `0.85` | LLM transformation |
| `a => TargetType` | `0.80` | Structured extraction |
| `a ~> "desc"` | `0.90` | Belief propagation |
| `merge(a, b)` | `0.95` | Information fusion |
| `` `code` `` | `1.0` | Deterministic meta-exec |

---

## 3. Provenance

Provenance is a first-class citizen — every belief carries its history.

```rust
struct Step {
    op: OpKind,          // transform, merge, extract, etc.
    inputs: Vec<UID>,    // source belief UIDs
    model: Option<String>, // which LLM/agent produced this
    timestamp: Instant,
    metadata: HashMap<String, Value>,
}
```

### 3.1 Provenance in PLL

```pll
x = ?("raw input") @ { source: "user", ts: now }
y = x => Person @ { step: "extraction", model: "gpt4" }

# y.provenance == [
#   { op: "init",   source: "user", ts: T0 },
#   { op: "extract", model: "gpt4", ts: T1 }
# ]
```

### 3.2 Provenance Queries

```pll
if x.provenance[0].source ~ "trusted" > 0.8:
    # use with high confidence

if y.provenance.filter("model == 'gpt4'").len > 0:
    # check if specific model was used
```

---

## 4. Protocol Types

Protocols define message schemas for agent↔agent communication.

```pll
p AgentProtocol:
    msg Query [text, context:num, timeout:num?]
    msg Response [result, confidence:num, provenance:belief<String>[]]
    constraint Response.confidence > 0.5
    constraint Query.text != ""
```

### 4.1 Serialization

Messages are compiled to:
- **Rust**: Typed enums with serde
- **Wire**: CBOR (compact binary) or token-efficient symbol table
- **Schema negotiation**: First exchange defines `t`, subsequent use indices

---

## 5. Contract Types

Contracts define pre/post conditions and invariants.

```pll
contract Extraction:
    pre:  input != "" and input ~ "text" > 0.3
    post: result.confidence > 0.7
    post: result.key_points.length >= 3
    invariant: result ~ input > 0.5   # semantic similarity preserved
```

### 5.1 Contract Enforcement

- **Compile-time**: Statically checkable conditions flagged
- **Runtime**: Verified at each `render` or `emit`
- **Negotiation**: Agents agree on contract before communication

---

## 6. Capability Types

Capabilities are types too — they define what an agent can do.

```pll
cap summarize [
    input: belief<String>,
    max_words: num
] -> [
    summary: belief<String>,
    cost: num
]
cap.cost: 0.002
cap.requires: "llm-v3"
cap.safety: ["no_pii", "max_output:1024"]
```

Capabilities form a **type hierarchy**:
- `cap A` is subtype of `cap B` if A's contract is stricter than B's
- Agents publish their capability set for discovery

---

## 7. Type Inference Rules

```
Γ ⊢ expr: T, c          # expression has type T with confidence c
───────────────────────
Γ ⊢ "lit": String, 1.0

Γ ⊢ a: T, c    Γ ⊢ b: T, c'
─────────────────────────────   (similarity)
Γ ⊢ a ~ b: num, min(c, c')

Γ ⊢ a: S, c    (prompt: String)
───────────────────────────────   (string transform)
Γ ⊢ a => prompt: String, c * 0.85

Γ ⊢ a: S, c    (Γ ⊢ T: type)
─────────────────────────────   (typed transform)
Γ ⊢ a => T: T, c * 0.80

Γ ⊢ a: belief<T>, c
────────────────────   (belief projection)
Γ ⊢ a.value: T, c

Γ ⊢ x: T, c    Γ ⊢ contract C: pre/post
    check(x, C.pre)                # runtime or static
─────────────────────────────────   (contract binding)
Γ ⊢ x under C: T, min(c, C.safety)
```
