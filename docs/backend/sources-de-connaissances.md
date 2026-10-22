# Sources de connaissances

Une **source** est un fournisseur de collections branché sur la plateforme : une URL qui respecte le contrat
[base-de-connaissances-api.yaml](base-de-connaissances-api.yaml). Il peut y en avoir plusieurs. Les collections se
choisissent ensuite par analyse (issue #358) ; cette étape ne fait que déclarer et vérifier les sources.

| Route | Rôle |
| --- | --- |
| `GET /api/knowledge-sources` | les sources visibles de la personne (`q`, `page`, `page_size`) |
| `POST /api/knowledge-sources` | ajoute une source, **après** avoir vérifié la connexion |
| `GET /api/knowledge-sources/{id}` | une source visible (404 sinon) |
| `POST /api/knowledge-sources/{id}/check` | revérifie la connexion avec l'identité de la personne qui demande |
| `DELETE /api/knowledge-sources/{id}` | seulement la personne qui l'a ajoutée, ou un administrateur |

## Ce qui est partagé avec les serveurs MCP

Rien n'est copié : la source réutilise les mêmes briques.

- **Garde d'URL anti-SSRF** (`services/tools/url_guard.py`) : https, pas d'identifiants, domaines autorisés, adresses privées refusées.
- **Authentification** (`services/tools/credentials.py`) : `none` ou `token_exchange` (échange de jeton Keycloak, `audience` obligatoire, aucun jeton ne passe par le worker). `static_token` est refusé comme point d'extension.
- **Visibilité** (`services/tools/visibility.py`) : privé, mes groupes, toute la plateforme ; une seule règle en Python et en SQL (`visible_clause` prend le modèle en paramètre).

## Vérification de la connexion

`GET {url}/v1/collections?page_size=1` avec les en-têtes d'authentification ; la réponse doit être un JSON avec une liste `items`. Erreurs à message affichable : `401/403` (authentification refusée), autre statut ou JSON invalide (« ne respecte pas le contrat »), fournisseur injoignable. Les redirections ne sont pas suivies (la garde d'URL n'a validé que l'adresse donnée). Le client réseau est isolé derrière `SourceProbe` ; le client complet du contrat (#357) s'appuiera sur les mêmes briques.

Stockage : table `knowledge_sources` (migration `b5c6d7e8f9a0`), qui réutilise les types `tool_auth_mode` et `tool_visibility`.
