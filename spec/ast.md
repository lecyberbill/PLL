# PLL v2 — Abstract Syntax Tree & Evaluation Model

## Role of the AST

The AST is the bridge between the grammar (what the agent writes/sends)
and the runtime (what executes). It preserves all semantic information:
types, confidence, provenance, and structure.

## 1. AST Root

```
Program {
    imports:     Vec<Import>,
    statements:  Vec<Stmt>,
    metadata:    ProgramMeta,
}

ProgramMeta {
    version:     String,
    zone:        String,        // "SAFE" | "EXPERIMENTAL" | "UNTRUSTED"
    lambda:      f64,           // confidence threshold for this program
    agent_id:    Option<String>,
}
```

## 2. Statements

```
Stmt = VarDecl
     | TypeDecl
     | ProtoDecl
     | CapDecl
     | ContractDecl
     | AgentDecl
     | Assign
     | Transform
     | Converge
     | ParBlock
     | Fork
     | If
     | MetaExec(StringExpr)
     | UiBlock
     | RouteBlock
     | Emit(Expr)
     | Render(Expr)
     | DbSet(Expr, Expr)
     | DbGet(Expr)
     | Block(Vec<Stmt>)
```

## 3. Variable & Belief State

```
VarDecl {
    name:        Ident,
    init:        BeliefInit,
    provenance:  Option<Provenance>,
}

BeliefInit {
    raw_text:    String,        // the "?" context
    confidence:  f64,           // always 1.0 at init
}

Assign {
    target:      Ident,
    source:      Expr,
}
```

## 4. Types (Compile-Time Representation)

```
TypeDecl {
    name:        Ident,
    fields:      Vec<Field>,
    params:      Vec<Ident>,    // generic params, e.g. T in Result[T]
    constraints: Vec<Expr>,     // type-level constraints
}

Field {
    name:        Ident,
    type_ref:    TypeRef,
    optional:    bool,
    default:     Option<Expr>,
}

TypeRef = Primitive(PrimType)
        | Named(Ident, Vec<TypeRef>)
        | Belief(Box<TypeRef>)
        | Dist(Box<TypeRef>)
        | Stream(Box<TypeRef>)
        | Arrow(Vec<TypeRef>, Box<TypeRef>)  // function type

PrimType = String | Bool | Num | Event
```

## 5. Protocol & Messages

```
ProtoDecl {
    name:        Ident,
    messages:    Vec<Message>,
    constraints: Vec<Expr>,
}

Message {
    name:        Ident,
    fields:      Vec<Field>,
}
```

## 6. Capability

```
CapDecl {
    name:        Ident,
    input:       Vec<Field>,
    output:      Vec<Field>,
    cost:        Option<f64>,
    requires:    Vec<String>,
    safety:      Vec<String>,
}
```

## 7. Contract

```
ContractDecl {
    name:        Ident,
    pre:         Vec<Expr>,
    post:        Vec<Expr>,
    invariants:  Vec<Expr>,
}
```

## 8. Transformation (The Core Operation)

```
Transform {
    target:      Ident,
    source:      Box<Expr>,
    mode:        TransformMode,
    contract:    Option<Ident>,
    verify:      Option<VerifyBlock>,
    provenance:  Option<Provenance>,
}

TransformMode = Prompt(String)
              | Typed(TypeRef)

VerifyBlock {
    checks:      Vec<Expr>,
    retry:       Option<RetryConfig>,
}

RetryConfig {
    temp_inc:    Option<f64>,
    attempts:    Option<u32>,
    model:       Option<String>,
    few_shot:    Option<u32>,
}
```

## 9. Convergence

```
Converge {
    target:      f64,           // target confidence
    patience:    u32,           // how many failures before giving up
    max_steps:   u32,
    strategy:    Vec<Strategy>,
    body:        Vec<Stmt>,
    result_var:  Ident,
}

Strategy = TempInc(f64)
         | FewShot(u32)
         | Model(String)
         | ChainOfThought
         | BestOf(u32)
```

## 10. Parallel Execution

```
ParBlock {
    branches:    Vec<Vec<Stmt>>,
    join:        Option<Join>,
}

Join {
    result_var:  Ident,
    mode:        JoinMode,
    threshold:   Option<f64>,   // minimum confidence threshold
}

JoinMode = Merge(Vec<Ident>)     // merge specific vars
         | First                 // take first to complete
         | WaitAll               // wait for all, union results
```

