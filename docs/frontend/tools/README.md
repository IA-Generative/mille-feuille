# Tools des agents : captures des écrans

Épique [#343](https://github.com/IA-Generative/mille-feuille/issues/343). Plan et avancement : [tools-mcp-plan.md](../../tools-mcp-plan.md).

## Les écrans

| Écran | État | Captures |
| --- | --- | --- |
| **Mes outils** (`/outils`) : liste, recherche, pagination, ajout d'un serveur MCP, import, actualiser, supprimer | **réel**, branché sur l'API (#333, #334, #335) | `page-outils*.png`, `ajout-serveur*.png`, `import-tools.png` |
| **Outils d'un agent** : sélecteur (recherche, filtres, pagination), enregistrement, historique et restauration, outil devenu indisponible | **réel** (#336, #337) | `selecteur-*.png`, `agent-*.png` |
| **Test unitaire** d'un outil MCP : demande, choix du modèle, sortie brute | **réel** (#339) ; réservé aux tools MCP (les internes sont exécutés par le worker) | `test-outil-*.png` |
| **Menu des outils du chat** : outils de l'analyse, retrait par conversation, outil qui modifie des données signalé | **réel** (#341) | `chat-menu-*.png`, `chat-outils*.png` |
| **Autorisation d'outils qui modifient des données** : une carte à onglets sous le message, tout autoriser / refuser, une validation, état après décision | **réel** (#342) | `chat-confirmation*.png` |
| **Questions à choix de l'assistant** : onglets, choix unique ou multiple, « Autre », une validation | **réel** (#353) | `chat-question*.png` |
| **Sources de connaissances** dans « Mes outils » : liste, recherche, ajout avec vérification de la connexion, revérifier, supprimer | **réel** (#356, #360) | `page-outils.png`, `ajout-source*.png` |
| **Collections de la base de connaissances d'une analyse** : état propre à la personne (indisponible signalé, à retirer), choix par source avec recherche et pagination chez le fournisseur, aperçu et lien, historique et restauration | **réel** (#358, #360) | `collections-*.png`, `selecteur-agent.png` |
| **Sources d'une réponse** : une même carte pour une page du dossier et pour une base de connaissances externe (titre, page, passage, aperçu avec zones surlignées), numérotées sur une seule suite ([1], [2]…), en carrousel quand il y en a plusieurs ; un clic sur un numéro du texte place le carrousel sur sa carte | **réel** (#369, #360, #372) | `chat-sources-*.png`, `chat-source-unique.png` |

## Régénérer les captures

Plus aucun écran n'est simulé dans l'interface : la bascule `VITE_TOOLS_PREVIEW` est retirée. L'API est simulée **par le script de captures** (interception de `/api/**`), avec les mêmes formes que l'API réelle.

```bash
cd frontend
pnpm dev                                  # le serveur de développement
node scripts/tools-screenshots.mjs        # régénère les captures dans docs/frontend/tools/
```

Après une régénération, ne garder que les captures des écrans modifiés (les autres changent de quelques pixels sans raison).
