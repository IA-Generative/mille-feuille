# L'agent tourne dans le backend

Les agents d'analyse, le chat d'un dossier, l'assistant de l'application, les résumés, la suggestion d'analyse, les
propositions depuis une note, la génération des champs d'un document et l'indexation de la recherche sont des **travaux du
backend**, menés par `backend/app/agent/`. Il n'y a plus de worker `agent_execution`, ni de file Celery pour eux ; la
classification, l'extraction d'entités, l'extraction de texte et le rendu de documents gardent les leurs.

## Pourquoi

Un worker séparé obligeait chaque lecture ou écriture à repasser par l'API interne (`/api/internal/*`), chaque message du chat
à attendre un message Celery, et chaque réponse à n'arriver qu'une fois entière. Dans le backend, les travaux lisent la base
et appellent les services directement, et le chat peut diffuser sa réponse pendant qu'elle s'écrit. Même choix que Muffin
(`Muffin/backend/app/agent/README.md`).

## Comment

- **`runner.py`** : `agent_runner` lance un travail comme tâche asyncio (`start(nom, travail)`), borne leur nombre par pod
  (`MAX_CONCURRENT_JOBS`), les annule à l'arrêt. Un nom déjà en cours n'est pas relancé. Il est démarré par le lifespan de
  `app/main.py`.
- **`dispatch.py`** : les points d'entrée des routeurs (`dispatch_chat_response`, `dispatch_agent_execution`,
  `dispatch_document_summary`, `dispatch_index_document`…). Ils rendent la main aussitôt.
- **Redémarrage** : un redéploiement tue les travaux en cours, et rien ne les reprend tout seul. Chaque travail vivant écrit un
  battement dans Redis (`agent:job:<nom>`, 60 s) ; au démarrage, ce qui est resté « en cours » sans battement (résumés,
  suggestions, générations, analyses de notes, agents, index) passe en **échec** pour que la personne le voie et relance. Une
  reconstruction d'index, qui ne refait que la différence, est relancée. Le flux SSE du chat, lui, détecte un travail
  interrompu et ferme avec une erreur.
- **Base** : chaque travail ouvre ses propres sessions (`async_session_factory`), brèves : aucune connexion n'est gardée
  pendant un appel au modèle.

## Le chat d'un dossier

`chat/job.py`, sur le modèle de Muffin : un premier appel court **décide** (`chat/planner.py`), la recherche est du **code**
(`chat/research.py`), un second appel **écrit** la réponse en streaming (`chat/answer.py`).

```
message → plan ─┬─ direct       réponse du plan
                ├─ clarify      question à choix enregistrée, la personne répond plus tard
                ├─ assistant    renvoi vers l'assistant de l'application
                ├─ act          boucle d'outils (note, correction de l'analyse, outil externe)
                ├─ agent        un agent de l'analyse répond (son prompt, ses outils, sa synthèse)
                └─ search       recherches en parallèle → passages numérotés [n] → réponse en streaming
                                (rien trouvé, ou dossier non indexé → boucle d'outils)
```

- **Interroger un agent** (`chat/agent_reply.py`) : le plan reçoit la liste des agents de l'analyse (rang, nom, début du
  prompt) et en choisit un quand la question relève de son rôle ; une référence inconnue ramène à `search`. L'agent
  répond en direct (réponse non streamée) avec ses outils, sans ceux qui modifient des données (ils demandent l'accord
  de la personne, ce que sa boucle ne sait pas faire), et relit sa synthèse déjà produite. Ses appels d'outils portent
  son nom dans les événements du chat, et la réponse se termine par un marqueur invisible `<!--agent:Nom-->` que
  le frontend montre en étiquette « Réponse de l'agent … » (comme les marqueurs de suggestion et de propositions).
- La recherche de la question brute part **pendant** le plan ; ses résultats rejoignent ceux du plan.
- Les morceaux de la réponse passent par un flux Redis (`chat:<conversation>:deltas`, `services/chat_stream.py`), lu par le SSE
  en plus de la base : pas de table, pas de migration. Le message final est en base ; le navigateur le recharge à la fin.
- `CHAT_PLAN_MODEL` (vide par défaut) permet de confier le plan à un petit modèle.
- Une décision ou une réponse sur un appel d'outil relance le chat **sans plan** : le modèle reprend là où il s'était arrêté.

## Accès à l'analyse et appel d'agent

Tous les agents (exécution d'une analyse comme chat) sont construits au même endroit, `analysis_agents.py` :
ses outils, la synthèse déjà produite, l'accès à son analyse et, s'il a l'outil `appel_agent`, de quoi en interroger un autre.

- **Lecture de l'analyse** (`analysis_reader.py`, lecture seule) : `read_analysis` (objectif, consignes de classification et
  d'extraction, labels, entités, agents), `list_agents`, `read_agent_output` (la synthèse d'un autre agent sur ce dossier) et
  `view_analysis` (les éléments). Le lecteur est construit pour un dossier : un agent ne lit jamais celui d'un autre.
- **`appel_agent`** (`agent_call.py`) : l'outil `ask_agent` pose une question à un autre agent de l'analyse et rend sa réponse.
  L'agent interrogé travaille avec son prompt et ses outils, mais **sans** `ask_agent` (profondeur 1, pas de boucle A → B → A) ;
  `MAX_CALLS` appels par exécution. Ses sources ne remontent pas, seule sa réponse.
