# Accès aux analyses

Une analyse n'est plus ouverte à toute personne connectée (#662).

## Règle

Une seule règle (`app/services/analyse_access.py`) :

| Qui | Voit l'analyse |
| --- | --- |
| Super admin | toujours |
| Membre d'un groupe associé | oui |
| Personne ajoutée à l'analyse | oui |
| Toute autre personne | non : **404**, comme si elle n'existait pas |

Une analyse sans groupe ni personne ajoutée n'est vue que des super admins. Le créateur n'a aucun droit propre.

La règle s'applique à toutes les routes `/analyses/{id}/…` (garde `app/core/analyse_guard.py`, vérifiée par un test qui les parcourt), à la liste et aux thèmes, aux dossiers **« selon l'analyse »**, à l'annuaire d'affectation et à l'agent assistant.

## Créer et partager

- Seuls un super admin et qui a la permission « Créer une analyse » dans un groupe créent une analyse. Sans choix, elle est associée à ces groupes.
- `GET`, `PUT /api/analyses/{id}/access` et `POST …/access/restore/{version_id}` : groupes, personnes ajoutées avec un rôle, historique.
- Modifient les accès : un super admin, et qui a « Gérer les accès » dans un groupe de l'analyse. Celui-ci ne change que **ses** groupes, en laisse au moins un, et ne donne ni ne touche un rôle plus large que le sien.

## Mise à jour

Les anciens partages d'analyse **par groupe** deviennent les premiers accès. **Toutes les autres analyses ne sont plus vues que des super admins** jusqu'à ce qu'un groupe leur soit associé. Il en va de même de leurs dossiers « selon l'analyse ».

## Limites

- Le rôle d'une personne ajoutée est enregistré mais **pas encore appliqué** (#664).
- Retirer un accès à une analyse ne désaffecte pas la personne d'un dossier : elle ne le voit simplement plus.
