# Appeler un serveur MCP au nom d'une personne : l'échange de jeton

Issue [#334](https://github.com/IA-Generative/mille-feuille/issues/334), dans l'épique [#343](https://github.com/IA-Generative/mille-feuille/issues/343). **Un serveur MCP sait pour qui on l'appelle, sans que le moindre jeton passe par le worker.**

## Le principe

Quand un serveur MCP est ajouté avec l'authentification « identité de l'utilisateur » (`token_exchange`, le mode par défaut), le backend :

1. retrouve la **dernière session** de la personne (Redis), et rafraîchit son jeton d'accès si besoin ;
2. demande à Keycloak un **jeton pour l'audience du serveur** (échange de jeton standard, RFC 8693) ;
3. appelle le serveur avec ce jeton (`Authorization: Bearer …`).

Le jeton échangé a le même `sub` que la personne, l'audience du serveur, et `azp = mille-feuille-backend`. Il est gardé en cache quelques minutes (par personne et par audience).

Le worker ne voit jamais un jeton : il demande au backend « appelle ce tool » et ne reçoit que le résultat.

## Configuration de Keycloak

Keycloak 26.2 ou plus récent.

1. **Client backend** (`mille-feuille-backend`) : activer **Standard Token Exchange** (onglet *Settings*, *Capability config*). Dans un export de realm : l'attribut `standard.token.exchange.enabled` à `"true"`.
2. **Un client par serveur MCP** : son identifiant est l'**audience** saisie à l'ajout du serveur dans « Mes outils ».
3. **Un rôle sur ce client** (par exemple `use`), donné aux personnes qui peuvent utiliser le serveur. Sans lui, Keycloak répond « Requested audience not available » : l'audience doit être *disponible* pour la personne. C'est ce qui décide qui peut utiliser un serveur.

Le realm de développement (`docker/keycloak/mille-feuille-realm.json`) contient déjà le client `mille-feuille-mcp-demo`, son rôle `use`, et le donne aux utilisateurs `agent` et `admin` : l'audience à saisir pour essayer est `mille-feuille-mcp-demo`.

## Ce qui peut échouer

Chaque erreur a un **code stable**, renvoyé en clair à la personne et au modèle. Le détail de Keycloak n'est jamais renvoyé (il est journalisé).

| Code | Cause |
| --- | --- |
| `session_requise` | la personne n'a plus de session (déconnectée, expirée, renouvellement refusé) : elle doit se reconnecter |
| `echange_refuse` | Keycloak a refusé : échange non activé sur le client backend, audience inconnue, ou personne sans rôle sur le client cible |
| `audience_manquante` | le serveur n'a pas d'audience configurée |
| `identite_absente` | aucun utilisateur n'est associé à l'appel (ex. exécution lancée par un créneau) |

Une exécution sans personne connectée (un créneau de traitement) ne peut donc pas appeler ces serveurs : il faudra un **compte de service**, prévu mais pas encore implémenté (le point d'extension est `services/tools/credentials.py`).

## Pour le développement

```python
# Vérifier l'échange contre le Keycloak de docker compose
from keycloak import KeycloakOpenID
from app.services.tools.token_exchange import KeycloakTokenExchanger

openid = KeycloakOpenID(server_url="http://localhost:8080", client_id="mille-feuille-backend",
                        realm_name="mille-feuille", client_secret_key="dev-only-secret-not-for-prod")
user = openid.token("agent", "agent")
print(KeycloakTokenExchanger(openid).exchange(user["access_token"], "mille-feuille-mcp-demo"))
```

## Les modules

| Module | Rôle |
| --- | --- |
| `core/security/session.py` | index personne → session, jeton d'accès frais, verrou contre le renouvellement concurrent |
| `services/tools/token_exchange.py` | l'appel à Keycloak, derrière une interface |
| `services/tools/identity_tokens.py` | session, échange, cache court et erreurs à code stable |
| `services/tools/credentials.py` | les en-têtes d'authentification selon le mode du serveur |
