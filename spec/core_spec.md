# PLL v2 — Core Language Specification

> Version: 2.0.0-draft
> Status: Foundation
> This document supersedes `grammar.ebnf`, `type_system.md`, and `ast.md`.

---

## 0. Philosophy

PLL is a language designed **by and for agents**. Every value is a **belief**
— a proposition with confidence, provenance, and optional distribution.
Determinism is `Belief<T>` where confidence = 1.0.

The language serves two roles simultaneously:
- **Exchange format**: agent A sends a PLL program to agent B
- **Executable semantics**: agent B evaluates the PLL program locally

---

## 1. Lexical Structure

### 1.1 Tokens

```
letter    = "A".."Z" | "a".."z" | "_"
digit     = "0".."9"
ident     = letter { letter | digit }
string    = '"' { unicode_no_quote_or_backslash | escape } '"'
escape    = "\\" ("n" | "t" | "r" | '"' | "\\")
decimal   = digit { digit }
float     = decimal "." decimal ["e" ["+" | "-"] decimal]
bool_lit  = "true" | "false"
newline   = '\n' | '\r\n'
indent    = emitted by lexer when indentation increases
dedent    = emitted by lexer when indentation decreases
```

### 1.2 Indentation

PLL uses indentation for scoping (Python-style). The lexer tracks
column position and emits `Indent`/`Dedent` tokens. A `block` is:

```
block = ":" newline indent { statement } dedent
```

Inline blocks are also possible for single statements:

```
if expr: stmt
```

### 1.3 Operator Precedence (lowest to highest)

```
Level 0:  `=>` `~>`     (transform, belief propagation)
Level 1:  `or`          (logical or)
Level 2:  `and`         (logical and)
Level 3:  `~`           (semantic similarity — returns num)
Level 4:  `==` `!=` `>` `<` `>=` `<=`
Level 5:  `+` `-`
Level 6:  `*` `/`
Level 7:  unary `!` `-` `~`
Level 8:  `.` `[]` `()` (member access, index, call)
```

---

## 2. Program Structure

```
program     = header? { statement } eof
header      = "#" "[" meta_item { "," meta_item } "]" newline
meta_item   = ident ":" value
value       = string | decimal | ident

statement   = import_stmt
            | var_decl
            | type_decl
            | proto_decl
            | cap_decl
            | contract_decl
            | agent_decl
            | assign
            | transform_stmt
            | converge_block
            | par_block
            | fork_stmt
            | if_stmt
            | meta_exec
            | ui_block
            | route_block
            | emit_stmt
            | render_stmt
            | db_set_stmt

import_stmt = "import" string
```

---

## 3. Variables & Belief States

```
var_decl    = ident "=" "?" "(" string ")" provenance?
assign      = ident "=" expr

provenance  = "@" "{" prov_entry ("," prov_entry)* "}"
prov_entry  = ident ":" expr
```

All variables are **immutable after assignment** (single-assignment).
Reassignment is a compile error. This matches the agent paradigm:
each belief is derived once, then refined.

### Internal runtime representation

```rust
struct Belief<T> {
    value: T,
    confidence: f64,          // [0.0, 1.0]
    provenance: Vec<ProvStep>, // derivation trace
}
```

**Important**: Every value `x: T` IS a `Belief<T>` at runtime. The explicit
`belief<T>` type annotation does NOT double-wrap. It is a type-level
reminder that the value carries uncertainty. `String` and `belief<String>`
are the **same runtime type**.

```
Γ ⊢ "lit": String, 1.0      (always confidence 1.0 for literals)
Γ ⊢ ?("text"): String, 1.0  (belief initialized with full confidence)
```

---

## 4. Type System

### 4.1 Primitive Types

| Type | Domain | Description |
|------|--------|-------------|
| `String` | UTF-8 | Probabilistic string |
| `num` | `f64` | Real number |
| `bool` | `[0.0, 1.0]` | Continuous truth value (not binary) |
| `belief<T>` | — | Explicit annotation: same runtime as `T` |
| `dist<T>` | probability mass fn | Full distribution over T |
| `stream<T>` | lazy sequence | Potentially infinite, pull-based |
| `event` | timestamp + payload | Temporal event |
| `T[]` | variable-length array | Homogeneous list |

