# API Ephemeral / On-Demand

## Contexte et objectif

On veut exposer une couche d'API permettant à un utilisateur (dev ou compte de service) de :

1. Récupérer la définition complète d'une analyse (agents, classification, entités).
2. Lancer le pipeline complet d'analyse (classification + extraction d'entités + agents) à la demande, sur un ensemble de documents, sans passer par le flux dossier standard de la plateforme.
3. Choisir, à chaque étape, si le résultat doit être conservé indéfiniment (`persist=true`, comportement actuel de la plateforme) ou être temporaire (`persist=false`, purgé automatiquement après un TTL).

La plateforme existante n'est pas modifiée : `Dossier`, `Analyse`, `ExecutionStep`, le pipeline Celery (`classify_dossier`, `extract_dossier_entities`, `run_agents`) et le stockage S3 restent tels quels. On ajoute une couche parallèle qui les réutilise.

## Principe du TTL

Le TTL ne démarre **pas** à la création de la ressource mais **à la fin de l'analyse** (`ended_at`). Tant que le run est en cours, `expires_at` reste `NULL` : on ne veut jamais purger un run en cours de traitement, même s'il reste en file d'attente longtemps.

```
expires_at = ended_at + ttl_hours   (posé au moment où le statut passe à un état terminal)
```

Le TTL est configurable par requête (`?ttl_hours=`) :

- **Défaut** : 24h si non fourni.
- **Maximum autorisé** : 2 ans (17 520h). Une valeur supérieure est rejetée (400) — au-delà, autant utiliser `persist=true`.

Pas de limite de taille ni de nombre de documents spécifique aux runs éphémères : les limites standard de la plateforme (upload, taille de fichier) s'appliquent telles quelles, sans restriction additionnelle.

## Fin de vie d'un run : on garde le résultat, on supprime le reste

Quand un run `persist=false` atteint un état terminal (`terminé`, `échec` ou `arrêté`, y compris après un `stop` manuel), le backend le **finalise** (`app/services/ephemeral_run_service.py`) :

1. le résultat complet du run (ce que renvoie `GET /api/ephemeral/runs/{id}` : statut, étapes, sorties des agents, pages, prédictions, résumés) est copié dans la table `ephemeral_results`, avec `expires_at = ended_at + ttl_hours` ;
2. le `Dossier` est supprimé : documents, fichiers S3, captures de page, étapes d'exécution, prédictions (cascade existante) ;
3. l'analyse éphémère `persist=false` liée est supprimée, **sauf** si un autre dossier la référence encore (le dernier run terminé la supprime). Une analyse `persist=true` ou une analyse classique n'est jamais supprimée.

Le client ne voit pas de différence : `GET /api/ephemeral/runs/{id}` renvoie le même schéma, servi depuis l'instantané (avec `analyse_id = null` si l'analyse a été supprimée, et des `s3_key` qui ne pointent plus vers rien). À `expires_at`, la purge supprime le résultat, et `GET` répond alors 404.

Un run `persist=true` n'est pas finalisé : dossier, fichiers et résultats restent tels quels, sans expiration.

Conséquence : une analyse `persist=false` n'est plus réutilisable une fois ses runs terminés. Pour enchaîner plusieurs runs sur la même analyse, la créer avec `persist=true`.

Limite connue : les résumés de documents sont générés en asynchrone ; si un résumé n'est pas terminé quand le pipeline finit, l'instantané le contient dans l'état où il était (`summary_status`), et le worker qui déposerait le résumé ensuite reçoit un 404.

## Modèle de données

Pas de duplication : `Analyse`, `Dossier`, `ExecutionStep`, `DossierDocument` et les résultats restent les tables existantes, utilisées telles quelles par le pipeline actuel. On ajoute seulement deux **tables d'association 1-1**, qui portent la métadonnée « ce record est éphémère » sans toucher au schéma ni au code métier existants.

### `analyse_ephemere`

Association avec `Analyse`.

