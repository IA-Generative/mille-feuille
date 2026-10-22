# Tools des agents : captures et écrans simulés

Épique [#343](https://github.com/IA-Generative/mille-feuille/issues/343). Plan et avancement : [tools-mcp-plan.md](../../tools-mcp-plan.md).

## Ce qui est réel, ce qui est simulé

| Écran | État | Captures |
| --- | --- | --- |
| **Mes outils** (`/outils`) : liste, recherche, pagination, ajout d'un serveur MCP, import, actualiser, supprimer | **réel**, branché sur l'API (#333, #334, #335) | `page-outils*.png`, `ajout-serveur*.png`, `import-tools.png` |
| **Outils d'un agent** : sélecteur (recherche, filtres, pagination), enregistrement, historique et restauration, outil devenu indisponible | **réel** (#336, #337) | `selecteur-*.png`, `agent-*.png` |
| Bouton « Tester » d'un outil | simulé (#339) | `test-outil-*.png` |
| Menu des outils du chat, confirmation avant un outil qui modifie des données | simulé (#341, #342) | `chat-*.png` |
| Collections de la base de connaissances d'une analyse | simulé, épique « base de connaissances » à venir | `collections-*.png` |

## Les écrans simulés sont masqués par défaut

Une seule bascule, `VITE_TOOLS_PREVIEW` (`frontend/src/utils/featureFlags.ts`), les affiche. Sans elle :

- le chat est inchangé ;
- il n'y a ni bouton « Tester » ni bloc de collections.

```bash
cd frontend
VITE_TOOLS_PREVIEW=true pnpm dev          # afficher les écrans simulés
node scripts/tools-screenshots.mjs        # régénérer les captures (l'API est simulée par le script)

pnpm dev                                  # sans la variable
node scripts/tools-screenshots.mjs --verifier-masque   # vérifie que rien de simulé n'apparaît
```

Quand une issue de la liste rend son écran réel, on retire sa condition `TOOLS_PREVIEW`.