### 4.2 Structural Types

```
type_decl   = "t" ident generics? "[" field ("," field)* "]"
generics    = "[" ident ("," ident)* "]"
field       = ident (":" type_ref)? ("?")?
type_ref    = "String" | "bool" | "num" | "event"
            | "belief" "<" type_ref ">"
            | "dist" "<" type_ref ">"
            | "stream" "<" type_ref ">"
            | type_ref "[]"
            | ident ("[" type_ref ("," type_ref)* "]")?    // named type
```

Parameteric types use `[]` consistently:

```pll
t Result[T] [value:T, error:belief<String>?]
t Batch     [items:String[], count:num]
t Pipeline  [input:belief<String>, output:belief<Result[String]>]
```

### 4.3 Arrays

```
Γ ⊢ a: T, c    Γ ⊢ b: T[], c'
─────────────────────────────────
Γ ⊢ [a, ...b]: T[], min(c, c')
```

Array access: `arr[i]` returns `belief<T>` (confidence = min(c(arr), 1.0)).

### 4.4 Confidence Algebra

```
Identity:      c(x → x)          = 1.0
Propagation:   c(a → f(a))       = c(a) · decay(f)
Conjunction:   c(a ∧ b)          = min(c(a), c(b))
Disjunction:   c(a ∨ b)          = max(c(a), c(b))
Product:       c(a × b)          = c(a) · c(b)
Weighted:      c(a ⊕ b, w)       = w·c(a) + (1-w)·c(b)
```

### 4.5 Operation Decay Factors

| Operation | Decay | Formula |
|-----------|-------|---------|
| `?("text")` | 1.0 | `c = 1.0` |
| `a => "prompt"` | 0.85 | `c = c(a) · 0.85` |
| `a => T` | 0.80 | `c = c(a) · 0.80` |
| `a ~> "desc"` | 0.90 | `c = c(a) · 0.90` |
| `merge(a, b)` | 0.95 | `c = min(c(a), c(b)) · 0.95` |
| `` `code` `` | 1.0 | `c = 1.0` |
| `arr[i]` | 1.0 | `c = c(arr)` |
| `obj.field` | 1.0 | `c = c(obj)` |

### 4.6 Branch Confidence

```
fork x:
    c "concept" (p > 0.7): y = ...
    else:                  z = ...

result confidence = max(selected.confidence, fork_threshold(x, "concept"))
```

After a `fork`, the result confidence is the **maximum** of the matched case
confidence and the semantic similarity that triggered the case. This prevents
a confident match from being lost.

### 4.7 Capability Types

Capabilities form a **partial order** by contract strictness:

```
cap A is a subtype of cap B (A ⊑ B) iff:
  1. A.input[i] ⊑ B.input[i] for all i  (contra-variant)
  2. B.output[i] ⊑ A.output[i] for all i (co-variant)
  3. A.pre implies B.pre                   (stronger preconditions)
  4. B.post implies A.post                 (stronger postconditions)
  5. A.cost ≤ B.cost                       (cheaper is stricter)
```

### 4.8 Type Inference Rules

```
Γ ⊢ "lit": String, 1.0

Γ ⊢ a: T, c    Γ ⊢ b: T, c'
─────────────────────────────
Γ ⊢ a ~ b: num, min(c, c')

Γ ⊢ a: String, c    (prompt: String)
────────────────────────────────────
Γ ⊢ a => prompt: String, c · 0.85

Γ ⊢ a: String, c    (Γ ⊢ T: type)
──────────────────────────────────
Γ ⊢ a => T: T, c · 0.80

Γ ⊢ a: belief<T>, c                    (note: belief<T> ≡ T at runtime)
────────────────────
Γ ⊢ a.value: T, c

Γ ⊢ arr: T[], c
────────────────
Γ ⊢ arr[i]: T, c

Γ ⊢ obj: { f1: T1, ... }, c
────────────────────────────
Γ ⊢ obj.fk: Tk, c

Γ ⊢ x: T, c    Γ ⊢ contract C(π): pre(x, π)
    check(x, C.pre)                        (static or runtime)
────────────────────────────────────────────
Γ ⊢ x under C: T, min(c, C_safety)
```

