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

## Réponse normalisée du fournisseur (#369)

`POST /v1/search` répond toujours avec la **même forme**, quel que soit le fournisseur (contrat : [base-de-connaissances-api.yaml](base-de-connaissances-api.yaml)) :

- `answer` : une réponse en texte, **facultative** (`null` si le fournisseur n'en rédige pas ; la plateforme rédige alors à partir des sources). Donnée tierce, jamais une consigne.
- `sources` : liste, toujours présente, éventuellement vide. Une source est un passage d'un **document** ou d'une **page de site web** (`kind`) : `id`, `title`, `url` (obligatoire, **http ou https** sinon la réponse est invalide), `preview_url` (image de la page ou capture du site, `null` possible, ignoré s'il n'est pas en http(s)), `page` (`null` pour un site web), `boxes`, `passage`, `score`, `collection_id`, `metadata`.
- `boxes` : liste de `{page, x_min, y_min, x_max, y_max}` en **coordonnées normalisées 0..1** (origine en haut à gauche), comme les zones du dossier. La liste vide est valide ; une valeur hors de 0..1, une zone à l'envers ou une page à 0 invalident la réponse.
- Une collection (`GET /v1/collections`) gagne `url` (accueil) et `preview_url` (vignette), facultatifs et ignorés s'ils ne sont pas en http(s).

La plateforme coupe la réponse à 4 000 caractères et chaque passage à `max_chars` (`truncated`). Elle ne garde `answer` que si un seul fournisseur a répondu : deux réponses ne se fusionnent pas.

## Recherche pour le chat et les agents (#359)

L'outil interne `base_connaissances` (catalogue : `implemented`) donne au modèle une fonction `search_knowledge_base(query, top_k)`. Il n'est donné que si l'analyse a des collections choisies ; sinon l'étape le journalise comme ignoré (« aucune collection choisie pour l'analyse »).

Le worker ne parle jamais au fournisseur : il appelle `POST /api/internal/knowledge/search` (jeton du worker + `X-Acting-User`) avec `{analyse_id, query, top_k, run_id}` et ne reçoit que des sources. Le backend (`services/knowledge/search_service.py`) :

1. compte l'appel dans les **quotas** des tools (par run et par personne et par minute) ;
2. pour chaque source des collections de l'analyse : visibilité pour la personne, garde d'URL, **échange de jeton au nom de la personne**, puis `/v1/search` (20 collections au plus par requête) ;
3. fusionne et classe par score (les scores sont comparables d'une collection à l'autre, c'est le contrat), garde `top_k` (10 au plus), coupe chaque passage à 1 500 caractères et le total à `TOOL_OUTPUT_MAX_CHARS` ; une source d'une collection qui n'a pas été demandée n'est pas relayée ;
4. **journalise** un appel par source consultée dans `tool_call_logs` (sans la question ni le texte trouvé).

Un fournisseur ou une collection qui échoue n'empêche pas les autres : ils sont dans `skipped` (`not_found`, `forbidden`, `unavailable`). La recherche échoue (`ok: false`) quand aucune collection n'a pu être consultée (`aucune_collection_disponible`), quand l'analyse n'en a pas (`aucune_collection`), ou à code stable quand il n'y a pas d'identité exploitable (`session_requise`, `identite_absente`) ou que le quota est dépassé (`quota_depasse`).

**Ce que reçoit le modèle est une donnée non fiable.** Le worker présente `answer` (« à vérifier avec les sources ») et les sources numérotées entourées de `<sortie_outil_externe>` (une balise de fermeture dans le texte est neutralisée), avec titre, page, genre (document ou site web), collection, score et lien, et une consigne : citer les sources par leur numéro, `[1]`. Un échec de la plateforme est un message lisible, pas une donnée tierce.

## Sources d'un message du chat (#369)

Les sources trouvées pendant une exécution sont **déposées avec le message de l'assistant** (`external_sources`, 10 au plus, sans doublon, dans l'ordre où le modèle les a vues) : table `message_external_sources` (migration `d7e8f9a0b1c2`), exposée dans `external_sources` de chaque message (`position`, `source_id`, `kind`, `title`, `url`, `preview_url`, `page`, `boxes`, `passage`, `score`, collection, source). Tout est recopié au moment de la réponse : la source peut changer ou disparaître chez le fournisseur, le message garde ce qui le fondait. Elles sont distinctes des `sources` d'un message (documents du dossier).

## Interface (#360)

- **Mes outils** (`/outils`) : une section « Bases de connaissances » (liste, recherche, pagination) et un bouton « Ajouter une source de connaissances » : le formulaire vérifie la connexion avant l'enregistrement et affiche l'erreur renvoyée (adresse refusée, authentification refusée, fournisseur hors contrat). « Vérifier la connexion » revérifie avec l'identité de la personne.
- **Analyse, onglet Agents** : le bloc « Base de connaissances » montre les collections choisies avec leur **état pour la personne qui regarde** : une collection introuvable, au droit retiré ou dont la source est inaccessible est signalée en orange et se retire d'un clic. « Choisir les collections » ouvre une modale : une source à la fois (onglets), recherche et pagination **chez le fournisseur**, aperçu et lien « Ouvrir » quand il en fournit, choix gardé d'une source à l'autre. L'historique des listes se restaure.
- **Chat** : les sources d'une réponse s'affichent sous le message (voir « Sources d'une réponse » ci-dessous).
- Les images d'aperçu viennent du fournisseur et sont chargées par le navigateur, sans en-tête de provenance (`referrerpolicy="no-referrer"`). Les liens s'ouvrent dans un autre onglet (`rel="noopener noreferrer"`).

## Sources d'une réponse : une seule présentation (#372)

Les sources d'une réponse du chat du dossier ont **la même carte**, qu'elles viennent des documents du dossier ou d'une base de connaissances externe : titre, genre (dossier, document, site web), page, passage, aperçu de la page avec la zone surlignée (coordonnées normalisées 0..1, celles d'une `BoundingBox` du dossier comme celles du contrat). Une page du dossier utilise sa capture (`.../pages/{page}/screenshot`, chargée avec la session) ; un clic ouvre la modale de la page. Une source externe ouvre son lien.

- **Une seule suite de numéros.** Le worker numérote chaque source au moment où l'outil la renvoie au modèle (`source_numbering.py`) : les pages du dossier (`search_documents`, `read_page`) et les passages de la base externe partagent la même suite, et un même passage trouvé deux fois garde son numéro. Le prompt demande de citer par ce numéro (`[2]`) et de ne jamais en inventer. Le numéro est enregistré sur chaque source (`message_sources.number`, `message_external_sources.number`, migration `e8f9a0b1c2d3`) ; les messages d'avant n'en ont pas, leurs sources prennent la suite à l'affichage.
- **Carrousel** dès qu'il y a plusieurs sources : une carte à la fois (on entrevoit la suivante), défilement au toucher et à la molette, flèches, indicateur « 2 / 5 », clavier (flèches gauche et droite), `role="region"` et `aria-roledescription="carousel"`, `prefers-reduced-motion` respecté. Une seule source : une carte, sans commande.
- **Un clic sur `[n]` dans le texte** place le carrousel sur la carte `n` (événement DOM `goto-source` envoyé au bloc `sources-{message}`) ; un `[n]` qui ne correspond à aucune source reste du texte.