| Champ | Type | Notes |
|---|---|---|
| `analyse_id` | uuid, PK + FK → `Analyse.id` | même id que l'analyse existante, renvoyé au client (`analyse_id`) |
| `persist` | bool, défaut `false` | si `true`, jamais purgée |
| `created_at` | timestamp | |
| `last_run_ended_at` | timestamp, nullable | mis à jour à chaque fin de run qui référence cette analyse |
| `expires_at` | timestamp, nullable | `NULL` si `persist=true` ou si jamais utilisée avant TTL ; sinon `last_run_ended_at + ttl_hours` |

Une `Analyse` **sans** ligne dans `analyse_ephemere` = analyse classique de la plateforme, comportement inchangé.

### `ephemeral_results`

Résultat conservé d'un run `persist=false` terminé (voir « Fin de vie d'un run »).

| Champ | Type | Notes |
|---|---|---|
| `run_id` | uuid, PK | même id que le run renvoyé au client ; pas de FK (le dossier n'existe plus) |
| `created_by` | str | créateur, pour le scoping de visibilité |
| `payload` | JSONB | instantané de `EphemeralRunOut` |
| `expires_at` | timestamp, indexé | `ended_at + ttl_hours` |
| `created_at` | timestamp | |

### `dossier_ephemere`

Association avec `Dossier` (le run).

| Champ | Type | Notes |
|---|---|---|
| `dossier_id` | uuid, PK + FK → `Dossier.id` | même id que le dossier existant, renvoyé au client (`run_id`) |
| `analyse_ephemere_id` | FK → `analyse_ephemere.analyse_id`, nullable | rempli seulement si l'analyse liée est elle-même éphémère |
| `persist` | bool, défaut `false` | indépendant du `persist` de l'analyse liée |
| `ttl_hours` | int, nullable | valeur effective utilisée pour ce run (`?ttl_hours=` ou défaut) |
| `expires_at` | timestamp, nullable | posé à `Dossier.ended_at + ttl_hours` dès passage à un statut terminal, si `persist=false` |

`DossierDocument`, `ExecutionStep` et les résultats/prédictions n'ont pas de TTL propre : ils sont supprimés en cascade avec leur `Dossier` (comportement déjà existant pour la suppression d'un dossier), donc purgés dès que `dossier_ephemere.expires_at` est dépassé.

Une `Dossier` **sans** ligne dans `dossier_ephemere` = dossier classique, comportement inchangé.

## Flux d'usage

### Flux A — en deux étapes (définir puis lancer)

1. `POST /api/ephemeral/analyses`
   Body : `agents`, `classification`, `entities`, `persist` (bool, défaut `false`).
   Réutilise la création `Analyse` existante, puis ajoute la ligne `analyse_ephemere` correspondante. Renvoie `{ "analyse_id": ... }` dans tous les cas (persistant ou non).

2. `POST /api/ephemeral/analyses/{analyse_id}/runs?ttl_hours=48`
   Multipart : fichiers + `persist` (bool, défaut `false`).
   Réutilise la création `Dossier` + upload de `DossierDocument` existante (même code que `dossiers.py`), lie ce dossier à l'analyse, ajoute la ligne `dossier_ephemere`, lance le pipeline complet (équivalent du `launch` existant, déclenché automatiquement). Renvoie `{ "run_id": ... }`.

### Flux B — en un seul appel (analyse déjà connue)

- `POST /api/ephemeral/runs?ttl_hours=48`
  Body : `analyse_id` + fichiers + `persist`.
  Équivalent à l'étape 2 du flux A sans repasser par l'étape 1. `analyse_id` peut être **soit** une analyse créée via `/api/ephemeral/analyses` (éphémère ou non), **soit** l'id d'une `Analyse` classique déjà existante sur la plateforme (jamais passée par ce flux) — cas d'usage confirmé : relancer une analyse déjà configurée sur des documents jetables, sans créer/modifier l'analyse elle-même. Dans ce second cas, `dossier_ephemere.analyse_ephemere_id` reste `NULL`.

