# Plan de tests de bout en bout

Ce document sert à **construire et dérouler** un plan de tests de bout en bout (E2E) de la plateforme sur une stack complète, avec un vrai LLM. Il accompagne l'issue « Tests de bout en bout de l'analyse de dossier » et se complète au fil des essais : les sections « Résultats » sont à remplir, les scénarios à enrichir.

## Pourquoi

Les fonctionnalités récentes (analyse de dossier, propositions du chat, extraction par document, migration des validations, accès à l'assistant) ont été développées avec des **tests unitaires et d'API** et vérifiées dans le navigateur avec des **données simulées**. **Aucune n'a été vue fonctionner de bout en bout** : worker → API interne → base → interface, avec un vrai LLM. Ce plan comble ce manque.

Ce qui n'a notamment **jamais été vérifié** (extrait des descriptions de PR) :

| Sujet | Ce qui n'est pas vérifié |
|---|---|
| Génération de l'analyse (#125) | un vrai lancement : analyse, unités et éléments créés par le vrai pipeline |
| Extraction par document (#126) | la **qualité** d'extraction avant/après, le coût, les valeurs par défaut (8000 jetons, recouvrement 1, 8 définitions par groupe) |
| Chat → propositions (#115) | qu'un vrai modèle appelle `propose_update` au bon moment et **sans bruit** |
| Chat → assistant (#104) | la détection d'une demande qui concerne l'application, et la réception du préfixe de dossier par l'assistant |
| Vue de l'analyse (#116) | la page sur de vraies données ; accepter, restaurer, enregistrer de bout en bout |
| Migration des validations (#120) | la migration sur des données de production réelles |

## 1. Environnement

### Démarrer la stack

```bash
make up          # docker compose up --build : reconstruit les images
```

> **Les images backend et workers sont construites sans montage du code** : après une mise à jour de `dev`, il faut **reconstruire** (`--build`), sinon la stack tourne sur d'anciennes versions (c'est ce qui a empêché ces vérifications jusqu'ici). Le frontend, lui, est monté en volume (HMR) sur http://localhost:5173.

Services utiles : backend `:8000`, frontend `:5173`, Keycloak, PostgreSQL, Redis, RustFS (S3). Meilisearch n'est pas requis par ces scénarios.

### LLM

Les scénarios avec LLM exigent un hub compatible API OpenAI dans `.env` (voir `.env.example`) :

```
OPENAI_API_KEY=...
OPENAI_API_BASE_URL=...
LLM_MODEL=...      # classification, extraction, chat, agents
VLM_MODEL=...      # description des captures de page
```

Noter dans le rapport **le modèle et sa fenêtre de contexte** : les réglages d'extraction en dépendent.

### Comptes de test

Realm de dev (`docker/keycloak/mille-feuille-realm.json`) : `agent` / `agent` (instructeur) et `admin` / `admin`. Les routes internes du worker se testent avec l'en-tête `X-App-Token: dev-only-worker-token-not-for-prod`.

### Points d'attention de l'environnement

- **Fenêtre de CGU** : une version non acceptée bloque l'interface ; l'accepter (ou en désactiver l'obstacle) avant de tester.
- **Workers affichés « unhealthy »** : c'était un faux négatif, **corrigé** : le `HEALTHCHECK` du Dockerfile de `worker/document_process` utilisait `celery@$$HOSTNAME` ; dans un Dockerfile, `$$` est le PID du shell (le `$$` est une syntaxe de `docker-compose.yaml`), donc le nom du nœud ne correspondait jamais. Il utilise maintenant `celery@$HOSTNAME`. **Les images doivent être reconstruites** (`make up`) pour que le correctif s'applique ; un conteneur d'une ancienne image reste `unhealthy` alors que le worker fonctionne. Dans le doute, vérifier avec `docker compose exec <worker> celery -A app.celery_app inspect ping`.
- **Base de dev** : les tests automatisés du backend s'exécutent sur la base de dev et y laissent des données (dossiers, analyses de rattrapage). Pour un E2E propre, utiliser une **base neuve** (`docker compose down -v` est **destructif**).
- **Plusieurs migrations** s'appliquent au démarrage ; vérifier la révision : `docker compose exec backend alembic current`.

## 2. Jeu de données

**Uniquement des documents fictifs ou anonymisés** : ce sont des dossiers d'instruction d'usagers, jamais de données réelles dans un environnement de test partagé.

| Jeu | Contenu | Sert à |
|---|---|---|
| **D1 – nominal** | une pièce d'identité fictive (1 page) + un justificatif de domicile (2 pages) + un avis d'imposition fictif (2 pages) | parcours complet |
| **D2 – pages homonymes** | deux documents de 2 pages (donc deux « page 1 », deux « page 2 ») | rattachement des entités à la bonne page |
| **D3 – long** | un document de 20+ pages denses | lots par budget de jetons, recouvrement, doublons |
| **D4 – vide / illisible** | une page blanche, un scan flou | classification et extraction sur du texte pauvre |
| **D5 – référence** | D1 + **valeurs attendues connues** (vérité terrain) | mesure de la qualité d'extraction |

**Analyse de test** : 3 labels (CNI, justificatif de domicile, avis d'imposition) ; **au moins 9 entités** (pour obtenir 2 groupes de définitions avec la taille 8) : nom, prénom, date de naissance, adresse, code postal, ville, numéro fiscal, revenu, date du document ; **1 agent** de cohérence (sortie visible).

## 3. Outils de vérification

### Logs

```bash
docker compose logs -f backend worker-document-process
docker compose exec worker-document-process celery -A app.celery_app inspect ping   # vivants ?
```

### Base de données

```bash
docker compose exec postgres psql -U millefeuille -d millefeuille
```

```sql
-- Analyses d'un dossier (une par exécution), la plus récente en premier
SELECT sequence, status, analyse_version, started_at FROM dossier_analyses
 WHERE dossier_id = '<id>' ORDER BY sequence DESC;

-- Unités de calcul et leur empreinte
SELECT kind, status, element_count, left(input_fingerprint, 12) AS empreinte, description
  FROM analysis_units WHERE analysis_id = '<analyse>' ORDER BY created_at;

-- Éléments et leur version retenue
SELECT e.kind, e.definition_name, e.first_page_number, e.needs_review, v.origin, v.value
  FROM analysis_elements e JOIN analysis_element_versions v ON v.id = e.retained_version_id
 WHERE e.analysis_id = '<analyse>' ORDER BY e.created_at;

-- Propositions et journal des décisions
SELECT status, definition_name, proposed_value, proposed_by, model, prompt_version FROM analysis_proposals;
SELECT kind, actor_id, value, duration_seconds FROM analysis_proposal_events ORDER BY created_at;
```

### API

Cookie de session du navigateur (connexion Keycloak) ou jeton Bearer Keycloak de l'utilisateur de test. Routes principales (`/api/dossiers/{id}/...`) : `analyse-dossier` (courante), `analyses-dossier` (liste), `analyses-dossier/{a}/units`, `.../elements/{e}/versions`, `.../proposals`, `.../revisions`. La documentation OpenAPI du backend liste le reste.

### Compter les appels au LLM

Les journaux du backend (`docker compose logs backend`) tracent chaque extraction ; compter les lignes « Entity ... » et les unités déclarées (`analysis_units`) par type, avant et après un changement de réglage.

## 4. Plan de tests

Légende : **Auto** = automatisable plus tard (API + base) ; **LLM** = non déterministe (vérifier des propriétés, pas des valeurs exactes) ; **Manuel** = interface.

### A. Socle

| ID | Scénario | Attendu |
|---|---|---|
| A1 | Démarrage de la stack sur une base neuve | tous les services up ; `alembic current` = dernière révision ; workers répondent à `inspect ping` |
| A2 | Connexion `agent`, acceptation des CGU, liste des dossiers | pas d'erreur console ni 5xx |
| A3 | Création d'une analyse de test (labels, entités, agent) | visible dans l'interface, versionnée |

### B. Génération de l'analyse (#125)

| ID | Scénario | Attendu | Type |
|---|---|---|---|
| B1 | Créer D1, le lancer | une `dossier_analyses` (séquence 1) créée au lancement ; unités `classification` (une par page), `extraction` (par lot × groupe), `agent` (par étape) ; statut final `terminé` | Auto |
| B2 | Après exécution | un élément par prédiction (classification, entités), version `model`, lien vers la prédiction, page et document corrects ; une synthèse par agent | Auto |
| B3 | Relancer sans arrêt pendant l'exécution | pas de seconde analyse | Auto |
| B4 | Arrêter puis relancer | seconde analyse (séquence 2) ; la première reste consultable en lecture seule | Auto |
| B5 | Couper le hub LLM (mauvaise clé) puis lancer | étapes `échec` ; unités en cours passées en `échec` ; aucune donnée partielle trompeuse ; le dossier passe en `échec` | Auto |
| B6 | Dossier lancé **avant** la mise à jour (sans analyse) | l'étape se termine normalement ; pas d'erreur (compatibilité) | Manuel |
| B7 | Tuer le worker en cours d'extraction puis le relancer | état cohérent (unités `en_cours` repérables), pas de doublon d'éléments au rejeu | Auto |

### C. Extraction par document et empreintes (#126)

| ID | Scénario | Attendu | Type |
|---|---|---|---|
| C1 | D2 (deux « page 1 ») | chaque entité est rattachée à la page **de son document** | Auto |
| C2 | D3 (long) avec `EXTRACTION_MAX_TOKENS` bas | plusieurs lots ; une page commune entre lots ; **toutes** les pages couvertes ; pas de doublon (même définition, même valeur) | Auto |
| C3 | 9+ entités, groupe de 8 | 2 groupes, un appel par groupe, `description.group` = 0 puis 1 | Auto |
| C4 | Relancer sans rien changer | **mêmes empreintes** unité par unité (comparer les deux analyses) | Auto |
| C5 | Modifier le prompt d'extraction puis relancer | toutes les empreintes d'extraction changent, pas celles de classification | Auto |
| C6 | Modifier une seule définition (la dernière) | seules les empreintes de **son groupe** changent | Auto |
| C7 | Remplacer un seul document | seules les empreintes de **ses** unités changent | Auto |
| C8 | `EXTRACTION_MODE=legacy` | ancien découpage (lots de 5 pages sur tout le dossier), empreintes calculées quand même | Auto |
| C9 | **Qualité (D5)** : comparer `legacy` et `by_document` à la vérité terrain | tableau précision / rappel / entités tronquées ou manquantes, par mode | LLM |
| C10 | **Coût** : nombre d'appels et durée, `legacy` vs `by_document` | relevés dans le rapport | LLM |

### D. Vue de l'analyse (#116)

| ID | Scénario | Attendu |
|---|---|---|
| D1 | Ouvrir `/dossiers/<id>/analyse` sur D1 exécuté | éléments groupés, provenance « Modèle », confiance, page |
| D2 | Modifier une entité (avec motif) | version « Instructeur » ; la valeur du modèle reste visible ; motif obligatoire |
| D3 | Ajouter un élément à la main | apparaît, provenance « Instructeur » |
| D4 | Historique : diff mot à mot, restauration d'une version | une nouvelle version est ajoutée, rien n'est supprimé |
| D5 | Sélecteur d'exécution (après B4) | ancienne exécution en lecture seule |
| D6 | Analyse figée (passer le statut à `FIGEE` en base : pas de route) | modification, restauration et validation refusées (409), lecture possible |
| D7 | Deux onglets modifiant le même élément | pas de perte silencieuse (voir #118 pour le verrou, qui n'existe pas encore) |

### E. Chat → propositions (#115)

| ID | Scénario | Attendu | Type |
|---|---|---|---|
| E1 | « Le nom est bien Dupont, j'ai vérifié par téléphone » | `propose_update` appelé ; carte sous la réponse ; **rien d'appliqué** ; étape d'outil visible | LLM |
| E2 | Accepter, modifier, rejeter | version créée / valeur modifiée / rien ; journal : `proposed` puis la décision, avec durée, modèle, `chat-v2` | Auto |
| E3 | Modifier l'élément ailleurs puis accepter la proposition | 409 « modifié depuis », proposition toujours en attente, rejetable | Auto |
| E4 | Question simple (« Quel est le nom ? ») | **aucune** proposition | LLM |
| E5 | Supposition (« Il me semble que c'est Dupont ») | pas de proposition (ou à documenter) | LLM |
| E6 | Un message avec 3 informations distinctes | une proposition par information, max 5 par réponse | LLM |
| E7 | Dossier sans analyse | pas d'outils proposés, le chat répond normalement | Auto |
| E8 | Analyse figée | propositions refusées (409), le chat l'explique | Auto |
| E9 | Recharger la page | les cartes réapparaissent avec leur état réel | Manuel |
| E10 | **Mesure du bruit** : 30 messages scriptés (10 avec information claire, 10 questions, 10 ambigus) | tableau : propositions attendues / reçues, faux positifs, faux négatifs ; taux d'acceptation via le journal | LLM |

### F. Validations de prédiction (#120)

| ID | Scénario | Attendu | Type |
|---|---|---|---|
| F1 | Valider, corriger (avec zone), rejeter une prédiction | contrat de la route inchangé ; versions d'instructeur ; `prediction_validations` **non alimentée** ; rejet → « à revoir » | Auto |
| F2 | **Migration sur une copie d'une base réelle** | comptage avant/après identique (voir `docs/backend/migration-validations-prediction.md`) ; analyses de rattrapage jamais « courantes » | Manuel |
| F3 | Retour arrière puis remontée de la migration sur cette copie | ancienne table intacte ; pas de perte à la remontée | Manuel |

### G. Assistant (#104)

| ID | Scénario | Attendu | Type |
|---|---|---|---|
| G1 | Icône robot depuis un dossier | modale ouverte, bandeau « Ouvert depuis le dossier… », conversation du dossier intacte à la fermeture | Manuel |
| G2 | Premier message depuis le dossier | l'assistant **reçoit** la référence du dossier (préfixe) et s'en sert | LLM |
| G3 | « Crée-moi une analyse pour les CNI » dans le chat du dossier | `suggest_assistant` appelé, bouton « Ouvrir l'assistant », question pré-remplie | LLM |
| G4 | 20 messages (10 sur l'application, 10 sur le contenu du dossier) | taux de faux positifs / négatifs de la détection | LLM |

### H. Droits et sécurité

| ID | Scénario | Attendu | Type |
|---|---|---|---|
| H1 | Appels sans authentification | 401 | Auto |
| H2 | Routes internes sans jeton ou avec un mauvais jeton | 401 | Auto |
| H3 | Identifiants d'un autre dossier (analyse, élément, proposition) | 404 | Auto |
| H4 | Aucune route `usager` n'expose l'analyse | confirmé (il n'y en a pas encore : à retester avec #96) | Manuel |
| H5 | Journaux des workers et du backend | **aucune donnée personnelle** de dossier dans les logs de niveau info | Manuel |

### I. Résilience

| ID | Scénario | Attendu |
|---|---|---|
| I1 | Redémarrer le backend pendant une exécution | le worker réessaie ou échoue proprement ; pas d'élément en double |
| I2 | Redémarrer Redis pendant une exécution | état cohérent après reprise |
| I3 | Double clic sur « Accepter » | une seule version créée (verrou de ligne) |
| I4 | Deux utilisateurs acceptent la même proposition | un seul réussit, l'autre reçoit 409 |

## 5. Modèle de rapport d'exécution

À copier dans `docs/e2e/resultats/AAAA-MM-JJ.md` (un fichier par campagne).

```markdown
# Campagne E2E AAAA-MM-JJ

- Commit de `dev` testé : <hash>
- Stack : base neuve ? oui/non ; images reconstruites ? oui/non
- Modèle LLM / VLM : ... (fenêtre de contexte : ...)
- Réglages d'extraction : mode, max tokens, recouvrement, taille de groupe
- Jeux de données utilisés : D1, D2, ...

| ID | Statut (OK / KO / non joué) | Preuve (capture, requête, log) | Anomalie (n° d'issue) |
|---|---|---|---|

## Mesures
- Qualité d'extraction (C9) : ...
- Coût (C10) : ...
- Bruit des propositions (E10) : ...
- Détection de l'assistant (G4) : ...

## Décision
Go / no-go par fonctionnalité, réserves.
```

## 6. Critères de sortie

Une fonctionnalité est **validée** quand : tous ses scénarios « Auto » et « Manuel » sont OK, ses scénarios « LLM » donnent des résultats **documentés** et jugés acceptables par l'équipe métier, et chaque anomalie a une issue.

Seuils à **fixer avec les métiers** avant la campagne (je n'en propose pas de valeur) : taux minimal de précision et de rappel de l'extraction, taux maximal de propositions inutiles du chat, taux maximal de faux positifs de la détection de l'assistant, surcoût acceptable en appels LLM.

## 7. Automatisation

Ce qui s'automatise raisonnablement après la première campagne manuelle : les scénarios « Auto » (appels API + requêtes SQL) dans une CI avec la stack et un **LLM simulé** ; les parcours d'interface avec Playwright (déjà utilisé pour les captures de `docs/frontend/`). Les scénarios « LLM » restent des **campagnes de mesure** (non déterministes), pas des tests de non-régression.

## 8. Limites connues à garder en tête

- Les jetons de l'extraction sont **estimés** (≈ 4 caractères), pas comptés par un tokenizer.
- « Rejeté » n'est pas un état d'élément d'analyse : un rejet se traduit par « à revoir ».
- Une analyse de rattrapage (migration) peut porter le numéro d'exécution `0`.
- Il n'existe pas de route pour changer le statut d'une analyse (brouillon, validée, figée) : le passer en base pour D6.
- Pas encore de verrou ni de présence entre instructeurs (#118) ni de relance incrémentale (#119).
