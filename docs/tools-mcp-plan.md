# Plan d'implémentation : tools des agents (internes + serveurs MCP)

Statut : phase 1 (UI) faite ; phases 2 et 3 (registre des serveurs MCP, backend + frontend) faites ; la suite est détaillée dans « Avancement ».
Branche à créer depuis `main` : `feat/tools-mcp`.

Convention de suivi : cocher au fur et à mesure de l'implémentation, dans cette branche.
Ordre retenu : **UI sur mocks d'abord**, puis backend, puis worker (design épuré, composants séparés).

## Avancement

| Phase | État |
| --- | --- |
| 1. UI sur mocks | **fait** (captures dans [frontend/tools/](frontend/tools/)) |
| 2. Modèle de données | **fait** pour le registre et pour les outils d'un agent (identifiants dans la colonne existante, aucune migration) ; collections par analyse (#358) **faites** ; sources de connaissances (#356) et outil de recherche (#359) **faits** |
| 3. Registre, API et import MCP | **fait** (CRUD, `discover`, `refresh`, garde SSRF, visibilité) ; frontend branché sur l'API |
| 3 bis. Outils d'un agent (#336, #337) | **fait** : sélection enregistrée, contrôle des droits, historique et restauration, outil indisponible signalé |
| 4. Identité et appel (#334) | **fait** : échange de jeton Keycloak à partir de la session, vérifié contre un vrai Keycloak ; compte de service et jeton statique prévus, grisés |
| 5. Proxy d'appel (#338) et test unitaire (#339) | **fait** : route interne, quotas, journal, sortie bornée ; test d'un tool MCP avec un modèle au choix (consommation comptée) ; tester un outil interne viendra avec le worker (#340) |
| 6. Worker (#340) | **fait** : calculatrice, calcul de dates et tools MCP donnés aux agents (au nom de la personne qui lance l'analyse), sortie externe balisée comme non fiable ; le socle de lecture du dossier reste toujours donné ; détail dans [backend/outils-des-agents.md](backend/outils-des-agents.md) |
| 7. Chat | menu des outils (#341) **fait** : outils de l'analyse, retrait par conversation, outils MCP appelés au nom de l'auteur ; confirmation avant un outil qui modifie des données (#342) **faite** : demande enregistrée avec le message, décision de tout le lot par la personne quand elle veut, qui relance le chat |
| 8. Préparation de la suite | à faire |

### Ce qui existe côté backend

Chaque module a un seul rôle et ses tests :

| Module | Rôle |
| --- | --- |
| `config/tools.py` | domaines autorisés, mode non sécurisé de développement, délai de découverte |
| `models/tool.py` | `ToolServer` et `Tool` (migration `c0d1e2f3a4b5`, schéma de la base régénéré) |
| `services/tools/internal_catalog.py` | les 10 tools internes, dont les 6 de l'ancienne énumération `AgentTool` avec **le même identifiant** (aucun agent existant à migrer) |
| `services/tools/url_guard.py` | garde d'URL anti-SSRF : forme, domaines autorisés, adresses publiques seulement |
| `services/tools/credentials.py` | les en-têtes d'authentification selon le mode ; un seul point d'extension pour le token exchange, le jeton statique et le compte de service |
| `services/tools/mcp_discovery.py` | client MCP réel (`tools/list`, pagination), isolé derrière `ToolLister` |
| `services/tools/discovery.py` | enchaîne garde d'URL, identifiants et découverte |
| `services/tools/visibility.py` | règle de visibilité unique, en Python et en SQL |
| `repositories/tool_server_repository.py` | création, liste visible paginée avec recherche, actualisation, suppression |
| `schemas/tool.py`, `routers/tool_servers.py`, `routers/tools.py` | l'API |

Routes : `GET /api/tools/internal`, `POST /api/tool-servers/discover`, `GET|POST /api/tool-servers`, `GET|DELETE /api/tool-servers/{id}`, `POST /api/tool-servers/{id}/refresh`.

Décisions de l'implémentation :
- la liste des tools est **relue côté serveur** à la création : on ne fait pas confiance à celle du client ;
- tous les tools découverts sont enregistrés, seuls ceux choisis sont `enabled` ; à l'actualisation, **les nouveaux arrivent non autorisés** ;
- `side_effect` vient de l'annotation MCP `readOnlyHint` ; sans elle, on suppose que le tool modifie des données ;
- un serveur que la personne ne voit pas répond **404** ; visible mais pas à elle, **403** ; un administrateur voit tout et peut supprimer ;
- `static_token` est refusé à la validation (422) ; `token_exchange` répond 422 `token_exchange_indisponible` jusqu'à la phase 4 ;
- limite connue de la garde d'URL : le DNS est vérifié avant la connexion, pas pendant (voir `url_guard.py`).

### Écrans simulés

Les écrans qui ne sont pas encore reliés à l'API sont **masqués par défaut** par la bascule `VITE_TOOLS_PREVIEW` ; voir [frontend/tools/README.md](frontend/tools/README.md). Chaque issue qui rend un écran réel retire sa condition.

## Décisions d'interface prises depuis la conception

- **Sélection des tools d'un agent** : un résumé en pastilles et un bouton qui ouvre une modale (recherche, filtres par source, pagination, « Tout sélectionner »). Les outils internes sont actifs par défaut.
- **« Mes outils »** (menu utilisateur, `/outils`) : recherche et pagination par section, bouton « Tester » par outil.
- **Chat** : le LLM choisit parmi les outils activés ; un menu dans la zone d'envoi, comme ChatGPT, permet d'en **retirer** pour la conversation (jamais d'en ajouter hors de ce que l'analyse autorise). Confirmation avant un tool qui modifie des données.
- **Test unitaire** : une demande en langage naturel, le modèle n'a que cet outil, on n'affiche que la **sortie brute** (l'appel du modèle est repliable). Un outil qui modifie des données demande une confirmation explicite.
- **Base de connaissances** : les collections se choisissent **par analyse**, avec historique et restauration. Le fournisseur de collections respecte le contrat [base-de-connaissances-api.yaml](backend/base-de-connaissances-api.yaml) (lister, retrouver par identifiant, chercher dans un ensemble de collections ; suggérer et lire un document sont facultatifs).

## À faire ensuite (backend)

- **Phase 4** : index `user_id → session_id` dans Redis, `get_access_token_for_user`, échange de jeton Keycloak avec un champ `audience` sur le serveur (et dans le formulaire), cache court, verrou contre la rotation du refresh token.
- **Phase 5** : route interne `POST /api/internal/tools/{id}/call` (jeton du worker + `X-Acting-User`), timeouts, quotas, journal des appels ; le test unitaire réutilise ce proxy avec un seul tool.
- **Liaison agent ↔ tools** : identifiants de tools dans les agents (liste versionnée), avec conversion de l'ancienne énumération.
- **Collections par analyse** : table versionnée des collections autorisées, client du contrat OpenAPI, route de lecture pour le worker.
- **Chat** : liste des tools exclus par conversation.

## Objectif

N'importe qui peut ajouter un serveur MCP. Les agents (et le chat, selon l'analyse) peuvent utiliser ou non chaque tool, internes comme MCP, dans la limite des droits de la personne.

## Constats sur l'existant

- Les tools internes (recherche BM25, dates, notes, propositions d'analyse) sont codés en dur dans `worker/agent_execution/app/tools.py` (`AgentTools`, `tool_definitions()`, `dispatch_tool()`), partagés par `agent_graph.py` et `chat_graph.py`.
- Le worker n'a pas accès à la base ni à Keycloak : il parle au backend via `/api/internal/*` (`X-App-Token`, et `X-Acting-User` pour agir au nom d'une personne, voir [acces-de-l-agent-assistant.md](backend/acces-de-l-agent-assistant.md)).
- Le backend garde déjà une session Redis par connexion (`access_token`, `refresh_token`), rafraîchie à la demande (`backend/app/core/security/session.py`).
- Les agents ont déjà un champ `tools: AgentTool[]` versionné (historique + restauration).
- Le serveur `/mcp/helper` est un serveur que nous exposons. Ici nous sommes **client** d'autres serveurs MCP.

## Décisions

1. **Un registre unique** : un tool interne et un tool MCP sont la même chose pour l'agent (`kind = internal | mcp`). Les internes sont seedés en code, non modifiables.
2. **Granularité** : on enregistre un **serveur MCP** (une URL), on importe sa liste de tools (`tools/list`), puis on choisit les tools autorisés **par agent**.
3. **Aucun token ne passe par le worker.** Le worker demande au backend « appelle ce tool avec ces arguments » et ne reçoit que le résultat. Le backend porte l'identité.
4. **Trois modes d'auth dès le modèle, un seul actif en V1 :**

   | `auth_mode` | V1 | Identité | Secret stocké |
   | --- | --- | --- | --- |
   | `none` | actif | aucune | non |
   | `token_exchange` | actif | la personne connectée (session Keycloak du backend) | non |
   | `static_token` | **grisé** | jeton fourni à l'ajout du MCP | oui, chiffré |

5. **Token exchange (RFC 8693)** fait par le backend à partir de la session de la personne (refresh paresseux déjà en place). Pas de refresh dédié pendant la tâche.
6. **Exécutions sans personne** (créneaux de traitement) : il faudra un compte de service. Pas en V1, mais on **prépare** le modèle, l'interface et l'UI : `identity_source = user | service_account` (seul `user` actif), erreur typée `identity_unavailable` renvoyée au LLM en clair.
7. **Visibilité d'un serveur** : privé par défaut, partageable ensuite (même logique que le partage des analyses).
8. **Versionnage** : la liste de tools d'un agent reste versionnée avec historique et restauration (règle « tout est versionné »).
9. **Chat** : les tools proposés = union des tools des agents de l'analyse, filtrée par les droits de la personne qui discute. Un tool à effet de bord demande une confirmation avant appel.
10. Les tools exposés au LLM sont préfixés par le serveur (`serveur__tool`) pour éviter les collisions.

## Sécurité

- **SSRF** : l'URL d'un MCP ajouté par un utilisateur est validée (refus des IP privées, liens locaux, metadata cloud) et peut être restreinte par une allowlist de domaines configurée par l'administrateur.
- **Contenu non fiable** : les résultats d'un MCP sont marqués comme tels dans le prompt (risque d'injection) et bornés en taille.
- **Garde-fous d'exécution** : timeout par appel, nombre maximal d'appels de tools par run, quotas.
- **Droits** : à l'exécution, on revérifie les droits de la personne qui lance le run, pas seulement ceux de l'éditeur de l'agent.
- **Journal** : chaque appel est tracé (auteur, serveur, tool, durée, issue) et rattaché à la consommation.
- **Secrets** : `credentials` chiffré au repos. Le refresh token en session Redis est aujourd'hui en clair : à noter comme risque, chiffrement à évaluer.
- Un MCP en `none` est public : l'UI l'indique clairement.

## Phase 0 — Cadrage

- [ ] Réécrire l'issue (texte ci-dessous) et la lier à ce plan.
- [ ] Créer la branche `feat/tools-mcp` depuis `main`.

## Phase 1 — UI sur mocks (frontend)

Données mockées, composants séparés, style sobre.

- [ ] Types TypeScript : `Tool`, `ToolServer`, `ToolAuthMode`, `ToolIdentitySource`, état d'utilisabilité d'un tool.
- [ ] Page « Outils » : liste (internes / MCP), badge du mode d'auth, indication « sans authentification » pour `none`.
- [ ] Formulaire d'ajout d'un serveur MCP : URL, nom, mode d'auth (`none`, `token_exchange`, `static_token` **grisé** avec infobulle « bientôt disponible » et champ désactivé), visibilité.
- [ ] Écran d'import : liste des tools découverts, choix de ceux à activer.
- [ ] Sélecteur de tools dans l'éditeur d'agent (avec historique et restauration, comme les autres champs).
- [ ] États d'indisponibilité d'un tool (« nécessite une session », « indisponible hors session »).
- [ ] Champ « exécuter avec un compte de service » **grisé**, dans le créneau de traitement.
- [x] Chat : puces des tools disponibles selon l'analyse, confirmation avant un tool à effet de bord.
- [ ] Tests des composants.

## Phase 2 — Modèle de données (backend)

- [ ] Modèles `ToolServer` (nom, `url`, `auth_mode`, `credentials` chiffré nullable, `visibility`, `enabled`, `created_by`) et `Tool` (`server_id` nullable pour les internes, `kind`, `name`, `description`, `input_schema` JSONB, `enabled`).
- [ ] Liaison agent ↔ tools (identifiants de tools dans `tools` de l'agent, avec versionnage existant).
- [ ] Enregistrement dans `models/__init__.py`, migration (vérifier le `downgrade` : types Postgres à dropper).
- [ ] Régénérer `docs/backend/data-model.png` avec `scripts/generate_data_model.py`.
- [ ] Seed des tools internes avec identifiants stables.

## Phase 3 — Repository, API et import MCP

- [ ] Repository et routes CRUD des serveurs (droits : propriétaire, partage).
- [ ] `static_token` refusé en 422 « pas encore disponible ».
- [ ] Garde SSRF et allowlist.
- [ ] Import `tools/list` d'un serveur MCP, avec rafraîchissement à la demande.
- [ ] Remplacer les mocks du frontend par l'API.
- [ ] Tests (droits, SSRF, import).

## Phase 4 — Identité et appel

- [ ] Index `user_id → session_id` dans Redis, écrit à la création de session.
- [ ] `get_access_token_for_user(user_id)` : session la plus récente, refresh si besoin, verrou court contre la rotation concurrente du refresh token.
- [ ] Interface `ToolCredentialProvider.headers_for(server, acting_user)` : `NoAuth` et `TokenExchange` ; `StaticToken` et `ServiceAccount` en stubs qui lèvent une erreur explicite.
- [ ] Appel de token exchange Keycloak, avec cache court par `(user, audience)`.
- [ ] Erreur typée `identity_unavailable` (aucune session, créneau sans personne) avec message clair pour le LLM.
- [ ] Configuration Keycloak documentée (Standard Token Exchange sur le client backend, audience par MCP).

## Phase 5 — Proxy d'appel (backend)

- [ ] Route interne `POST /api/internal/tools/{id}/call` (`X-App-Token` + `X-Acting-User`), contrôle des droits sur le serveur et l'agent.
- [ ] Timeout, limites de taille, quotas, nombre d'appels par run.
- [ ] Journal des appels et rattachement à la consommation.
- [ ] Tests (droits, session absente, serveur indisponible).

## Phase 6 — Worker

- [ ] `AgentTools` fusionne tools internes et MCP, `tool_definitions()` dynamique selon l'agent.
- [ ] `dispatch_tool()` route les tools MCP vers la route interne via `api_client` (aucun token côté worker).
- [ ] Marquage du contenu non fiable dans le prompt.
- [ ] Tests dans `worker/agent_execution/tests/`.

## Phase 7 — Chat

- [ ] Calcul des tools proposés selon l'analyse et les droits de la personne.
- [ ] Confirmation avant tool à effet de bord.
- [ ] Affichage des appels dans `groupToolEvents.ts`.

## Phase 8 — Préparation de la suite (sans activer)

- [ ] Documenter le point d'extension du compte de service pour les créneaux.
- [ ] Documenter l'activation de `static_token` (stockage chiffré, rotation).

## Hors périmètre V1

- Token statique et compte de service (préparés, grisés).
- Marketplace ou catalogue public de serveurs MCP.

## Brouillon de l'issue

**Titre :** Tools des agents : tools internes et serveurs MCP ajoutables par les utilisateurs

**Description :** Permettre à n'importe qui d'ajouter un serveur MCP et à chaque agent d'avoir accès, ou non, à chaque tool (internes comme MCP). Dans le chat, proposer les tools selon ce à quoi l'analyse a accès.

**Périmètre V1 :**
- Registre unique de tools (internes seedés + serveurs MCP importés).
- Auth `none` et `token_exchange` (identité de la personne, portée par le backend ; aucun token ne passe par le worker).
- `static_token` et compte de service préparés dans le modèle, l'API et l'UI, mais grisés.
- Sélection des tools par agent, versionnée.
- Garde SSRF, journal des appels, quotas.

**Hors périmètre :** token statique, compte de service pour les créneaux de traitement.

Plan détaillé : `docs/tools-mcp-plan.md`.
