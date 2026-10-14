# Sources des fichiers

D'où vient un fichier déposé dans un dossier (courrier, guichet, autre administration…) ? Une **source** est libre,
définie par l'utilisateur, avec une **description** que l'IA reçoit en contexte. Elle se choisit (ou se crée) au
moment du dépôt, et se corrige ensuite.

## Modèle

Table `document_sources` (`DocumentSource`) : `name`, `description`, et **exactement un propriétaire** (contrainte
`ck_document_source_one_owner`) :

| Source | `analyse_id` | `dossier_id` | Visible |
|---|---|---|---|
| **Catalogue d'analyse** | renseigné | vide | dans tous les dossiers de l'analyse |
| **Tampon** | vide | renseigné | dans ce seul dossier « à ranger » |

Le nom est unique dans un catalogue d'analyse, et dans un dossier pour les tampons. `dossier_documents.source_id`
(optionnel) rattache chaque document à sa source ; supprimer une source laisse ses documents, **sans source** (`ON
DELETE SET NULL`). **Pas de versionnage** : modifier ou supprimer est définitif.

## Dossier « à ranger »

Un dossier sans analyse n'a pas de catalogue : ses sources sont des tampons. Quand il est rattaché à une analyse
(`POST /api/dossiers/{id}/assign`), ses tampons **rejoignent le catalogue de l'analyse**. Si l'analyse a déjà une
source du même nom, on garde celle-là et les documents sont rebranchés dessus. Aucun document n'est réécrit autrement.

## Routes

| Route | Rôle |
|---|---|
| `GET /api/analyses/{id}/sources` | catalogue de l'analyse |
| `POST /api/analyses/{id}/sources` | ajoute une source au catalogue (409 si le nom existe) |
| `GET /api/dossiers/{id}/sources` | sources proposées pour ce dossier : celles de son analyse, ou ses tampons |
| `POST /api/dossiers/{id}/sources` | crée une source depuis le dossier : catalogue de l'analyse, ou tampon s'il n'a pas d'analyse |
| `PUT` / `DELETE /api/sources/{id}` | modifie / supprime (une source tampon suit la visibilité de son dossier : 404 sinon) |
| `PUT /api/dossiers/{id}/documents/{doc}/source` | change la source d'un document, ou la retire (`source_id: null`) |
| `POST /api/dossiers/{id}/documents` | champ `source_id` (form, optionnel) : la source de tous les fichiers du dépôt (422 si elle n'est pas celle de l'analyse du dossier ou un tampon du dossier) |

L'événement `document_added` du dossier enregistre le `source_id`, jamais le nom du fichier (#169).

## Ajouter un fichier après coup

`POST /api/dossiers/{id}/documents` fonctionne sur un dossier **quel que soit son état** : rien n'est refusé. Les
fichiers ajoutés ne sont pas vus par une analyse déjà lancée : l'interface compare la date de dépôt de chaque
document (`created_at`) au dernier lancement (`started_at`) et propose de relancer.

## Contexte donné à l'IA

L'API interne renvoie la source (`name`, `description`) avec chaque document, et les workers la donnent en contexte :

- **classification** : dans le prompt de chaque page du document (la classification visuelle CLIP ne la voit pas) ;
- **extraction** : en tête du texte des pages (mode « par document ») ;
- **agents et chat** : dans le libellé du document, et avec le contenu d'une page lue ;
- **résumés** : en tête du texte à résumer.

Elle fait partie de l'**empreinte** de chaque unité de calcul, mais seulement si le document a une source : les
empreintes des documents sans source ne changent pas (une relance reprend donc ce qui n'a pas changé), et changer la
source d'un document fait recalculer ses unités à la prochaine relance.
