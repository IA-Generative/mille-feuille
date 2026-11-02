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
                └─ search       recherches en parallèle → passages numérotés [n] → réponse en streaming
                                (rien trouvé, ou dossier non indexé → boucle d'outils)
```

- La recherche de la question brute part **pendant** le plan ; ses résultats rejoignent ceux du plan.
- Les morceaux de la réponse passent par un flux Redis (`chat:<conversation>:deltas`, `services/chat_stream.py`), lu par le SSE
  en plus de la base : pas de table, pas de migration. Le message final est en base ; le navigateur le recharge à la fin.
- `CHAT_PLAN_MODEL` (vide par défaut) permet de confier le plan à un petit modèle.
- Une décision ou une réponse sur un appel d'outil relance le chat **sans plan** : le modèle reprend là où il s'était arrêté.

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
