# millefeuille-ephemeral

SDK Python pour l'API **éphémère** de mille-feuille (`/api/ephemeral/*`) : analyses et runs à la volée,
résultats disponibles pendant un TTL (défaut 24 h, max 17 520 h / 2 ans), purge automatique côté
serveur. Voir [docs/ephemeral-api.md](../../../docs/ephemeral-api.md).

Dépend de [`millefeuille`](../millefeuille/README.md) (client HTTP, exceptions, modèles).

## Installation

```bash
pip install millefeuille-ephemeral
```

## Authentification

```python
from millefeuille_ephemeral import EphemeralClient

client = EphemeralClient("https://api.mille-feuille.example.fr", api_token="ddd_...")  # X-App-Token
# ou bearer_token="<access token Keycloak>" / session_cookie="<cookie millefeuille_session>"
```

Chaque compte ne voit que les analyses/runs qu'il a créés (404 sinon).

## Cycle de vie côté serveur

Quand un run `persist=False` se termine (ou est arrêté), le serveur **conserve son résultat** jusqu'à
`expires_at` (fin du run + `ttl_hours`) et **supprime** le dossier, les fichiers envoyés et l'analyse
`persist=False`. `client.runs.get(run_id)` continue de renvoyer le résultat (avec `analyse_id=None`) ;
après `expires_at`, il lève `NotFoundError`. Conséquences :

- une analyse `persist=False` n'est pas réutilisable après ses runs : pour enchaîner plusieurs runs, la
  créer avec `persist=True` ;
- un run `persist=True` n'est jamais nettoyé (dossier, fichiers et résultats conservés).

## One-liner

```python
from millefeuille_ephemeral import EphemeralAnalysisConfig

result = client.analyze(
    files=["cni.pdf", "justif_domicile.pdf"],
    analysis_config=EphemeralAnalysisConfig(
        name="Vérification CNI + justificatif",
        classification_prompt="Classe le document (CNI, justificatif...)",
        labels=[{"name": "CNI", "definition": "Carte nationale d'identité"}],
        extraction_prompt="Extrait nom, prénom, adresse",
        entities=[{"name": "nom", "definition": "Nom de famille", "type": "texte"}],
        agents=[{"name": "vérif", "prompt": "Vérifie la cohérence des données"}],
    ),
    ttl_hours=48,
    timeout=300,
)
print(result.status, result.expires_at)
```

`analyze()` crée l'analyse, lance le run et attend la fin. Options : `analyse_id=` (réutiliser une
analyse existante au lieu de `analysis_config`), `persist=` (conserver le run), `cleanup=True`
(supprimer aussi le résultat conservé côté serveur une fois récupéré).

## Classer ou extraire un document, sans définir d'analyse

Pour les labels ou les entités d'**un** document, sans créer d'analyse (même cycle de vie et même TTL que
les runs ; voir [le guide](../../../docs/ephemeral-classification-extraction.md)) :

```python
classification = client.classify(
    "cni.pdf",
    labels=[
        {"name": "CNI", "definition": "Carte nationale d'identité"},
        {"name": "RIB", "definition": "Relevé d'identité bancaire"},
    ],
    multi_label=False,  # un seul label par page ; True : un ou plusieurs
    cleanup=True,  # supprime le run une fois le résultat récupéré
)
for document in classification.documents:
    for page in document.pages:
        for label in page.labels:  # chaque page reçoit deux classifications : "textual" et "visual"
            print(page.page_number, label.name, label.confidence, label.source)

extraction = client.extract(
    "facture.pdf",
    entities=[{"name": "montant", "definition": "Montant TTC", "type": "nombre"}],
)
for entity in extraction.documents[0].pages[0].entities:  # deux sources : "textual" (LLM) et "gliner"
    print(entity.name, entity.value, entity.pages, entity.source)
```

`classify()` et `extract()` créent le run, attendent sa fin (`timeout`, `poll_interval`) et renvoient le
résultat. Pour garder la main : `client.classifications.create(...)` / `client.extractions.create(...)`
renvoient aussitôt, puis `.get(run_id)` ou `.wait(run_id, timeout=...)`. Au moins une catégorie (ou une
entité) est requise, vérifié avant tout appel réseau.

## Lister ses runs

```python
for run in client.runs.list():  # du plus récent au plus ancien, 100 au plus
    print(run.id, run.kind, run.status, run.documents, run.persist, run.expires_at)
```

`kind` vaut `classification` ou `extraction` pour un run à une seule étape, `analyse` sinon.

## Flux A : réutiliser une analyse

```python
analyse = client.analyses.create(name="Réutilisable", persist=True, classification_prompt="...")
run1 = client.runs.create_for_analyse(analyse.id, files=["doc1.pdf"], ttl_hours=24)
result1 = client.runs.wait(run1.id)
client.runs.delete(run1.id)  # optionnel : la purge automatique s'en charge
client.analyses.delete(analyse.id)  # ConflictError si des runs y sont encore liés
```

## Flux B : un seul appel sur une analyse existante

```python
run = client.runs.create(analyse_id, files=["doc.pdf"], persist=False, ttl_hours=48)
```

`analyse_id` peut être une analyse éphémère ou une analyse classique de la plateforme.

## API

| Ressource | Méthodes |
|---|---|
| `client.analyses` | `create(name, description, persist, classification_prompt, labels, extraction_prompt, entities, agents)`, `create_from_config`, `get`, `delete` |
| `client.runs` | `create` (flux B), `create_for_analyse` (flux A), `list`, `get`, `stop`, `delete`, `wait(timeout, poll_interval)` |
| `client.classifications` | `create(file, labels, multi_label, prompt, persist, ttl_hours)`, `get`, `wait` |
| `client.extractions` | `create(file, entities, prompt, persist, ttl_hours)`, `get`, `wait` |
| `client` | `analyze(...)`, `classify(...)`, `extract(...)`, `version()` (version du backend) |

Un run démarre dès sa création : il n'y a pas d'appel `launch`. `expires_at` reste `None` tant que le
run n'est pas terminé (le TTL démarre à la fin du run) ou si `persist=True`.

`ttl_hours` est validé côté client (1 à 17 520) : `TTLValidationError`, aussi levée si le serveur
répond 400. Les autres erreurs sont celles de `millefeuille` (`NotFoundError`, `ConflictError`, …).

## Développement

```bash
uv sync
uv run ruff check . && uv run mypy src && uv run pytest
MILLEFEUILLE_BASE_URL=... MILLEFEUILLE_API_TOKEN=... uv run pytest -m integration
```