## 11. Semantic Branching

```
Fork {
    target:      Box<Expr>,
    cases:       Vec<Case>,
    else_branch: Option<Vec<Stmt>>,
}

Case {
    concept:     String,        // the semantic concept to match
    condition:   Expr,          // e.g., p > 0.7
    body:        Vec<Stmt>,
}

If {
    condition:   Expr,
    then:        Vec<Stmt>,
    else_:       Option<Vec<Stmt>>,
}
```

## 12. Agent Declaration

```
AgentDecl {
    name:        String,
    protocol:    Option<Ident>,
    state:       Vec<StateDecl>,
    handlers:    Vec<Handler>,
}

StateDecl {
    name:        Ident,
    init:        BeliefInit,
    persistent:  bool,
}

Handler {
    message:     Ident,         // message type this handler processes
    body:        Vec<Stmt>,
}
```

## 13. Expressions (The Core IR)

```
Expr = Literal(Literal)
     | Ident(String)
     | Unary { op: UnaryOp, expr: Box<Expr> }
     | Binary { op: BinaryOp, left: Box<Expr>, right: Box<Expr> }
     | Similarity { left: Box<Expr>, right: Box<Expr> }
     | BeliefProp { source: Box<Expr>, target: Box<Expr>, desc: Option<String> }
     | InlineTransform { source: Box<Expr>, mode: TransformMode }
     | Input(String)
     | Merge(Vec<Expr>)
     | MetaExec(Box<Expr>)
     | List(Vec<Expr>)
     | Member { obj: Box<Expr>, field: Ident }
     | Index { obj: Box<Expr>, index: Box<Expr> }
     | Call { func: Ident, args: Vec<Expr> }

Literal = Str(String)
        | Num(f64)
        | Bool(bool)

UnaryOp = Not | Negate | SemanticInvert

BinaryOp = Add | Sub | Mul | Div
         | Eq | Neq | Gt | Lt | Gte | Lte
         | And | Or
```

## 14. Provenance (Runtime Metadata)

```
Provenance {
    entries:     Vec<ProvEntry>,
}

ProvEntry {
    op:          OpKind,
    inputs:      Vec<Uid>,
    model:       Option<String>,
    timestamp:   Instant,
    metadata:    HashMap<String, Literal>,
}

OpKind = Init | Transform | Merge | Extract | Verify
       | Converge | Fork | AgentCall | MetaEval
```

## 15. Evaluation Model

### 15.1 Core Loop

```
eval(program, env):
    for stmt in program.statements:
        eval_stmt(stmt, env)
```

### 15.2 Belief Propagation

Every expression returns `Belief<T>`:

```
eval_expr(expr, env) -> Belief {
    value: T,
    confidence: f64,
    provenance: Vec<ProvEntry>,
}
```

### 15.3 Operation Semantics

| Construct | Evaluation |
|-----------|------------|
| `?("text")` | Create `Belief(text, 1.0, [Init])` |
| `a => prompt` | LLM call: `Belief(LLM(a, prompt), 0.85 * c(a), [Transform])` |
| `a => T` | Structured extraction: `Belief(extract(a, T), 0.80 * c(a), [Extract])` |
| `a ~ b` | Similarity score: `Belief(sim(a, b), min(c(a),c(b)), [])` |
| `a ~> "desc"` | Belief propagation: `Belief(LLM(a, desc), 0.90 * c(a), [Transform])` |
| `v expr` | Check `c(expr) > threshold`, retry on failure |
| `fork x: c "concept" (p > 0.7)` | Check `sim(x, "concept") > 0.7` |
| `par { A } { B } join r: merge(a,b)` | Execute A, B in parallel, merge results |
| `` `code` `` | Parse and eval code string at runtime |
| `emit x` | Serialize x and send to agent channel |
| `render x` | Serialize x to HTTP response |

### 15.4 Confidence Thresholds

```
Execution Mode      Default λ   Behavior
──────────────────────────────────────────────────
SAFE                0.95        Block if confidence < λ
NORMAL              0.70        Warn if confidence < λ
EXPERIMENTAL        0.30        Execute anyway, tag results
UNTRUSTED           0.00        Execute, no guarantees
```
