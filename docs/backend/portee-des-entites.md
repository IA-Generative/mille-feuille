# Où chercher une entité : labels, exemples et zones

Un **label** de classification a des **documents d'exemple**. Une **entité** peut être limitée aux pages classées dans
**un ou plusieurs labels** et, facultatif, à des **zones** tracées sur ces exemples. Sans rien : tout le dossier, comme
avant.

## Définitions

- **Exemples d'un label** (`label_examples`, fichiers dans S3 sous `analyses/{id}/label-examples/`) : PDF, PNG, JPEG ou
  WebP, 10 Mo au plus, 10 par label. Routes sous `/api/analyses/{id}/classification/labels/{label}/examples` : liste,
  ajout (tout ou rien), fichier, suppression. Ils sont aussi dans `GET /api/analyses/{id}` (`labels[].examples`).
  Retirer un label ou supprimer l'analyse supprime leurs fichiers.
- `EntityDefinition.label_ids` (table `entity_definition_labels`) : labels de l'analyse où chercher l'entité (aucun :
  toutes les pages). Un label utilisé par une entité ne peut pas être retiré (422, avec le nom des entités).
- `EntityDefinition.zones` : rectangles `{x0, y0, x1, y1, example_id?}` en **fractions** de la page (0 à 1,
  `x1 > x0`, `y1 > y0`), 20 au plus. `example_id` : l'exemple sur lequel la zone a été tracée ; supprimer l'exemple
  garde le rectangle mais efface ce lien. Une zone suppose des documents de même gabarit (formulaires).
- **Identifiants stables** : `PUT /classification/labels` et `PUT /extraction/entities` acceptent un `id` par élément
  et le conservent (avant, chaque enregistrement recréait les lignes). Un `id`, un label ou un exemple inconnu de
  l'analyse est refusé (422). L'ordre est porté par `position`.
- **Historique** : les versions sauvegardent `id`, `label_ids` et `zones` ; les anciennes (sans ces champs) se
  restaurent toujours. À la restauration, un label ou un exemple disparu depuis est écarté (l'entité cherche alors
  partout, ou sur toute la page).

## Pour le worker d'extraction

Le backend expose déjà ce qu'il faudra lire, **le worker ne s'en sert pas encore** :

- `GET /api/internal/analyses/{id}` : chaque entité porte `label_ids` et `zones`.
- `GET /api/internal/dossiers/{id}/page-labels` : labels de chaque page selon la **valeur retenue** de l'analyse
  courante (la correction d'un instructeur prime, un label rejeté ne compte pas ; à défaut d'élément, les prédictions du
  worker).

## Pas encore fait

- Le **worker d'extraction** ne limite pas encore la lecture aux labels ni aux zones.
- Les **exemples ne sont pas versionnés** (ajout et retrait ne passent pas par l'historique des labels).
- L'API éphémère et le MCP ne permettent pas de définir la portée d'une entité.