---

## 5. Protocols

```
proto_decl  = "p" ident block
proto_block = { msg_decl | constraint_decl }
msg_decl    = "msg" ident "[" field ("," field)* "]"
constraint_decl = "constraint" expr
```

Protocols define message schemas for agent↔agent communication.

```pll
p BookingProtocol:
    msg BookIntent [action, params:num, confidence:num]
    msg BookingResult [status, booking_ref:String?, confidence:num]
    constraint BookIntent.confidence > 0.5
    constraint BookingResult.status in ["confirmed", "pending", "rejected"]
```

### Serialization

Messages are serialized via CBOR using a **shared symbol table**.
After handshake, all type/protocol names are mapped to 16-bit indices.
A message `BookIntent { action: "search", confidence: 0.92 }` on the wire:

```
[Op::Emit, 0, 1, [1, ["search", 0.0, 0.92]]]
  // 0 = schema_id (BookingProtocol)
  // 1 = message_id (BookIntent)
  // [1, ...] = field values with symbol indices
```

---

## 6. Contracts

```
contract_decl = "contract" ident "(" params? ")" block
contract_block = { pre_stmt | post_stmt | invariant_stmt }
pre_stmt      = "pre" ":" expr
post_stmt     = "post" ":" expr
invariant_stmt = "invariant" ":" expr
```

Contracts have explicit parameters to bind free variables:

```pll
contract BookingAccuracy(input, expected_ref):
    pre:  input.confidence > 0.5
    post: result.ref == expected_ref
    invariant: result.confidence > 0.6

# Usage:
result = input => BookingResult under BookingAccuracy(input, "ABC123")
```

### Enforcement

- **Static**: Conditions on constants are checked at compile time
- **Runtime**: Dynamic conditions checked at `emit`/`render`
- **Negotiation**: Agents exchange contracts before message exchange

---

## 7. Capabilities

```
cap_decl    = "cap" ident func_sig cap_meta*
func_sig    = "[" params? "]" "->" "[" params? "]"
cap_meta    = "cap" "." ("cost" ":" expr | "requires" ":" string | "safety" ":" "[" string* "]")
```

```pll
cap summarize [
    input: String,
    max_words: num
] -> [
    summary: String,
    cost: num
]
cap.cost: 0.002
cap.requires: "llm-v3"
cap.safety: ["no_pii", "max_output:1024"]
```

---

## 8. Transformations

```
transform_stmt = ident "=" expr "=>" (string | type_ref)
                 ("under" ident "(" args? ")")?
                 verify_block?
verify_block = ":" newline indent
               { "v" expr newline }
               ["r" "(" retry_param ("," retry_param)* ")" newline]
               dedent
retry_param  = "temp" ("+=" | "=") expr
             | "attempts" "=" expr
             | "model" "=" string
             | "few_shot" "=" expr
```

```pll
# String transform:
summary = doc => "Summarize this text in 3 sentences"

# Typed transform with verification and retry:
person = text => Person:
    v person.name != ""
    v person.age > 0
    r (temp += 0.2, attempts = 3)

# Transform with contract:
result = data => BookingResult under BookingAccuracy(data, "REF1")
```

### Retry Confidence

After `n` successful attempts with temperature `T`:

```
c_final = c_base · (1 - (1 - success_rate)^n)
```

Each retry increases probability of correctness via repeated sampling.
The final confidence reflects the empirical success rate, not just decay.

---

## 9. Convergence

