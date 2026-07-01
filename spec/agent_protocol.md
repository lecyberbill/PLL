# PLL v2 — Agent Protocol & Mesh Communication

## Vision

Two agents communicate by exchanging **PLL programs**, not serialized data.
The receiving agent evaluates the program in its own context — sandboxed by
capability and contract.

```
Agent A                          Agent B
   │                                │
   ├─ "t Intent [action, conf:num]" │  (schema negotiation)
   ├─ "m 0 [book_flight, 0.92]"     │  (ultra-dense message)
   │                              ──┤
   │                                ├─ eval("m 0 [...]") 
   │                                ├─ match handler on "Intent"
   │                                ├─ reply: "m 1 [confirmed, 0.95]"
   │←───────────────────────────────┤
```

## 1. Protocol Definition (`p`)

```pll
p BookingProtocol:
    msg BookIntent [action, params:belief<BookingParams>, confidence:num]
    msg BookingResult [status, booking_id:String?, confidence:num]
    constraint BookIntent.confidence > 0.5
    constraint BookingResult.status in ["confirmed", "pending", "rejected"]
```

## 2. Agent Declaration (`agent`)

```pll
agent "booking_agent" on BookingProtocol:
    state = ?("booking_context") @ persistent:true

    on BookIntent:
        validated = payload => BookIntent:
            v validated.action != ""
            v validated.confidence > 0.5
            r (attempts = 2, temp += 0.1)

        result = validated => BookingResult under BookingAccuracy
        emit result
```

## 3. Wire Protocol

### 3.1 Handshake (First Contact)

```
A → B: PLL_HELLO { version: "2.0", capabilities: [cap1, cap2, ...] }
B → A: PLL_ACK   { version: "2.0", accepted: [cap1, cap3], rejected: [cap2] }
A → B: PLL_SCHEMA { type: t, protocol: p, contract: c }
```

### 3.2 Symbol Table Optimization

After handshake, both sides share a symbol table. Messages use indices:

```
# Full:   t Intent [action, confidence:num]
# Index:  [t, 0, [action, confidence:num]]  → assign index 0 to Intent

# Full:   msg BookIntent [action, params, confidence:num]
# Index:  [msg, 1, [action, params, confidence:num]]  → assign index 1

# Message: emit BookIntent { action: "search", confidence: 0.9 }
# Wire:    [Op::Emit, [1, ["search", null, 0.9]]]     ~8 tokens vs ~20
```

### 3.3 Message Envelope

Every message is wrapped in a standard envelope:

```rust
struct Envelope {
    version:    u8,           // protocol version
    msg_type:  MsgType,       // SCHEMA | DATA | HELLO | ACK | ERROR
    schema_id: Option<u16>,   // reference to negotiated schema
    payload:   Vec<u8>,       // CBOR-encoded message data
    sender:    AgentId,
    signature: Option<Signature>,  // optional capability signing
    deadline:  Option<Instant>,    // optional timeout
}
```

## 4. Message Routing

### 4.1 Agent Registry

```
Registry {
    agents: HashMap<AgentId, AgentInfo>,
}

AgentInfo {
    id:           AgentId,
    protocol:     ProtoDecl,
    capabilities: Vec<CapDecl>,
    address:      SocketAddr,
    status:       Online | Busy | Offline,
}
```

### 4.2 Capability-Based Routing

Messages are routed by capability, not by address:

```pll
# Agent A needs summarization:
# A → Registry → find agent with cap(summarize)
# Registry → B: route Request to B
# B → A: emit Response
```

## 5. Safety & Sandboxing

### 5.1 Capability Enforcement

```rust
struct CapabilityGuard {
    allowed:   Vec<String>,     // allowed action patterns
    budget:    Budget,          // token/cost limits
    sandbox:   SandboxLevel,    // NONE | READ_ONLY | STRICT
}

enum SandboxLevel {
    None,                       // full access (trusted agent)
    ReadOnly,                   // can read state, no writes
    Strict {                     // isolated execution
        max_steps: u32,
        no_network: bool,
        no_filesystem: bool,
        allowed_models: Vec<String>,
    },
}
```

### 5.2 Contract Enforcement

All cross-agent `emit` calls are wrapped with contract validation:

```pll
# Source agent:
emit result under BookingAccuracy

# Receiving agent validates:
#   check pre: result ~ expected > 0.5
#   check post: result.confidence > 0.7
#   check invariant: result.booking_id != ""
```

## 6. Agent Discovery

### 6.1 Local Discovery (mDNS / Unix socket)

```
Agent starts → broadcasts PLL_HELLO on local subnet
Other agents → respond with PLL_ACK + capabilities
```

### 6.2 Mesh Discovery (DHT / Registry)

```
Agent joins mesh → registers with DHT under protocol+capability keys
Agent leaves   → gracefully deregisters
Agent lookup   → hash(protocol) + hash(capability) → agent list
```

## 7. Conversation Context

### 7.1 Session State

```rust
struct Session {
    id:          SessionId,
    agents:      Vec<AgentId>,
    protocol:    ProtoDecl,
    shared_schema: SymbolTable,
    history:     Vec<Envelope>,
    budget:      Budget,          // shared compute budget
}
```

### 7.2 Context Propagation

```pll
# Agent A:
session.context.merge({
    "source_doc": doc,
    "deadline": T + 30s,
})

# Agent B (receives context implicitly via protocol):
on BookIntent:
    # has access to session.context.source_doc
    enriched = merge(payload, session.context.source_doc) => BookIntent
```

## 8. Example: Two-Agent Conversation

```pll
# ── Agent A: User Facing ──
p BookingProtocol:
    msg Intent [action, params:num, confidence:num]
    msg Confirm [status, booking_ref:String?, confidence:num]

agent "user_proxy" on BookingProtocol:
    on Intent:
        emit payload  # forward to booking agent

    on Confirm:
        render "Booking {payload.status}: ref {payload.booking_ref}"

# ── Agent B: Booking Backend ──
cap book_flight [params:num] -> [ref:String, price:num]
cap.cost: 0.05
cap.requires: "flight-api-v2"

contract BookingAccuracy:
    pre:  params ~ "valid booking" > 0.7
    post: ref != "" and price > 0
    invariant: confidence > 0.6

agent "booking_backend" on BookingProtocol:
    on Intent:
        if payload.action ~ "book_flight" > 0.8:
            result = book_flight(payload.params) under BookingAccuracy
            emit Confirm { status: "confirmed", booking_ref: result.ref, confidence: result.confidence }
        else:
            emit Confirm { status: "rejected", confidence: 0.9 }
```
