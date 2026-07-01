# PLL v2 — Reference for LLM Developer Agents

PLL (Probabilistic LLM Language) v2 est un langage agent-native, auto-hébergé, qui se compile en Rust natif ou s'exécute sur sa VM.

## 1. Syntaxe

### 1.1 Commentaires
```pll
# Ceci est un commentaire ligne
```

### 1.2 Déclarations de types
```pll
t Token [kind: String, value: String, line: num, col: num]
t Point [x: num, y: num]
```
Types primitifs : `String`, `num` (f64), `bool`, `event`. Un type déclaré devient utilisable comme type.

### 1.3 Variables
```pll
v nom != valeur          # Déclaration + initialisation
v nom != 42
v nom != "hello"
v nom != [1, 2, 3]       # Liste
v nom != Point {x: 5, y: 10}  # Record
nom = nouvelle_valeur     # Réaffectation
```

### 1.4 Expressions arithmétiques et logiques
```pll
x + y   x - y   x * y   x / y        # Arithmétique
x > y   x < y   x >= y  x <= y       # Comparaisons
x == y  x != y                        # Égalité
cond and cond   cond or cond          # Logique
not cond                              # Négation
```

### 1.5 Contrôle de flux
```pll
if condition:
    corps
else:
    corps_alternatif

while condition:
    corps

return valeur
```

### 1.6 Fonctions
```pll
fn double(n: num) -> num:
    return n * 2

fn greet(name: String) -> String:
    return str_concat("Hello, ", name)

# Paramètres par défaut : num
fn add(a, b):
    return a + b
```

### 1.7 Listes
```pll
v items != [1, 2, 3]
list_length(items)        # → 3
list_get(items, 1)        # → 2
items = list_push(items, 4)  # → [1, 2, 3, 4]
```

### 1.8 Chaînes
```pll
str_concat(a, b)          # Concaténation
str_length(s)             # Longueur
str_slice(s, start, end)  # Sous-chaîne
str_char_at(s, i)         # Caractère à l'index i
str_to_num(s)             # → f64
str_from_num(n)           # → String
str_starts_with(s, p)     # → bool
str_is_digit(s)           # → bool
str_is_letter(s)          # → bool
str_to_upper(s)           # → String
```

### 1.9 Persistance (DB)
```pll
db_set("key", valeur)     # Stocke
db_read("key")            # Récupère ("" si absent)
```

### 1.10 Entrées / Sorties
```pll
emit valeur               # Émet un événement
render valeur             # Affiche une réponse
read_file(chemin)         # Lit un fichier → String
write_file(chemin, contenu)  # Écrit un fichier
args()                    # Arguments CLI → List
input(nom)                # Entrée HTTP/input
```

### 1.11 Communication agent (wire)
```pll
send(payload)             # Envoie un message (auto-wrapping WireMessage)
recv()                    # Reçoit un message → String
```

### 1.12 Déclarations d'Agents (VM Handoff)
```pll
# Déclarer un agent écoutant sur un protocole et réagissant à un type de message
agent "bot" on Proto:
    on Ping:
        render "PONG!"
```
Les agents réagissent à des événements via `emit Msg {}`. Le runtime injecte le message reçu dans la variable locale `payload`.

## 2. Exemple complet : Agent calculateur
```pll
fn factorial(n: num) -> num:
    if n <= 1:
        return 1
    return n * factorial(n - 1)

v result != factorial(5)
render str_from_num(result)
# Output: 120
```

## 3. Exemple : Tokenizer + Parseur (en PLL)
```pll
t Token [kind: String, value: String, line: num, col: num]

fn tokenize(input: String) -> List:
    v tokens != []
    v pos != 0
    while pos < str_length(input):
        v ch != str_char_at(input, pos)
        if ch == " ":
            pos = pos + 1
        if ch == "+":
            v tok != Token {kind: "OP", value: "+", line: 1, col: pos}
            tokens = list_push(tokens, tok)
            pos = pos + 1
        # ... autres caractères
    return tokens
```

## 4. Exécution

| Commande | Description |
|---|---|
| `pll run fichier.pll` | Parse + type-check + exécute sur la VM |
| `pll check fichier.pll` | Lex → Parse → Type-check seulement |
| `pll repl` | Lance la console interactive avec support d'agents (méta-commandes : `.help`, `.agents`, `.db`, `.chat`) |
| `pll compile fichier.pll` | Génère un projet Rust + `cargo build` |
| `pll bootstrap fichier.pll` | Génère du Rust autonome (pll_runtime) |
| `pll multi-run a.pll b.pll [a_recv.pll]` | Compile deux agents + les fait communiquer |
| `pll tokens fichier.pll` | Affiche le token stream |
| `pll ast fichier.pll` | Affiche l'AST |

## 5. Architecture agent

```
Agent A (PLL)  ──send──→  Agent B (PLL)
  send("hello")           recv() → "hello"
                          send("ack") 
  recv() → "ack"    ←──
```

- `send`/`recv` utilisent `WireMessage` avec auto-wrapping.
- Routage par capacité via `CapabilityRouter`.
- `multi-run` : compilation Rust + transport bidirectionnel.

## 6. Compilation autonome (self-hosting)

```
compiler_v4.pll (580 lignes)
   ↓ pll bootstrap (rapide, Rust -> Rust)
compiler_v4.boot.rs (34KB de Rust)
   ↓ cargo build
pll_selfhosted.exe (125KB)
   ↓ exécute du PLL
Résultat
```

Le compilateur PLL peut se compiler lui-même : le langage est auto-hébergé.