```
converge_block = "converge" "(" converge_param ("," converge_param)* ")" block
converge_param = "target" ":" expr | "patience" ":" expr | "max_steps" ":" expr
```

```pll
extracted = source => Person:
    converge (target: 0.95, patience: 2, max_steps: 5):
        strategy: ["temp+0.1", "few_shot+2"]
        v extracted.name != ""
        v extracted.age > 0
```

A converge block wraps a transform with an iterative self-correction loop:
1. Execute the body
2. Check verification conditions
3. If confidence < target, adjust strategy and retry
4. Stop when confidence ≥ target or patience exhausted
5. Return best result seen

---

## 10. Parallel Execution

```
par_block   = "par" block join_clause?
join_clause = "join" ident ":" (ident | merge_expr)
merge_expr  = "merge" "(" ident ("," ident)* ")" ("~>" string "(" merge_param ")")?
merge_param = "threshold" ":" expr
```

```pll
par:
    summary   = doc => "Summarize"
    entities  = doc => "Extract entities"
    sentiment = doc => "Classify sentiment"
join result:
    merged = merge(summary, entities, sentiment) ~> "Unify" (threshold: 0.8)
```

### Semantics

- All branches execute concurrently (async)
- Variables defined in branches are NOT visible to each other
- The `join` merge function has access to all branch results
- Results with confidence < threshold are excluded from merge

---

## 11. Semantic Branching

### `fork` — concept-based dispatch

```
fork_stmt = "fork" expr block
fork_block = indent { case_stmt } else_stmt? dedent
case_stmt = "c" string "(" expr ")" block
else_stmt = "else" block
```

```pll
fork user_input:
    c "book a flight" (p > 0.7):
        intent = user_input => BookIntent
    c "cancel booking" (p > 0.7):
        intent = user_input => CancelIntent
    else:
        intent = user_input => UnknownIntent
```

`fork` uses **semantic similarity** against concept strings. The condition
`p > 0.7` is the required similarity threshold. The first matching case
wins (top-to-bottom priority).

### `if` — boolean expression branch

```
if_stmt = "if" expr block ("else" block)?
```

`if` uses **deterministic boolean expressions**. No LLM call. Used for
confidence thresholds, field checks, and control flow.

```pll
if person.confidence > 0.8:
    emit person
else:
    person = person => "Verify and correct" under StrictCheck
```

### Fork vs If

| Aspect | `fork` | `if` |
|--------|--------|------|
| Condition type | Semantic string concept | Boolean expression |
| LLM call | Yes (`~` similarity) | No |
| Use case | Intent classification, NL routing | Confidence checks, data validation |
| Cost | High (one sim per case) | Zero |
| Confidence impact | `max(c_match, c_case)` | None (`c` unchanged) |

---

## 12. Agent Declaration

```
agent_decl = "agent" string ("on" ident)? block
agent_block = indent { state_decl | handler } dedent
state_decl = ident "=" "?" "(" string ")" provenance?
             ("@" "persistent")?
handler   = "on" ident block
```

```pll
agent "booking_agent" on BookingProtocol:
    ctx = ?("booking context") @ { source: "init" } @ persistent

    on BookIntent:
        validated = payload => BookIntent:
            v validated.action != ""
            r (attempts = 2)

        result = validated => BookingResult
        emit result
```

### Handler dispatch

When an agent receives a message `m` of type `T`:
1. Look up handler for `T`
2. Bind `payload` to the message contents
3. Execute handler body
4. Any `emit` statements send results back to caller

---

## 13. Meta-Execution

```
meta_exec = "`" expr "`"
```

Backtick evaluates a string expression as PLL code at runtime:

```pll
code = ?("generate PLL to extract emails from text")
result = `code`        # compiles and executes the generated PLL
```

Meta-execution is **sandboxed** by the current capability scope.
The generated code shares the same symbol table and cannot use
undeclared capabilities.

---

## 14. UI & Routing

```
ui_block    = "ui" block
route_block = "route" string block
```

