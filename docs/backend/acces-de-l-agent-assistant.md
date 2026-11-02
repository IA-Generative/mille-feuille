# Accès de l'agent assistant aux dossiers

Issue [#222](https://github.com/IA-Generative/mille-feuille/issues/222), suite de [#177](acces-aux-dossiers.md). **L'agent assistant agit au nom d'une personne : il ne voit jamais plus de dossiers qu'elle.**

L'agent assistant est le modèle de langage qui cherche, crée et lance des dossiers à la demande d'une personne. Il existe sous deux formes, qui n'ont pas de session Keycloak :

| Forme | Qui l'appelle | Comment il s'authentifie |
| --- | --- | --- |
| **Agent de l'interface** (la fenêtre de l'assistant) | Le backend lui-même (`app/agent/helper/`), qui appelle les services au nom de la personne qui a ouvert la conversation. | L'identité de cette personne (`context_for_user`). |
| **Serveur MCP** (`/mcp/helper`) | Un client MCP extérieur (un assistant de développement, un script). | Un **jeton d'application** (`Authorization: Bearer …`), créé avec `POST /api/app-tokens`. |

Avant ce changement, ni l'une ni l'autre ne passait par la règle d'accès par groupe : n'importe quelle personne connectée pouvait créer un jeton d'application et lire, lancer ou modifier **un dossier restreint** par l'agent. La règle de l'API (garde sur `/dossiers/{id}/…`) est donc contournable par ce chemin, tant que l'agent n'a pas d'identité.

## Le principe

L'agent reçoit les **droits d'une personne** : ses groupes et son rôle d'administrateur. Il applique ensuite exactement la même règle que l'API :

