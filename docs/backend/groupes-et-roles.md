# Groupes et rôles de l'application

Les groupes et les rôles sont **gérés dans l'application** (épique #656). Keycloak ne sert plus qu'à se connecter et à désigner les **super admins** (rôle client `admin` ou `realm-admin`). Les groupes présents dans le jeton sont ignorés.

## Qui peut faire quoi

| Qui | Peut faire |
| --- | --- |
| Super admin | Créer, modifier, supprimer les groupes et les rôles ; gérer tous les membres |
| Membre avec « Gérer les membres » | Ajouter, changer, retirer des membres de son groupe, **sans donner ni toucher un rôle plus large que le sien** |
| Membre | Voir ses groupes et leurs membres |

Trois rôles sont fournis : « Admin de groupe » (figé), « Instructeur » et « Lecteur ». **Les permissions des rôles ne sont pas encore appliquées** (#664) : tout membre d'un groupe agit sur les dossiers de ce groupe.

## Lecture des droits

Les groupes d'une personne sont lus en base **à chaque requête** : un retrait vaut dès la suivante. `app_users.groups` en garde une copie, resynchronisée à chaque changement de membre, pour l'annuaire et pour l'agent assistant.

## Ajouter une personne

- **Personne connue**, choisie par son nom : elle est membre aussitôt.
- **Adresse e-mail** : la place est réservée (« En attente de connexion ») et rattachée au compte à sa prochaine requête, **si Keycloak déclare l'adresse vérifiée** (`email_verified`).

## Mise à jour depuis les groupes Keycloak

À faire **avant** : définir `ENCRYPTION_KEYS` et `EMAIL_INDEX_KEY` ([secrets](../secrets.md)) et vérifier que le royaume Keycloak fournit `email_verified`.

La migration crée un groupe pour chaque chemin Keycloak **utilisé** (dossier, serveur d'outils, source de connaissances, partage d'analyse), avec comme **Instructeur** les personnes que l'annuaire connaissait dans ce groupe, et remplace les références.

À faire **après**, par un super admin :

- ajouter les personnes jamais connectées avant la mise à jour : elles ne sont pas reprises ;
- désigner un **admin de groupe** dans chaque groupe : aucun ne l'est par défaut ;
- recréer les groupes Keycloak qui n'étaient utilisés nulle part, s'il en faut ;
- s'ajouter aux groupes sur lesquels il veut restreindre un dossier : on n'associe que ses propres groupes.

Le journal des dossiers antérieur garde les anciens chemins.
