# Accès aux dossiers par groupe (backend)

Issue #177 (partie 1 : modèle, règle, création, modification, affectation), parent #144. Avoir accès à une **analyse** ne donne plus accès à tous ses **dossiers** : un dossier peut être **restreint** à certains [groupes de l'application](groupes-et-roles.md).

> **État : parties 1 et 2, et agent assistant.** La règle s'applique à **toutes** les routes d'un dossier, au suivi, au tableau de bord, aux notifications, aux créneaux et aux conversations, et l'**agent assistant** agit avec les droits de la personne pour qui il travaille ([détail](acces-de-l-agent-assistant.md)). L'**interface** est branchée ([accès aux dossiers, interface](../frontend/acces-aux-dossiers/README.md)). Restent les rôles et le lien de partage par e-mail (voir « Reste à faire »).

## Règle

Une seule règle, partagée (`app/services/dossier_access.py`) : aucune route ne réécrit la sienne.

| Qui | Voit un dossier… |
| --- | --- |
| **Administrateur** | tous. |
| Membre d'un groupe associé | **restreint** : s'il est membre d'un des groupes du dossier (pas d'héritage entre groupes). |
| Toute personne qui a [accès à l'analyse](acces-aux-analyses.md) | **« selon l'analyse »**. |
| N'importe qui | un dossier **« à ranger »** (sans analyse) suit ses groupes associés : il n'a pas d'analyse dont hériter. |

- Le **créateur n'a aucun droit propre** : son accès vient de ses groupes. S'il quitte le groupe, il perd l'accès.
- Un dossier qu'on ne voit pas répond **404** (jamais 403), pour ne pas révéler son existence.
- L'**affectation** ne donne pas d'accès : on affecte quelqu'un qui a déjà accès.

## Modèle

- `dossiers.visibility` : `restricted` ou `analyse`. Les dossiers **existants** sont migrés en `analyse` : personne ne perd d'accès à la mise en production ; ils restent visibles comme avant, sans limite de temps ([#180](https://github.com/IA-Generative/mille-feuille/issues/180)). Seuls les dossiers créés ensuite par un utilisateur sont restreints par défaut.
- `dossier_group_access` (`dossier_id`, `group_id`, `granted_by`, `created_at`) : les groupes associés, supprimés avec le dossier.
- `app_users.groups` : copie des groupes de la personne, resynchronisée à chaque changement de membre ; `app_users.is_admin` : super admin **vu à la dernière connexion** (annuaire, [affectation](affectation-des-dossiers.md)).

Schéma : [`data-model.png`](data-model.png). Migration : `20261013_0900_d9e0f1a2b3c4_acces_aux_dossiers.py`.

## Création

`POST /api/dossiers` accepte `visibility` (`restricted` ou `analyse`) et `group_paths`.

- Sans `visibility` : **restreint**, aux groupes que la personne choisit, **à défaut tous les siens**.
- Les groupes proposés sont **ceux de la personne**, y compris pour un administrateur (422 `group_not_yours` sinon).
- Un dossier restreint a **au moins un groupe** (422 `groups_required`), sinon son créateur lui-même ne pourrait plus l'ouvrir.
- `analyse` n'a pas de groupe : ceux qu'on enverrait sont ignorés.
- Les créations **sans session utilisateur** (agent assistant MCP, runs éphémères, routes internes) restent « selon l'analyse », comme avant.

## API

| Route | Rôle |
| --- | --- |
| `GET /api/dossiers/{id}/access` | Visibilité, groupes (avec qui les a associés et quand), `can_edit` (administrateur), `available_groups` (les groupes de la personne). Lisible par ceux qui voient le dossier. |
| `PUT /api/dossiers/{id}/access` | Remplace visibilité et groupes. **Administrateurs seulement** (403 sinon). Un groupe **ajouté** doit faire partie des groupes de l'administrateur ; un groupe déjà associé se garde ou se retire librement. Un dossier restreint garde au moins un groupe. |
| `PUT /api/dossiers/{id}/assignee`, `PUT /api/dossiers/bulk-assignee` | 422 `assignee_has_no_access` si la personne n'a pas accès (tout ou rien en lot, avec la liste des dossiers concernés) ; 404 pour un dossier qu'on ne voit pas. |
| `PUT /api/dossiers/{id}/access?dry_run=true` | **Simulation** : rien n'est enregistré ni tracé ; la réponse dit si la personne affectée perdrait l'accès (`assignee_unassigned`, `unassigned_person`). L'interface s'en sert pour la confirmation. |
| `PUT /api/dossiers/bulk-access` | Corps `{"dossier_ids": [...], "visibility": …, "group_paths": […]}` (1 à 200 dossiers). **Administrateurs seulement**, **une transaction** (tout ou rien : 404 avec la liste des dossiers introuvables, 422 pour un groupe qui n'est pas le sien ou un dossier restreint sans groupe). Les groupes **remplacent** ceux de chaque dossier. Renvoie `{updated, unchanged, unassigned}`. |
| `GET /api/dossiers`, `GET /api/dossiers/{id}` | Ne renvoient que les dossiers visibles ; chaque dossier porte `visibility` (pastille « Restreint »). |
| `GET /api/tracking?access=restricted\|analyse` | Filtre « Accès » du suivi ; chaque ligne porte `visibility`. |

Un changement d'accès est tracé dans le [journal](journal-du-dossier.md) (`access_changed` : visibilité avant et après, groupes ajoutés et retirés). Retirer un groupe **désaffecte** la personne qui perd ainsi l'accès (événement `assignee_changed` avec `reason: access_lost`) ; la réponse l'indique (`assignee_unassigned`). Changer la visibilité vers « selon l'analyse » ne désaffecte personne.

## Appliquée partout (partie 2)

**Une garde pour tous les dossiers** : `app/core/dossier_guard.py` est une dépendance branchée au niveau de chaque routeur qui porte `/dossiers/{dossier_id}/…` (dossiers, analyse de dossier, notes, brouillons et documents, propositions, documents générés, journal, travail à plusieurs, créneaux). Une personne qui ne voit pas le dossier reçoit **404 « Dossier introuvable »**, comme s'il n'existait pas, **avant** la validation du corps de la requête : on ne devine pas son existence par un 403 ou un 422.

- **Aucune route oubliée** : un test parcourt le schéma OpenAPI, appelle **chaque** opération sous `/dossiers/{dossier_id}` en tant que personne extérieure aux groupes et exige un 404. Une route ajoutée plus tard est testée sans qu'on y pense. Les routes internes des workers (`/api/internal/…`, jeton d'application) sont hors périmètre.
- **Suivi** (`GET /api/tracking`) : seuls les dossiers visibles sont listés, **comptés** et exportés.
- **Tableau de bord** : indicateurs, urgences, dossiers par statut, non affectés et activité ne portent que sur des dossiers visibles ; un dossier dont on perd l'accès disparaît de ses indicateurs.
- **Notifications** : on ne génère de notification que pour un dossier visible. Celles qui existent déjà **restent dans la liste** après un retrait d'accès, mais sans lien ni nom (`accessible: false`, `dossier_id` et `dossier_name` à `null` : « Dossier non accessible »).
- **Créneaux** et **conversations** : un créneau ou une conversation sur un dossier qu'on ne voit plus n'est plus listé (il n'est pas supprimé).
- **Annuaire** : `GET /api/users?dossier_id=…` ne propose que les personnes qui ont accès à ce dossier (même règle, évaluée sur leurs groupes et leur rôle vus à la dernière connexion).

### Accès administrateur tracé ([#182](https://github.com/IA-Generative/mille-feuille/issues/182))

Un administrateur qui entre dans un dossier **restreint dont il n'est pas membre d'un groupe** est tracé dans le journal (`admin_access` : `method`, `write`). Un administrateur membre d'un groupe associé, ou qui entre dans un dossier « selon l'analyse », n'est pas tracé : il y a accès comme tout le monde.

- Une **lecture** est tracée une fois par fenêtre (15 minutes, comme les consultations) ; **chaque modification** l'est. Les battements de présence et les verrous ne comptent pas comme des modifications.
- Ces traces ne sont **lisibles que des administrateurs** : les autres ne les voient ni dans l'historique, ni dans le filtre « Auteur ». Pour la même raison, l'entrée d'un administrateur « en passant par les droits d'administration » n'ajoute pas de consultation ordinaire.
- Durée de conservation et lecteurs définitifs : [#182](https://github.com/IA-Generative/mille-feuille/issues/182).

## Reste à faire

- *(fait, #222)* **Agent assistant** : il agit désormais avec les droits de la personne pour qui il travaille : [accès de l'agent assistant](acces-de-l-agent-assistant.md).
- Un lien de partage par e-mail ne doit jamais donner plus de droits que ceux du destinataire.
- Dossier restreint sans groupe actif ([#181](https://github.com/IA-Generative/mille-feuille/issues/181)).
- Appliquer les permissions des rôles : [#664](https://github.com/IA-Generative/mille-feuille/issues/664).