- il **ne liste pas** les dossiers restreints dont la personne n'est pas membre ;
- un dossier qu'elle ne voit pas répond **« Dossier introuvable » (404)**, comme s'il n'existait pas, pour `get`, `launch` et `documents` ;
- un dossier qu'il **crée** est **restreint aux groupes de la personne**, comme par l'API ;
- un administrateur qui entre par l'agent dans un dossier restreint dont il n'est pas membre est **tracé** dans le journal (`admin_access`), comme ailleurs ([#182](acces-aux-dossiers.md)) ;
- le journal du dossier attribue les actions de l'agent **à la personne** (elle est responsable de ce que fait son agent), et non plus au système.

## Quelle personne ?

| Forme | La personne est… |
| --- | --- |
| **Serveur MCP** | **Le propriétaire du jeton d'application** (`created_by`) : la personne qui l'a créé. Le jeton a donc ses droits, ni plus ni moins. |
| **Agent de l'interface** | **L'auteur de la conversation** avec l'assistant. Le worker la transmet à chaque appel dans l'en-tête `X-Acting-User`. |
| Conversation ouverte par le MCP | Elle est signée du jeton ; on remonte au propriétaire du jeton. |

Les routes internes sont authentifiées par le jeton du worker, un **service de confiance** : l'en-tête `X-Acting-User` n'a de sens que venant de lui. Le navigateur n'y a pas accès.

### Les droits viennent de l'annuaire

Les groupes et le rôle d'une personne sont ceux que l'**annuaire local** a enregistrés à sa **dernière connexion** ([affectation](affectation-des-dossiers.md)). Conséquences :

- Une personne qui n'a **jamais ouvert l'application** n'est pas dans l'annuaire : son agent n'a **aucun groupe** et ne voit que les dossiers « selon l'analyse ».
- Un changement de groupe dans Keycloak n'est pris en compte qu'à la **prochaine connexion** de la personne ([#179](https://github.com/IA-Generative/mille-feuille/issues/179)).
- Sans `X-Acting-User`, ou avec une personne inconnue, l'agent n'a aucun droit : il ne voit pas de dossier restreint et **ne peut pas créer de dossier** (un dossier restreint a besoin d'au moins un groupe : 422 `groups_required`).

## Les routes internes de l'agent de l'interface

Toutes sous `/api/internal/agent`, avec `X-App-Token` et, pour agir au nom d'une personne, `X-Acting-User: <identifiant Keycloak>`.

| Route | Comportement |
| --- | --- |
| `GET /dossiers` | Les dossiers que la personne voit, paginés. |
| `GET /dossiers/{id}` | 404 « Dossier introuvable » si elle ne le voit pas. |
| `POST /dossiers` | Crée un dossier **restreint aux groupes de la personne** (422 si elle n'en a aucun). |
| `POST /dossiers/{id}/documents` | Ajoute des fichiers ; 404 si elle ne voit pas le dossier. Compté comme une **modification** pour la trace administrateur. |
| `POST /dossiers/{id}/launch` | Lance l'analyse ; 404 si elle ne voit pas le dossier. Compté comme une modification. |

```bash
# En tant que la personne alice (identifiant Keycloak), l'agent liste « ses » dossiers :
curl -H "X-App-Token: $WORKER_TOKEN" -H "X-Acting-User: alice-sub" \
  "$BACKEND/api/internal/agent/dossiers?page_size=20"
```

Côté worker, `app/tasks/helper_chat.py` charge la conversation puis appelle `api_client.act_for(client, conversation["created_by"])` : tous les appels suivants de la tâche portent l'en-tête.

## Le serveur MCP

Les outils qui prennent un dossier (`get_dossier`, `get_dossier_results`, `run_dossier`, `add_dossier_files`) répondent `{"error": "Dossier introuvable", "status_code": 404}` pour un dossier que le propriétaire du jeton ne voit pas. `list_dossiers` ne renvoie que les siens, `create_dossier` crée un dossier restreint à ses groupes.

**Conséquence pratique** : un jeton d'application **n'est plus un passe-droit**. Il vaut les droits de la personne qui l'a créé ; si cette personne quitte un groupe (et se reconnecte), le jeton perd cet accès. Pour donner à un agent l'accès à des dossiers restreints, c'est à **son propriétaire** d'y avoir accès.

## Pour les développeurs

- **`app/core/security/acting_user.py`** : `context_for_user(db, user_id)` construit le contexte (groupes, rôle) à partir de l'annuaire, et remonte d'un jeton d'application à son propriétaire ; `acting_user` en fait une dépendance FastAPI qui lit `X-Acting-User`.
- **`app/core/dossier_guard.py`** : `check_dossier_access(db, dossier_id, personne, method=…, write=…)` est la fonction commune à la garde des routes et aux chemins de l'agent (404 + trace administrateur).
- **Ajouter un outil MCP ou une route d'agent qui prend un dossier** : il doit s'appuyer sur la personne (`_acting(db, identity)` côté MCP, `Depends(acting_user)` côté interne) et appeler `check_dossier_access`. Un test (`tests/test_agent_access.py`) liste les outils MCP qui prennent un `dossier_id` et **échoue** si un nouvel outil apparaît : il faut alors le filtrer et l'ajouter à ce test.

## Tests

`backend/tests/test_agent_access.py` : liste filtrée, 404 sur get/launch/documents pour une personne extérieure aux groupes (et pas pour un membre), création restreinte aux groupes de la personne, personne inconnue sans droit, accès administrateur tracé, et les mêmes garanties par le serveur MCP (quatre outils, liste, création) avec des jetons de personnes différentes.

## Limites

- **Droits d'un instant** : ceux de la dernière connexion ; une session déjà ouverte ne reflète un changement de groupe qu'à la reconnexion.
- **Jeton sans propriétaire connu** : s'il a été créé par une identité absente de l'annuaire, il n'a aucun groupe.
- **Création de jetons** : n'importe quelle personne connectée peut en créer un ; il ne donne plus plus de droits qu'elle n'en a. Réserver cette création aux administrateurs reste possible, mais ce n'est plus nécessaire pour la confidentialité des dossiers.
- **Autres surfaces** : le serveur MCP **éphémère** (`/mcp`) et les routes des runs éphémères ne manipulent pas les dossiers persistants et n'ont pas ce besoin.

## Deux défauts corrigés au passage

Les tests de cette partie ont mis au jour deux défauts préexistants de l'agent, introduits par les évolutions précédentes sans être détectés :

- la route interne `GET /api/internal/agent/dossiers` et l'outil MCP `list_dossiers` **plantaient** (erreur 500) : la fonction qu'elles appelaient avait gagné un paramètre obligatoire (la personne) que ces appels ne fournissaient pas ;
- `list_dossiers` du serveur MCP échouait dès qu'un dossier avait un responsable ou une échéance (schéma de réponse qui ne lisait pas ces objets).
