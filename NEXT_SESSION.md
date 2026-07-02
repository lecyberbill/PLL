# Session suivante

## État actuel

- [x] Rust compiler + VM intégrés : `pll run`, `pll run --bc`
- [x] 19 tests unitaires (bytecode compiler + VM)
- [x] Récursion corrigée (parse_block contextuel)
- [x] Appels croisés fonctionnent
- [x] ForEach, Index implémentés
- [x] Git endpoints (init, status, commit, push, remote, clone)
- [x] Agent ReAct avec 21 outils
- [x] Clarification humain-agent
- [x] Arbre VFS, rename, delete
- [x] Barre d'état git
- [x] Mode disque et mode DB
- [x] PLL exec via Rust CLI
- [x] Stack traces VM
- [x] Zéro warnings de compilation

## Prochaines étapes

### Priorité haute
1. **Streaming SSE** — voir les étapes de l'agent en temps réel
2. **Parallélisation des outils** — `asyncio.gather` pour les outils indépendants
3. **Cache LLM sémantique** — éviter les appels redondants

### Priorité moyenne
4. **CLI refactor** — remplacer `main.rs` monolithique par `clap`
5. **Tests while + récursion** — tests de boucle et fibonacci
6. **Améliorer les messages d'erreur** — stack traces complètes avec numéros de ligne PLL

### Priorité basse
7. **Remplacer les stubs CLI** — `selfhost-compile`, `multi-run`, `install`
8. **Restaurer `pll-wasm`** — rebuild WASM pour le navigateur
9. **Web search fiable** — remplacer DuckDuckGo par une API Google Custom Search

## Bugs connus
- Tests doivent être exécutés en séquentiel (`--test-threads=1`) à cause de `last_rendered` global
- `test_record` flaky (test isolation)
