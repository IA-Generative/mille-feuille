# Recherche dans les dossiers (Qdrant, hybride)

`search_documents`, l'outil de recherche du chat et des agents, interroge un **index Qdrant par dossier** : une recherche
**hybride**, qui combine le sens (embeddings) et les mots (BM25), à la place de l'ancien index BM25 reconstruit en mémoire à
chaque exécution. Épique : #103.

## Qui fait quoi

| Composant | Rôle |
| --- | --- |
| backend | Tient l'**état** : réglages de l'analyse, index de chaque dossier, reconstructions. Ne parle jamais à Qdrant : il dépose des tâches. |
| `document_process` | Une fois l'OCR terminé, dépose `app.tasks.index_document` sur la file `agent_execution`. |
| `agent_execution` | Découpe, vectorise, écrit dans Qdrant (`app/search/`), reconstruit, et répond à `search_documents`. |
| Qdrant | Un **alias** `dossier_<id>` par dossier, qui désigne la collection active. |

## Réglages de l'analyse

Onglet « Recherche » de l'analyse, `GET|PUT /api/analyses/{id}/search-settings` (versionnés : historique et restauration).

- **Découpage** : `ia` (par défaut, un modèle d'IA coupe aux frontières de sens) ou `classique` (`size`, `overlap` en caractères).
  Le découpage par IA retombe sur le classique si le modèle échoue ou répond n'importe quoi : une page n'est jamais sans index.
- **`window`** : passages voisins renvoyés de chaque côté d'un passage trouvé (sans effet sur l'index).
- **Modèle d'embeddings** : choisi parmi ceux que le hub sert (`GET /api/models/embeddings`, sondés et mis en cache comme les
  modèles de chat). Un modèle laissé vide prend celui de la plateforme (`SEARCH_EMBEDDING_MODEL`, `SEARCH_CHUNK_MODEL`).

L'**empreinte** résume ce qui change le contenu de l'index (stratégie, modèles, taille et chevauchement du classique). Elle est
enregistrée sur chaque passage et sur le dossier.

## Un index par dossier

Deux vecteurs nommés par point : `dense` (cosinus) et `sparse` (BM25, l'IDF est calculé par Qdrant). Chaque passage porte son
dossier, son document, sa page, sa position dans la page (surlignage) et le hash du texte de la page. Les identifiants de points
sont déterministes : réécrire une page ne laisse rien derrière elle.

La recherche passe par l'**alias** du dossier : elle ne peut pas lire un autre dossier, quoi que contienne la requête. La requête
est vectorisée avec le modèle de **l'index** (pas celui de l'analyse, qui peut avoir changé depuis).

## Reconstruction blue/green

Changer les réglages rend obsolètes les dossiers déjà indexés : ils **gardent leur index** (la recherche continue) jusqu'à leur
reconstruction. `POST /api/dossiers/{id}/search-index/rebuild` (un dossier) ou
`POST /api/analyses/{id}/search-index/rebuild` (tous ceux qui ne sont plus à jour).

1. Le nouvel index `dossier_<id>_<empreinte>` se construit **à côté** de l'actif.
2. La construction est une **réconciliation** répétée : elle compare ce que l'index contient à ce que le dossier devrait y avoir
   (pages manquantes, texte changé, autre empreinte, pages disparues) et ne refait que la différence. Un document ajouté pendant
   la construction est donc rattrapé, et un job interrompu reprend où il en était.
3. L'**alias bascule en une opération atomique**, puis une dernière réconciliation rattrape ce qui a été écrit entre-temps.
4. L'ancien index est gardé : la personne **valide** (il est supprimé) ou **revient à l'ancien** (l'alias est remis dessus).

États : `queued` → `building` → `swapped` → `finalized`, ou `rolled_back`, ou `failed`. Un dossier a au plus une reconstruction
active. Pour une reconstruction en lot, `SEARCH_MAX_PARALLEL_REBUILDS` (3 par défaut) plafonne celles qui tournent en même
temps ; les autres attendent et démarrent à mesure que des places se libèrent. Une première indexation, sans ancien index, se
termine directement en `finalized`.

## Mesurer

`uv run python -m app.search.evaluation --dossier <id> --cases questions.json --k 5` (depuis `worker/agent_execution`) compare le
**lexical seul** (ce que faisait l'ancien BM25), le **sémantique seul** et l'**hybride** sur un jeu de questions
(`recall@k`, `hit@k`, `mrr`). Pour comparer deux découpages ou deux modèles, indexer le même dossier avec chacun et relancer.

Format du jeu de questions : `[{"question": "...", "expected": [{"document": "bail.pdf", "page": 2}, {"contains": "800 euros"}]}]`.

## Exploitation

- Qdrant : service `qdrant` de `docker-compose.yaml` ; sous-chart `qdrant` du chart Helm, service interne
  `millefeuille-qdrant:6333`, clé d'API dans le secret `millefeuille-qdrant` (voir `docs/secrets.md`).
- Les vecteurs et les passages sont des **données dérivées** de dossiers d'usagers : le modèle d'embeddings et le modèle de
  découpage doivent être hébergés dans un cadre validé. La suppression d'un dossier supprime son index.
- On part de zéro : il n'y a pas de reprise des dossiers déjà présents avant cette fonctionnalité.
- Sauvegarde : l'index se reconstruit depuis les pages stockées (`POST .../search-index/rebuild`) ; des snapshots de Qdrant
  accélèrent une restauration mais ne sont pas indispensables.
- Tests contre un vrai serveur : `QDRANT_TEST_URL=http://localhost:6333 QDRANT_TEST_API_KEY=... uv run pytest` dans
  `worker/agent_execution` (ignorés sans serveur).