### Flux C — classification ou extraction d'un document en un seul appel

> Guide d'utilisation pas à pas, avec clé d'API, `curl` et exemples de réponses : [ephemeral-classification-extraction.md](ephemeral-classification-extraction.md).

Pour n'obtenir que les labels ou les entités d'**un** document, sans définir d'analyse : l'analyse éphémère (une seule étape, sans agent) et le run sont créés ensemble, même cycle de vie et même TTL que le flux B.

- `POST /api/ephemeral/classifications?ttl_hours=48` — multipart : `file`, `labels` (JSON `[{"name", "definition"}]`, au moins un), `multi_label` (défaut `false` : un seul label par page ; `true` : un ou plusieurs), `classification_prompt` (optionnel), `persist`. Renvoie `{ "run_id": ... }`.
- `GET /api/ephemeral/classifications/{run_id}` — `status`, `error` et, par document puis par page, les `labels` (`name`, `confidence`, `source`). Chaque page reçoit **deux classifications** : `source: "textual"` (texte de la page : OCR, description VLM, LLM) et `source: "visual"` (apparence de la capture, CLIP). Les labels textuels viennent d'abord, puis les visuels, chacun trié par confiance décroissante. `multi_label` s'applique aux deux sources.
- `POST /api/ephemeral/extractions?ttl_hours=48` — multipart : `file`, `entities` (JSON `[{"name", "definition", "type"}]`, au moins une), `extraction_prompt` (optionnel), `persist`. Renvoie `{ "run_id": ... }`.
- `GET /api/ephemeral/extractions/{run_id}` — `status`, `error` et, par document puis par page, les `entities` (`name`, `value`, `confidence`, `source`, `pages` = toutes les pages de l'entité). Chaque document reçoit **deux extractions** : `source: "textual"` (LLM) et `source: "gliner"` (GLiNER2.5, qui reçoit les définitions comme descriptions). Les entités textuelles viennent d'abord ; la même valeur peut apparaître avec chaque source. Les entités de type booléen ne sont extraites que par le LLM.

Les deux `GET` sont des vues de `GET /api/ephemeral/runs/{id}` (même scope strict, même conservation du résultat) ; `stop` et `DELETE` passent par `/api/ephemeral/runs/{run_id}`. `multi_label` est une colonne de `analyses`, posée à la création : elle n'est pas encore modifiable via l'API standard des analyses (donc sans historique de versions).

### Lecture / arrêt / suppression

- `GET /api/ephemeral/analyses/{id}` — définition complète (agents/classification/entités)
- `GET /api/ephemeral/runs/{id}` — statut, et résultats une fois `terminé`
- `POST /api/ephemeral/runs/{id}/stop` — arrêt complet du run en cours (réutilise le `stop` existant de `dossiers.py:203`, coupe l'exécution Celery en cours), statut → `arrêté`. Un run `persist=false` arrêté est finalisé comme un run terminé (résultat conservé, dossier et analyse supprimés) ; no-op sur un run déjà finalisé.
- `DELETE /api/ephemeral/runs/{id}` — arrête d'abord le run s'il est encore en cours (même effet que `stop`), puis supprime immédiatement le `Dossier`, ses `DossierDocument`, `ExecutionStep` et résultats (cascade existante) + la ligne `dossier_ephemere`, ou, si le run est déjà finalisé, le résultat conservé (`ephemeral_results`). Suppression immédiate, sans attendre le TTL, sans toucher à l'analyse liée.
- `DELETE /api/ephemeral/analyses/{id}` — supprime immédiatement l'`Analyse` + la ligne `analyse_ephemere`. **Scope strict** : ne s'applique qu'aux analyses ayant une ligne `analyse_ephemere` (créées via `/api/ephemeral/analyses`). Si `{id}` correspond à une `Analyse` classique de la plateforme (jamais passée par ce flux), l'endpoint renvoie 404 — il ne la supprime jamais. Refusé (409) si des `dossier_ephemere` non supprimés y font encore référence, pour éviter une suppression en cascade surprise — le client doit d'abord `DELETE` les runs concernés.

### Comportement `persist` (validé)

- `persist` se règle indépendamment sur l'analyse et sur le run.
- Si l'analyse est `persist=true` mais le run est `persist=false` : l'analyse est conservée, seuls le run, ses documents et ses résultats sont purgés au TTL.
- Si l'analyse est `persist=false` et n'est jamais réutilisée par un run après sa création : elle expire selon son propre TTL (fallback sur `created_at + ttl_hours` si `last_run_ended_at` est `NULL`).

## Purge

Tâche Celery périodique, planifiée via **Celery beat** (réutilise l'infra Celery existante, pas de CronJob Helm à ajouter) :

1. À chaque passage d'un `Dossier` en statut terminal (`terminé`/`échec`/`arrêté`, y compris après un `stop` manuel), si une ligne `dossier_ephemere` existe et `persist=false` : poser `expires_at = ended_at + ttl_hours` — fait directement dans le code qui marque le run terminé (callback worker → `/api/internal/*`), pas en batch, pour être réactif. Même logique pour `analyse_ephemere.last_run_ended_at` / `expires_at` si le run référence une analyse éphémère.
2. Job périodique (ex. toutes les heures) : supprime les `ephemeral_results` expirés, puis sélectionne les `dossier_ephemere` et `analyse_ephemere` avec `expires_at < now()` et `persist=false`, supprime le `Dossier`/`Analyse` correspondant (la cascade existante s'occupe de `DossierDocument`, `ExecutionStep`, résultats et fichiers S3 — même chemin de code qu'une suppression manuelle aujourd'hui).

## Authentification

Les endpoints `/api/ephemeral/*` acceptent **les deux** mécanismes d'auth existants :
- Clé d'API de l'environnement (variable `EPHEMERAL_API_KEY` du backend, vide = désactivée) : identité unique, toujours non persistante (`persist=true` → `403`), limitée aux analyses éphémères qu'elle a créées.
- Token API (`app_tokens.py`) pour un usage programmatique / compte de service, en-tête `X-App-Token: <clé>` ou `Authorization: Bearer <clé>`.
- Un access token Keycloak en `Authorization: Bearer` fonctionne aussi (rattaché au compte).
- Session Keycloak standard (cookie), pour un développeur qui teste depuis son compte.

**Visibilité :**

- Un compte Keycloak ne voit/ne peut agir (GET/stop/DELETE) que sur les analyses/runs éphémères auxquels il est associé — mêmes règles d'association que pour les analyses/dossiers classiques de la plateforme.
- Un token API (compte de service) voit/peut agir sur les ressources éphémères qu'il a créées.
- Pas de visibilité croisée entre comptes Keycloak et comptes de service en dehors de ces règles d'association/propriété.

**État actuel (implémenté par #22)** : scoping simplifié au créateur uniquement (`created_by` = `RequestContext.user_id` ou `AppToken.id`) pour les deux mécanismes — un compte Keycloak ne voit que ce qu'il a lui-même créé, pas encore de notion de "partage"/association élargie comme sur les analyses classiques (`AnalyseShare`). #08 affinera cette règle si le besoin apparaît (ex. partage d'une analyse éphémère entre plusieurs comptes d'une même équipe).

## Découpage en issues

Suivi sur GitHub : [issues #20 à #29](https://github.com/IA-Generative/mille-feuille/issues?q=is%3Aissue+20..29). Détaillées individuellement dans `docs/issues/` tant qu'elles ne sont pas implémentées (le fichier est supprimé une fois le code mergé, l'issue GitHub reste la référence) :

1. [GitHub #20](https://github.com/IA-Generative/mille-feuille/issues/20) — création des tables d'association `analyse_ephemere` et `dossier_ephemere` (Alembic). ✅ implémenté (`backend/app/models/analyse_ephemere.py`, `dossier_ephemere.py`, migration `7f1e8bb1c9da`).
2. [GitHub #21](https://github.com/IA-Generative/mille-feuille/issues/21) — suppression complète d'un `Dossier` : DB (cascade déjà câblée) + nettoyage S3. ✅ implémenté (`S3Connector.delete`, `DossierRepository.delete_dossier`).
3. [GitHub #22](https://github.com/IA-Generative/mille-feuille/issues/22) — `POST/GET/DELETE /api/ephemeral/analyses`. ✅ implémenté (`app/routers/ephemeral.py`, `app/repositories/ephemeral_repository.py`, `app/core/security/ephemeral.py`).
4. [GitHub #23](https://github.com/IA-Generative/mille-feuille/issues/23) — `POST/GET /api/ephemeral/runs` (flux A + B). ✅ implémenté (`_create_run` dans `app/routers/ephemeral.py`, CRUD `DossierEphemere` dans `ephemeral_repository.py`).
5. [GitHub #24](https://github.com/IA-Generative/mille-feuille/issues/24) — `POST .../stop` et `DELETE /api/ephemeral/runs/{id}`. ✅ implémenté.
6. [GitHub #25](https://github.com/IA-Generative/mille-feuille/issues/25) — logique `expires_at` sur fin de run, propagation vers `analyse_ephemere`. ✅ implémenté. A aussi nécessité de combler un trou plateforme : rien ne faisait passer `Dossier.status` à `terminé`/`échec` (seul `stop()` manuel existait) - ajouté dans `DossierRepository._complete_dossier_if_all_steps_done`, déclenché par le callback worker existant.
7. [GitHub #26](https://github.com/IA-Generative/mille-feuille/issues/26) — tâche Celery + planification Celery beat. ✅ implémenté (`backend/app/tasks.py`, service `backend-maintenance` dans `docker-compose.yaml`, beat embarqué `-B` sur la file `maintenance`).
8. [GitHub #27](https://github.com/IA-Generative/mille-feuille/issues/27) — double support token API / Keycloak + règles de visibilité. ✅ implémenté. A débusqué un vrai bug en écrivant les tests multi-utilisateurs : `get_ephemeral_identity` appelait `get_current_user(request)` directement plutôt que via `Depends()`, ce qui contournait silencieusement `app.dependency_overrides` - deux comptes Keycloak différents se voyaient mutuellement. Corrigé.
9. [GitHub #28](https://github.com/IA-Generative/mille-feuille/issues/28) — documentation OpenAPI du tag "Ephemeral". ✅ implémenté (summary/description/responses sur chaque endpoint, exemples et descriptions de champs dans `app/schemas/ephemeral.py`).
10. [GitHub #29](https://github.com/IA-Generative/mille-feuille/issues/29) — serveur MCP au-dessus de l'API éphémère, pour qu'un agent puisse l'appeler directement. ✅ implémenté (`backend/app/mcp/`, monté sous `/mcp` dans le process backend). Doc client : [backend/app/mcp/README.md](../backend/app/mcp/README.md).

## Points tranchés

- TTL par défaut : 24h. TTL maximum : 2 ans.
- Pas de limite de taille/nombre de documents spécifique aux runs éphémères.
- Purge via Celery beat (déjà inclus dans le package `celery`, pas de CronJob Helm, pas de nouveau service).
- `persist` indépendant entre l'analyse et le run.
- Auth : token API et Keycloak tous les deux acceptés, scoping par association/propriété (cf. section Authentification).
- `DELETE /api/ephemeral/analyses/{id}` : scope strict aux analyses éphémères, 404 sinon.
- Flux B : `analyse_id` peut référencer une analyse éphémère ou une analyse classique de la plateforme.
- Pas de possibilité d'étendre un TTL déjà posé (pas de `PATCH .../ttl_hours`).

## Questions ouvertes / points à éclaircir

Aucun point bloquant restant à ce stade. Tout ce qui a été soulevé lors des passes de relecture a été tranché ci-dessus.
