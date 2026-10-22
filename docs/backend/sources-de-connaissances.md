# Sources de connaissances

Une **source** est un fournisseur de collections branché sur la plateforme : une URL qui respecte le contrat
[base-de-connaissances-api.yaml](base-de-connaissances-api.yaml). Il peut y en avoir plusieurs. Les collections se
choisissent ensuite par analyse (issue #358) ; cette étape ne fait que déclarer et vérifier les sources.

| Route | Rôle |
| --- | --- |
| `GET /api/knowledge-sources` | les sources visibles de la personne (`q`, `page`, `page_size`) |
| `POST /api/knowledge-sources` | ajoute une source, **après** avoir vérifié la connexion |
| `GET /api/knowledge-sources/{id}` | une source visible (404 sinon) |
| `GET /api/knowledge-sources/{id}/collections` | les collections que **la personne** voit chez le fournisseur (`q`, `page`, `page_size`, filtrées et paginées côté fournisseur) |
| `POST /api/knowledge-sources/{id}/check` | revérifie la connexion avec l'identité de la personne qui demande |
| `DELETE /api/knowledge-sources/{id}` | seulement la personne qui l'a ajoutée, ou un administrateur |

## Ce qui est partagé avec les serveurs MCP

Rien n'est copié : la source réutilise les mêmes briques.

- **Garde d'URL anti-SSRF** (`services/tools/url_guard.py`) : https, pas d'identifiants, domaines autorisés, adresses privées refusées.
- **Authentification** (`services/tools/credentials.py`) : `none` ou `token_exchange` (échange de jeton Keycloak, `audience` obligatoire, aucun jeton ne passe par le worker). `static_token` est refusé comme point d'extension.
- **Visibilité** (`services/tools/visibility.py`) : privé, mes groupes, toute la plateforme ; une seule règle en Python et en SQL (`visible_clause` prend le modèle en paramètre).

## Le client du contrat

`services/knowledge/client.py` (`KnowledgeClient`, implémentation `HttpKnowledgeClient`) : lister (`/v1/collections`), retrouver par identifiants (`/v1/collections/lookup`, doublons retirés) et chercher (`/v1/search`). Il ne fait ni garde d'URL ni authentification : l'appelant lui donne l'URL et les en-têtes issus de `connection.prepare_call` (garde anti-SSRF **refaite à chaque appel**, échange de jeton au nom de la personne).

- **Réponses validées** contre le contrat (`contract.py`) : un champ manquant ou d'un autre type rend la réponse invalide (`invalid_response`), un champ hors contrat est ignoré et jamais relayé.
- **Bornes** : délai d'un appel de tool, réponse lue au plus `KNOWLEDGE_RESPONSE_MAX_BYTES` (2 Mo), texte de chaque passage coupé à `max_chars` (`truncated` vaut vrai), requête de recherche bornée comme le contrat (1 à 20 collections, `top_k` ≤ 50, question d'au moins 3 caractères) avant tout appel. Les redirections ne sont pas suivies.
- **Un échec partiel n'est pas un échec** : une collection indisponible est dans `skipped`, les autres répondent. Seul un fournisseur sans aucune collection utilisable répond en erreur (`no_usable_collection`).
- **Erreurs à code stable** (`unauthorized`, `forbidden`, `not_found`, `invalid_request`, `no_usable_collection`, `rate_limited`, `unavailable`, `not_implemented`, `invalid_response`, `not_json`, `too_large`) et à **message français fixe** : le message d'un fournisseur tiers n'est jamais relayé tel quel.

Les quotas par run et par personne et le journal des appels de recherche viennent avec le proxy d'appel de l'outil (#359), qui est le seul à appeler ce client pour un modèle.

## Vérification de la connexion

`GET {url}/v1/collections?page_size=1` avec les en-têtes d'authentification ; la réponse doit être un JSON avec une liste `items`. Erreurs à message affichable : `401/403` (authentification refusée), autre statut ou JSON invalide (« ne respecte pas le contrat »), fournisseur injoignable. Les redirections ne sont pas suivies (la garde d'URL n'a validé que l'adresse donnée). Le sondage passe par le client du contrat (`list_collections`, une page d'un élément) ; il est isolé derrière `SourceProbe` pour les tests.

Stockage : table `knowledge_sources` (migration `b5c6d7e8f9a0`), qui réutilise les types `tool_auth_mode` et `tool_visibility`.