```pll
ui:
    "<h1>Agent Interface</h1>"
    "<form action='/ask' method='get'>"
    "  <input type='text' name='query'/>"
    "  <button type='submit'>Ask</button>"
    "</form>"

route "/ask":
    q = input("query")
    res = q => Response
    render res
```

---

## 15. I/O and Persistence

```
emit_stmt   = "emit" expr
render_stmt = "render" expr

db_set_stmt = "db_set" "(" expr "," expr ")"
db_get_expr = "db_get" "(" expr ")"
```

- `emit`: Send value to the calling agent (wire protocol)
- `render`: Send value as HTTP response (UI mode)
- `db_set(key, val)`: Persist key-value to local JSON store
- `db_get(key)`: Retrieve persisted value (can appear in any expression)

```pll
last = db_get("last_query")
render "Previous: {last}"
```

---

## 16. Expression Grammar (Unified)

```
expr       = transform_expr

transform_expr = prop_expr ("=>" (string | type_ref) | "~>" string)?
prop_expr = or_expr ("~>" string)?         # belief propagation
or_expr   = and_expr ("or" and_expr)*
and_expr  = sim_expr ("and" sim_expr)*
sim_expr  = comp_expr ("~" comp_expr)?     # semantic similarity
comp_expr = add_expr (("==" | "!=" | ">" | "<" | ">=" | "<=") add_expr)?
add_expr  = mul_expr (("+" | "-") mul_expr)*
mul_expr  = unary_expr (("*" | "/") unary_expr)*
unary_expr = ("!" | "-" | "~") unary_expr | postfix_expr
postfix_expr = primary ("." ident | "[" expr "]" | "(" args? ")")*
primary    = literal
           | ident
           | "(" expr ")"
           | "input" "(" string ")"
           | "db_get" "(" string ")"
           | "merge" "(" args ")"
           | "[" [expr ("," expr)*] "]"
           | meta_exec
           | "?" "(" string ")" provenance?

literal    = string | float | decimal | bool_lit
args       = expr ("," expr)*
```

### Expression Side Effects

| Expression | Side Effect |
|------------|-------------|
| `a => prompt` | LLM call |
| `a => T` | LLM call (structured extraction) |
| `` `code` `` | Code execution |
| `input(name)` | HTTP request read |
| `db_get(k)` | File I/O |
| `merge(args)` | None |
| All others | Pure |

---

## 17. Scoping Rules

```
Scope      = ProgramScope     (top-level)
           | BlockScope       (indented block)
           | HandlerScope     (inside agent handler)
           | ParBranchScope   (one branch of par)
           | CaseScope        (one case of fork)

Visibility:
  - Variables are visible from declaration point to end of enclosing scope
  - Inner scopes can see outer scopes (lexical scoping)
  - Par branches CANNOT see each other's variables
  - Handler can see its agent's state declarations
  - `payload` is implicitly declared in each handler

Shadowing: NOT allowed. Redeclaring a name in a nested scope is an error.
```

---

## 18. Evaluation Model

### 18.1 Core Loop (Async)

```
async eval(program, env, llm):
    env.λ = program.metadata.lambda     # confidence threshold
    for stmt in program.statements:
        await eval_stmt(stmt, env, llm)
```

### 18.2 Confidence Guard

Before any `emit` or `render`, the runtime checks:

```
if result.confidence < env.λ:
    if env.zone == "SAFE":
        raise ConfidenceError(result.confidence, env.λ)
    else if env.zone == "EXPERIMENTAL":
        log warning, continue
    // UNTRUSTED: always continue
```

### 18.3 Operation Semantics

