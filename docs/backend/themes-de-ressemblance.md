# Thèmes de ressemblance

Rapprochements calculés à l'avance entre dossiers (#649), selon des thèmes définis par les administrateurs.

## Avant d'activer

Le calcul rapproche des personnes à travers tous les dossiers, sans qu'une recherche soit faite. Il est **désactivé par défaut**. À définir avant de l'activer : la finalité, la base légale, la durée de conservation et les personnes autorisées.

| Variable | Défaut | Effet |
|---|---|---|
| `RESEMBLANCE_ENABLED` | `false` | Active le calcul et la lecture des groupes |
| `RESEMBLANCE_INTERVAL_MINUTES` | `60` | Recalcul périodique des thèmes actifs |
| `RESEMBLANCE_SUGGESTION_MIN_SCORE` | `0.6` | Similarité minimale d'une entité proposée, à régler selon le modèle |

Les propositions d'entités demandent `QDRANT_URL` et `SEARCH_EMBEDDING_MODEL`. Sans eux, on choisit les entités à la main et l'écran le dit.

## Un thème

Nom, description, un à cinq critères **tous obligatoires**, portée, certitude annoncée, actif ou non. Chaque modification garde l'état précédent (restaurable). Supprimer un thème supprime aussi son historique.

- **Critère d'entités :** les entités tenues pour équivalentes, choisies ou acceptées par l'administrateur. Sans équivalence, seule l'entité choisie est comparée.
- **Même fichier :** même empreinte de contenu.
- **Portée :** tous les dossiers ; au sein d'un même thème d'analyse ; ou entre au moins deux thèmes d'analyse.

**Aucune extraction :** seules les valeurs déjà extraites par les analyses sont lues, comparées comme les liens exacts (sans casse, accents ni espaces en trop). Les dates sont admises dans un thème, sans rapprocher leurs différents formats. Les variantes (#648) ne s'appliquent pas aux thèmes.

## Entités équivalentes

La collection Qdrant `entity_definitions_*` contient un vecteur par définition d'entité (nom et définition). **Jamais de contenu de dossier ni de valeur extraite.** Elle est mise à jour à chaque demande de proposition. Elle propose, seul l'administrateur décide ; un refus est gardé avec le critère.

## Calcul

En tâche de fond : à chaque enregistrement d'un thème, puis toutes les heures pour les thèmes actifs. Un changement dans un dossier est donc pris en compte avec ce délai ; les preuves, elles, sont toujours relues sur les valeurs actuelles.

- Ce que partagent plus de 20 dossiers, ou plus de 10 % d'entre eux, ne rapproche pas.
- La base ne garde que le thème, une empreinte du groupe et les dossiers : aucune valeur n'est copiée. Un dossier supprimé quitte ses groupes.
- Le calcul charge en mémoire les valeurs des entités citées : à mesurer sur un gros volume avant activation.

## Lecture et droits

`/api/resemblances` : thèmes (lecture des actifs pour tous, écriture aux administrateurs), groupes paginés, entités et propositions (administrateurs).

- Les droits sont appliqués à la lecture : seuls les dossiers visibles, et un groupe n'est renvoyé que s'il en reste au moins deux.
- Un administrateur qui lit un groupe avec un dossier hors de ses groupes est tracé.
- Écarter un rapprochement demande de pouvoir **valider** sur chacun des dossiers qu'on voit. Il disparaît pour tout le monde ; qui et quand sont conservés, et on peut le rétablir.
- « Dossiers en double » n'est pas une règle à part : c'est un thème, par exemple « même personne et même numéro ».