- **Choisir le bon agent** (`services/search/agent_index.py`, `jobs/agent_index.py`) : avec plus de 4 agents, le plan ne lit que
  les plus proches de la question, trouvés par recherche hybride (dense + BM25, RRF) dans une collection Qdrant `agents_<modèle>`
  (nom + début du prompt, filtrée par analyse). L'index suit la création d'un agent et son changement de prompt (restauration
  comprise), et se synchronise au démarrage ; seul ce qui a changé est recalculé. Sans Qdrant ni modèle d'embeddings, ou en cas
  d'erreur, le plan reçoit tous les agents. La référence d'un agent reste son rang dans l'analyse.
- **Mention** (`chat/agent_reply.mentioned`) : `@Nom` dans le message appelle l'agent à coup sûr, sans appel au plan (casse
  ignorée, nom entier : « @Agent 10 » n'est pas « @Agent 1 », une adresse de courriel n'est pas une mention).
- **Liste** : `GET /api/dossiers/{id}/agents` (`routers/dossier_agents.py`) donne les agents de l'analyse du dossier (nom, rôle en
  une ligne), avec les droits de lecture du dossier ; le menu des agents du chat s'en sert.
- Dans le chat, `appel_agent` n'est pas proposé comme outil : c'est le plan qui choisit l'agent à interroger.

## Réponses prêtes aux questions fréquentes

Une analyse définit des **questions fréquentes** (`Analyse.frequent_questions`, versionnées). À la fin de l'analyse d'un dossier,
`jobs/question_answers.py` calcule la réponse à chacune, en tâche de fond, pour que la conversation les affiche sans appel au
modèle (table `dossier_question_answers`, une ligne par dossier et par question).

- **Comme le chat répond** : recherche hybride dans le dossier, passages numérotés `[n]`, puis un seul appel qui dit si le dossier
  permet de répondre (`answerable`) et écrit la réponse. Une question **sans réponse n'est pas suggérée** (statut `sans_réponse`,
  pas un échec). Les passages cités sont gardés avec la réponse.
- **Pas de recalcul inutile** : chaque ligne garde l'empreinte de ce qu'elle a lu (pages, éléments retenus de l'analyse, synthèses des
  agents). Inchangée, la question n'est pas recalculée ; un échec (empreinte vide) est retenté au passage suivant.
- **Quand** : à la fin de `run_agents` (en même temps que le résumé du dossier), avec `full=True` : la liste de l'analyse fait foi (une
  question ajoutée apparaît, une retirée disparaît). Après une **correction** d'un élément par l'instructeur, `full=False` : seules
  les réponses existantes sont rafraîchies ; une question ajoutée à l'analyse n'apparaît sur un dossier qu'à sa relance.
- **Index** : le travail attend l'index de recherche du dossier ; sans index (Qdrant absent, échec) il ne fait rien.
- **API** : `GET /api/dossiers/{id}/question-answers` (réponses prêtes, ordre de l'analyse, état `pending`/`failed`/`ready`) et
  `POST …/regenerate` (relance, c'est ce qui reprend un échec). Un balayage au démarrage passe en échec une réponse restée en cours.

## Présentation du dossier à l'ouverture d'une conversation

Toute conversation d'un dossier s'ouvre sur la présentation du dossier (les cartes de résultats `DossierResults` sont retirées).
La présentation n'est pas un message stocké : elle est composée à la demande (`services/dossier_presentation.py`) à partir de ce que l'analyse a produit, sans appel au modèle, donc toujours à jour.

- `GET /api/dossiers/{id}/presentation` : `status` (`idle` : pas lancée ou arrêtée, rien à montrer ; `pending` : l'analyse tourne, pas
  de résumé partiel ni de suggestions ; `ready` ; `failed` avec la raison), le résumé, la classification, les entités **retenues** (une
  correction de l'instructeur fait foi, avec leur page), les synthèses des agents, les documents et les questions suggérées (réponses
  prêtes de #422). `refreshing` indique que le résumé ou les réponses se calculent encore : la page recharge jusqu'à ce que tout y soit. Un résumé
  absent ou en échec (`summary_error`) propose de le (re)générer.
- `POST /api/dossiers/{id}/conversations/{conversation_id}/question-answers/{answer_id}/ask` : la question et sa réponse prête entrent
  dans la conversation de la personne comme un échange normal (avec les sources), sans appel au modèle. 404 hors de sa conversation ou
  si la réponse n'est pas prête.
- Les vues de détail (classification par fichier et par page, explorateur des entités avec page source) sont ouvertes depuis la
  présentation par « Voir le détail ».

## Les agents d'analyse

`jobs/agents.py` attend la classification et l'extraction en lisant la base (jusqu'à 10 minutes ; ils partent ensuite avec ce
qu'il y a), s'arrête si le dossier a été arrêté, saute un agent déjà terminé, reprend la synthèse précédente quand rien n'a
changé (#119), puis lance le résumé du dossier. Le pipeline éphémère n'a plus de dernière tâche Celery : le backend lance les
agents après la chaîne (`dispatch_dossier_pipeline`).

## L'indexation

Le backend lance lui-même le résumé et l'indexation d'un document quand le worker `document_process` lui dit que l'extraction
du texte est « terminée » (route interne `extraction-status`). Voir [recherche-dossier.md](recherche-dossier.md).

## Les routes internes

Les routes `/api/internal/*` que seul l'ancien worker appelait (conversation, résumés, suggestions, notes, propositions,
brouillons, outils, base de connaissances, index, assistant) n'existent plus : l'agent appelle les services directement. Restent
celles des workers de classification, d'extraction et d'extraction de texte (`app/routers/internal.py`).
