# Recherche à travers les dossiers

`POST /api/search` (#642, épique #637) : `{"query": "…", "limit": 20}` (50 au plus). Un `POST` pour que les mots cherchés, souvent des noms de personnes, n'apparaissent ni dans l'URL ni dans les journaux. Une erreur SQL n'est journalisée que par son type, son message reprenant les paramètres.

## Ce qui est cherché

Le nom du dossier, le nom de ses documents, les valeurs extraites retenues de son analyse courante (une valeur rejetée ne compte pas) et le texte des pages. Une référence (`DOS-2026-0012`) désigne le dossier.

- **Tous** les mots doivent être trouvés dans le dossier, pas forcément au même endroit.
- Français, sans tenir compte des accents ni des majuscules ; pluriels, accords et débuts de mots acceptés.
- Classement : le nom du dossier d'abord, puis les valeurs, les noms de documents et les pages.

## Réponse

`total` (tous les dossiers trouvés) et `dossiers` (les plus pertinents) : référence, nom, analyse, thème, et trois extraits au plus (document, page, nom de la valeur, morceaux surlignés).

`"details": false` ne rend que les dossiers, sans extraits ni liens (choisir un dossier par son nom).

## Points communs

La réponse porte aussi `items`, ce qui relie au moins deux des dossiers renvoyés (40 au plus) :

| `kind` | Ce qui est partagé |
|---|---|
| `identifier` | La même valeur d'une entité de type « identifiant » |
| `value` | La même valeur d'une autre entité ou d'un champ (texte) |
| `document` | Le même fichier (même empreinte de contenu) |

- Les valeurs sont comparées sans tenir compte de la casse, des accents ni des espaces. La correction d'un instructeur prime, une valeur rejetée ne compte pas.
- Les dates, les nombres, les booléens, les classifications et les valeurs vides (« oui », « néant »…) ne relient pas.
- Ce que partagent plus de 20 dossiers visibles, ou plus de 10 % d'entre eux, est écarté.
- Chaque preuve donne le dossier, le document, la page, la valeur telle qu'elle est écrite et son origine (« Analyse X · entité »).

Les définitions d'entités n'ont pas de type « personne », « entreprise » ou « adresse » : ces liens sont des `value`.

## À partir de dossiers choisis

`POST /api/search/links` (#645) : `{"dossier_ids": [...], "include_related": true}`, 10 dossiers de départ au plus. La réponse donne `anchor_ids`, `dossiers` (les départs puis, avec `include_related`, 20 autres dossiers visibles au plus, ceux qui relient le plus de départs d'abord) et `items`, chacun touchant un départ. Un dossier de départ non visible répond 404 avec la liste des identifiants refusés, qu'il existe ou non.

## Droits

Seuls les dossiers visibles de la personne sont cherchés (`visible_clause`, dans la requête). Un point commun ne mentionne jamais un dossier absent de la réponse. Un administrateur qui reçoit un extrait ou une preuve d'un dossier hors de ses groupes est tracé (`admin_access`). Des dossiers non accessibles, rien n'est dit sauf si l'annonce est activée (ci-dessous).

## Dossiers non accessibles

Décision #641 : on peut annoncer qu'il en existe (#647). La réponse porte alors `hidden` : par thème, le **nombre** de dossiers non visibles qui partagent une valeur ou un fichier avec les résultats (ou les dossiers de départ), et les dossiers accessibles concernés. Jamais d'identifiant, de nom, d'extrait ni de motif.

| Variable | Défaut | Effet |
|---|---|---|
| `SEARCH_HIDDEN_LINKS_ENABLED` | `false` | Active l'annonce |
| `SEARCH_HIDDEN_LINKS_MIN` | `1` | Nombre de dossiers en dessous duquel un thème n'est pas annoncé |

Rien n'est annoncé sans résultat accessible, ni à un administrateur (il voit tout).

**Ce que l'annonce révèle.** Un nombre suffit à apprendre qu'une valeur existe ailleurs : une personne qui met un nom dans un de ses dossiers peut savoir si d'autres dossiers le citent. Les recherches ne sont pas journalisées. À activer en connaissance de cause.

## Index et performances

La migration ajoute `document_pages.search_vector`, calculé par la base, des index plein texte, la fonction `dossier_link_key` (PostgreSQL 14 ou plus) et son index. Elle **réécrit la table des pages** : prévoir un temps de mise à jour proportionnel à son volume. Elle reprend les configurations `french_unaccent` et `simple_unaccent`, qui demandent l'extension `unaccent`.

Mesures sur un poste de développement (PostgreSQL 16, données fictives) :

- texte : 4 000 dossiers, 200 000 pages de 2 Ko (1,1 Go), de 0,2 à 0,6 s, y compris pour un mot présent sur toutes les pages ;
- liens : 100 000 valeurs extraites, environ 0,3 s à partir de 10 dossiers ; une recherche dont les mots désignent 4 000 dossiers prend alors 1,2 s.

## Page « Recherche »

- **Par mots-clés** : 20 résultats au plus, le total est annoncé. Les mots cherchés ne sont jamais mis dans l'adresse.
- **À partir de dossiers** : on y arrive en cochant des résultats, depuis la liste des dossiers ou depuis un dossier. La sélection (des identifiants, 10 au plus) est dans l'adresse (`/recherche?dossiers=…`) : on la retrouve en revenant en arrière.
- **Rapprochements** : encore une maquette sur données fictives (#649, bloquée par #641).
