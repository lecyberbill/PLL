# PLL Agentic IDE — Roadmap

## 🟢 Fait
- [x] Compilateur PLL + VM WASM
- [x] Serveur FastAPI (30+ endpoints)
- [x] Agents parlent PLL entre eux (ReAct, Coordinator)
- [x] Mécanisme de clarification Humain ↔ Agent
- [x] Détection intelligente de langage (30+ langages)
- [x] GCA lifecycle (init → checkpoint → handoff → vault)
- [x] Playground Monaco Editor

## 🔵 Prioritaire (prochaine session)

### 1. Exécution PLL dans la boucle agent
Le compilateur WASM existe mais les agents ne peuvent pas l'appeler. Un agent devrait pouvoir écrire du PLL → le compiler en bytecode → l'exécuter → utiliser le résultat.
```
Agent: "calcule le nombre de jours entre date1 et date2"
→ génère du PLL avec les builtins de date
→ compile avec bcvm.pll
→ récupère le résultat
→ continue
```

### 2. Persistance multi-tour de la clarification
Actuellement un seul cycle Q&A. Il faudrait :
- Historique complet conservé dans le vault
- L'agent peut revenir sur une décision
- `current_state` étendu pour stocker l'arbre de décision

### 3. Palette d'outils PLL au lieu de JSON
Les outils actuels (`read_file`, `write_file`, etc.) sont appelés en JSON. Les transformer en **capabilités PLL** :
```pll
v content != read_file("app.py")
v files != glob("*.py")
v result != grep("def ", "*.py")
```
Le ReAct parse le PLL natif au lieu du JSON.

## 🟡 Court terme

### 4. Routing par capabilité
Le coordinateur devrait router les sous-tâches par capacité plutôt que par nom d'agent :
```pll
p StorageCap:
    cap save_todo [data: Todo] -> [id: num]
    cap list_todos [] -> [items: Todo[]]
```
Le planner détecte les besoins et trouve l'agent capable.

### 5. Vault sémantique (RAG amélioré)
Le RAG actuel est keyword-based. Le remplacer par embeddings (sentence-transformers) :
- À chaque checkpoint, le résumé est vectorisé
- La recherche utilise la similarité cosinus
- Résultats bien meilleurs, surtout pour du PLL

### 6. Interface de collaboration
Le playground a besoin de :
- Chat threadé (plusieurs tours, édition des messages)
- Diff view pour les modifications de code
- Bouton "Appliquer" / "Rejeter" les suggestions agent
- État de l'agent visible en temps réel

## 🟠 Moyen terme

### 7. Compilation bytecode pour agents déterministes
Quand un agent a besoin de faire un calcul ou une transformation déterministe :
1. Il génère du PLL
2. Le PLL est compilé en bytecode via `compile_bc.pll`
3. Le bytecode est exécuté par la VM
4. Le résultat est garanti déterministe (pas d'LLM)

### 8. Agents multi-projets
Un agent peut référencer du code d'un autre projet :
```pll
v auth_module != import_project("auth-service", "auth.py")
v user != auth_module.login("token")
```

### 9. Auto-amélioration des prompts
Le système analyse ses générations réussies/échouées et ajuste ses prompts :
- Si le clarify renvoie toujours OK → prompt trop permissif
- Si le code généré a des erreurs de syntaxe → ajouter few-shot
- Si l'agent boucle sans final_answer → ajuster le system prompt

## 🔴 Long terme

### 10. Écosystème de packages PLL
Le dossier `.pll_packages/gca/` est un début. Il faudrait :
- Un registre de packages
- `pll install <package>` dans le playground
- Agents capables de découvrir et d'utiliser des packages
- Packages agentiques : modules PLL contenant des capabilités

### 11. Agents spécialisés interchangeables
Au lieu d'un AgentBrain monolithique :
- Agents spécialisés : `CodeGenAgent`, `DebugAgent`, `ReviewAgent`, `PlannerAgent`
- Chaque agent est un fichier PLL avec ses capabilités déclarées
- Le coordinateur assemble l'équipe selon la tâche

### 12. Mode offline/local complet
- Tous les modèles en local (via LM Studio / Ollama)
- PLL VM en Rust natif (pas WASM)
- Base de connaissances locale vectorisée
- Zéro dépendance cloud
