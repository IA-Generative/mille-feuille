# Tools des agents : captures et écrans simulés

Épique [#343](https://github.com/IA-Generative/mille-feuille/issues/343). Plan et avancement : [tools-mcp-plan.md](../../tools-mcp-plan.md).

## Ce qui est réel, ce qui est simulé

| Écran | État | Captures |
| --- | --- | --- |
| **Mes outils** (`/outils`) : liste, recherche, pagination, ajout d'un serveur MCP, import, actualiser, supprimer | **réel**, branché sur l'API (#333, #334, #335) | `page-outils*.png`, `ajout-serveur*.png`, `import-tools.png` |
| **Outils d'un agent** : sélecteur (recherche, filtres, pagination), enregistrement, historique et restauration, outil devenu indisponible | **réel** (#336, #337) | `selecteur-*.png`, `agent-*.png` |
| **Test unitaire** d'un outil MCP : demande, choix du modèle, sortie brute | **réel** (#339) ; réservé aux tools MCP (les internes sont exécutés par le worker) | `test-outil-*.png` |
| **Menu des outils du chat** : outils de l'analyse, retrait par conversation, outil qui modifie des données signalé | **réel** (#341) | `chat-menu-*.png`, `chat-outils*.png` |
| **Autorisation d'outils qui modifient des données** : une carte à onglets sous le message, tout autoriser / refuser, une validation, état après décision | **réel** (#342) | `chat-confirmation*.png` |
| **Questions à choix de l'assistant** : onglets, choix unique ou multiple, « Autre », une validation | **réel** (#353) | `chat-question*.png` |
| Collections de la base de connaissances d'une analyse | simulé, épique « base de connaissances » à venir | `collections-*.png` |

## Les écrans simulés sont masqués par défaut

Une seule bascule, `VITE_TOOLS_PREVIEW` (`frontend/src/utils/featureFlags.ts`), les affiche. Sans elle :

- il n'y a pas de bloc de collections.

```bash
cd frontend
VITE_TOOLS_PREVIEW=true pnpm dev          # afficher les écrans simulés
node scripts/tools-screenshots.mjs        # régénérer les captures (l'API est simulée par le script)

pnpm dev                                  # sans la variable
node scripts/tools-screenshots.mjs --verifier-masque   # vérifie que rien de simulé n'apparaît
```

Quand une issue de la liste rend son écran réel, on retire sa condition `TOOLS_PREVIEW`.