| Construct | Behavior |
|-----------|----------|
| `?("text")` | `Belief(text, 1.0, [Init])` |
| `a => prompt` | `Belief(llm.generate(a, prompt), c(a)·0.85, [Transform])` |
| `a => T` | `Belief(llm.extract(a, T), c(a)·0.80, [Extract])` |
| `a ~ b` | `Belief(llm.similarity(a, b), min(c(a),c(b)), [])` |
| `a ~> "desc"` | `Belief(llm.propagate(a, desc), c(a)·0.90, [Propagate])` |
| `v cond` | if `c(cond) < env.λ` → retry or fail |
| `r(...)` | Re-execute with adjusted params, update confidence |
| `` `code` `` | Parse string → eval in sandboxed env |
| `fork x: ...` | `max(sim(x, concept_i))` → eval matching case |
| `par {A} {B}` | `await Promise.all([A, B])` |
| `emit x` | Serialize x → write to agent channel |
| `render x` | Serialize x → write to HTTP response |
| `db_set(k, v)` | Write to local JSON store |
| `db_get(k)` | Read from local JSON store |

### 18.4 Verification & Retry Semantics

```
verify(transform, checks, retry_cfg):
    for attempt in 0..retry_cfg.max_attempts:
        result = execute(transform)
        all_pass = true
        for check in checks:
            if eval(check, env_with(result)).confidence < env.λ:
                all_pass = false
                break
        if all_pass:
            result.confidence *= confidence_boost(attempt, retry_cfg)
            return result
        if attempt < retry_cfg.max_attempts - 1:
            adjust_strategy(retry_cfg)
    return best_result_so_far  // with warning
```

Confidence boost after `n` successful verifications (across retries):

```
c_final = c_base · (1 - (1 - p_single)^n)
// where p_single = 0.8 (typical LLM success rate per attempt)
```

---

## 19. Agent Wire Protocol

### 19.1 Message Envelope

```rust
struct Envelope {
    version:     u8,           // protocol version (2)
    msg_type:    MsgType,       // SCHEMA | DATA | HELLO | ACK | ERROR
    schema_id:   Option<u16>,   // reference to negotiated schema
    payload:     Vec<u8>,       // CBOR-encoded
    sender:      AgentId,
    signature:   Option<Signature>,
    deadline:    Option<Instant>,
}
```

### 19.2 Handshake

```
A → B: HELLO { version, caps: [cap_ids], protocols: [proto_ids] }
B → A: ACK   { accepted_caps, accepted_protos, schema_version }
A → B: SCHEMA { t, p, c definitions }  // only if schema_version differs
// ... subsequent messages use symbol table indices
```

### 19.3 Symbol Table

After schema negotiation, all type and message names are 16-bit indices.
The wire format for a `msg BookIntent ["search", 0.92]`:

```
[Envelope{ msg_type: DATA, schema_id: 0 },
 [1, ["search", 0.92]]]    // 1 = message index within schema
```

A full NL-equivalent message would be ~15 tokens. The PLL wire format: ~5.
---

## 20. Self-Hosting Strategy

```
Phase 1: PLL → Rust compiler (written in Rust)
Phase 2: Rewrite compiler in PLL; compile with Phase 1 compiler
Phase 3: Design PLL bytecode; write PLL VM in PLL
Phase 4: Self-hosting: PLL VM runs PLL compiler running PLL programs
```

See `bootstrap.md` for the complete plan.

---

## Appendix: Summary of Changes from v1

| Area | v1 (original reference) | v2 (this spec) |
|------|------------------------|----------------|
| Grammar | Informal markdown | Formal EBNF with precedence |
| Indentation | Mentioned | Lexer-emitted Indent/Dedent |
| Types | `t` with fields | Full parametric, `belief<>`, `dist<>`, `stream<>`, `T[]` |
| Confidence | Implicit | Exhaustive algebra, decay factors, branch confidence |
| Operators | `~` only | `~`, `~>`, `=>`, full precedence levels |
| Control flow | `fork` + `if` | Both, with clear semantic distinction |
| Par/async | None | `par`/`join` with async eval |
| Agent comm | `emit` only | Full protocol, handshake, symbol table |
| Contracts | Pre/post only | Explicit binding parameters, formal subcontracting |
| Meta | None | `` `code` `` meta-execution |
| Scoping | None | Lexical scoping rules |
| Retry | `r(attempts=N)` | Confidence recalculation, success-rate boost |
