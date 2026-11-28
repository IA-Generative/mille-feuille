# Recherche à travers les dossiers

`POST /api/search` (#642, épique #637) : `{"query": "…", "limit": 20}` (50 au plus). Un `POST` pour que les mots cherchés, souvent des noms de personnes, n'apparaissent ni dans l'URL ni dans les journaux. Une erreur SQL n'est journalisée que par son type, son message reprenant les paramètres.

## Ce qui est cherché

Le nom du dossier, le nom de ses documents, les valeurs extraites retenues de son analyse courante (une valeur rejetée ne compte pas) et le texte des pages. Une référence (`DOS-2026-0012`) désigne le dossier.

- **Tous** les mots doivent être trouvés dans le dossier, pas forcément au même endroit.
- Français, sans tenir compte des accents ni des majuscules ; pluriels, accords et débuts de mots acceptés.
- Classement : le nom du dossier d'abord, puis les valeurs, les noms de documents et les pages.

## Réponse

`total` (tous les dossiers trouvés) et `dossiers` (les plus pertinents) : référence, nom, analyse, thème, et trois extraits au plus (document, page, nom de la valeur, morceaux surlignés).

## Droits

Seuls les dossiers visibles de la personne sont cherchés (`visible_clause`, dans la requête). Un administrateur qui reçoit un extrait d'un dossier hors de ses groupes est tracé (`admin_access`). Rien n'est dit des dossiers non accessibles (voir #641).

## Index et performances

La migration ajoute `document_pages.search_vector`, calculé par la base, et des index plein texte. Elle **réécrit la table des pages** : prévoir un temps de mise à jour proportionnel à son volume. Elle reprend les configurations `french_unaccent` et `simple_unaccent`, qui demandent l'extension `unaccent`.

Mesure sur un poste de développement (PostgreSQL 16, 4 000 dossiers, 200 000 pages de 2 Ko, soit 1,1 Go) : de 0,2 à 0,6 s, y compris pour un mot présent sur toutes les pages. 26 à 45 requêtes pour 20 résultats vus par un administrateur (les traces d'accès en sont la plus grande part).
