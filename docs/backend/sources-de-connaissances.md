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

## Collections autorisées par analyse (#358)

L'analyse garde la liste des collections que son chat et ses agents peuvent interroger : `analyses.knowledge_collections` (migration `c6d7e8f9a0b1`), liste de `{source_id, collection_id, name}`, **versionnée** comme les autres champs d'une analyse (`VersionedField.KNOWLEDGE_COLLECTIONS` : chaque changement est une version, restaurable ; la liste restaurée devient elle-même une version).

| Route | Rôle |
| --- | --- |
| `GET /api/analyses/{id}/knowledge-collections` | les collections et **leur état pour la personne qui demande**, le nom à jour, et l'historique |
| `PUT /api/analyses/{id}/knowledge-collections` | remplace la liste (au plus 50) |
| `POST /api/analyses/{id}/knowledge-collections/restore/{version_id}` | restaure une liste antérieure |

- **Seules les collections ajoutées sont contrôlées** (comme les outils d'un agent) : source visible de la personne, collection retrouvée chez le fournisseur **avec son identité**, nom enregistré = celui du fournisseur. Une collection déjà choisie reste acceptée même devenue inaccessible, pour qu'on puisse modifier le reste de la liste. Refus : 422 `collections_refusees` avec la raison de chacune (`introuvable chez le fournisseur`, `accès refusé`, `source inaccessible ou qui ne répond pas`) ; rien n'est enregistré.
- **État affiché** : `available`, `not_found`, `forbidden` ou `source_unavailable` (source supprimée, plus visible, ou fournisseur qui ne répond pas : les autres collections s'affichent quand même). Il dépend de la personne : deux personnes peuvent ne pas voir la même chose.
- **Le worker** lit la liste dans `GET /api/internal/analyses/{id}` (`knowledge_collections`). Les droits ne sont pas contrôlés à cette lecture : c'est le fournisseur qui répond selon la personne au moment de la recherche (#359).

## Recherche pour le chat et les agents (#359)

L'outil interne `base_connaissances` (catalogue : `implemented`) donne au modèle une fonction `search_knowledge_base(query, top_k)`. Il n'est donné que si l'analyse a des collections choisies ; sinon l'étape le journalise comme ignoré (« aucune collection choisie pour l'analyse »).

Le worker ne parle jamais au fournisseur : il appelle `POST /api/internal/knowledge/search` (jeton du worker + `X-Acting-User`) avec `{analyse_id, query, top_k, run_id}` et ne reçoit que des passages. Le backend (`services/knowledge/search_service.py`) :

1. compte l'appel dans les **quotas** des tools (par run et par personne et par minute) ;
2. pour chaque source des collections de l'analyse : visibilité pour la personne, garde d'URL, **échange de jeton au nom de la personne**, puis `/v1/search` (20 collections au plus par requête) ;
3. fusionne et classe par score (les scores sont comparables d'une collection à l'autre, c'est le contrat), garde `top_k` (10 au plus), coupe chaque passage à 1 500 caractères et le total à `TOOL_OUTPUT_MAX_CHARS` ;
4. **journalise** un appel par source consultée dans `tool_call_logs` (sans la question ni le texte trouvé).

Un fournisseur ou une collection qui échoue n'empêche pas les autres : ils sont dans `skipped` (`not_found`, `forbidden`, `unavailable`). La recherche échoue (`ok: false`) quand aucune collection n'a pu être consultée (`aucune_collection_disponible`), quand l'analyse n'en a pas (`aucune_collection`), ou à code stable quand il n'y a pas d'identité exploitable (`session_requise`, `identite_absente`) ou que le quota est dépassé (`quota_depasse`). Un passage d'une collection qui n'a pas été demandée n'est pas relayé ; un lien n'est gardé que s'il est en http ou https.

**Les passages sont des données non fiables.** Le worker les présente au modèle entourés de `<sortie_outil_externe>` (une balise de fermeture dans le texte est neutralisée), avec le document, la page, la collection, le score et le lien, et une consigne : citer le document et la page. Un échec de la plateforme est un message lisible, pas une donnée tierce.

Limite : la citation passe par le texte de la réponse. Les passages ne sont pas encore ajoutés aux **sources** du message du chat (qui référencent des documents du dossier, pas des documents d'une base externe).

