# Values du chart

`common-values.yaml` porte les valeurs **communes à tous les environnements** déployés (registre Harbor, secrets Vault, workers,
KEDA…). Il se **superpose** aux values du chart (`../values.yaml`) et est lui-même surchargé par les values **propres à chaque
environnement** (hôtes, domaines, ressources), qui ne sont pas dans ce dépôt : elles vivent côté Argo CD.

```bash
helm template millefeuille ./millefeuille \
  -f millefeuille/values/common-values.yaml \
  -f <values de l'environnement>.yaml
```

## Les trois réglages qui structurent le fichier

| Clé | Valeur dans `common-values.yaml` | Sert à |
|---|---|---|
| `global.projectName` | `exploration` | Projet Harbor, ajouté devant **chaque dépôt d'image**, et **point de montage Vault** de tous les secrets |
| `global.env.ENVIRONMENT` | *(non défini : `dev` par défaut)* | Environnement, premier segment du **chemin Vault** des secrets |
| `global.ingress.hosts` | *(à fournir par l'environnement)* | Hôtes et chemins exposés |

### `global.projectName`

Écrit **une seule fois**. `helper.image` le préfixe à chaque `repository` : on écrit `repository: "mille-feuille-backend"` et l'image
devient `harbor…/exploration/mille-feuille-backend:<version>`. Un `repository` qui commence déjà par `exploration/` n'est pas préfixé
deux fois. Les images qui ne viennent pas de ce projet (Redis, par exemple) ne passent pas par ce helper. Vide (valeur par défaut du
chart) : les dépôts sont utilisés tels quels.

### `global.env.ENVIRONMENT` et le chemin Vault des secrets

Chaque secret Kubernetes est synchronisé par le Vault Secrets Operator depuis le chemin :

```
<mount>/<env>/millefeuille/<secret>
   │       │                   └─ nom court : s3, openai, keycloak, worker, async-api-worker, redis, db-superuser, db-appuser, db-backups
   │       └─ global.env.ENVIRONMENT (dev, recette, prod…)
   └─ global.projectName (exploration)
```

Par exemple, avec `ENVIRONMENT: "dev"` : `exploration` / `dev/millefeuille/s3`. Le schéma n'est écrit qu'à un endroit, le helper
`helper.vaultSecretPath` (`templates/_helpers.tpl`) ; le secret `millefeuille-db-infos` est calculé à partir de `db-appuser`.

- **`dev` est la valeur par défaut** quand `global.env.ENVIRONMENT` n'est pas défini. **Tout autre environnement doit le renseigner**,
  sinon il lirait les secrets de `dev`.
- `global.env` peut être une table (`ENVIRONMENT: dev`, ou `ENVIRONMENT: {value: dev}`) ou une liste native d'entrées ; les trois
  formes sont comprises.
- `global.env` est aussi injecté comme variable d'environnement dans les pods.
- Le détail de chaque secret (variables attendues, création, rotation) est dans [docs/secrets.md](../../docs/secrets.md).

> **Migration.** Avant ce schéma, les secrets étaient à la racine du mount (`millefeuille-s3`…). Les **copier vers les nouveaux
> chemins avant de déployer**, sinon l'opérateur ne les trouve plus. Si les values d'un environnement définissent déjà `spec.path`
> pour ces objets, elles l'emportent : les retirer pour utiliser le schéma commun.

## Exemple : values d'un environnement

```yaml
global:
  env:
    ENVIRONMENT: "dev"            # chemin Vault : exploration/dev/millefeuille/<secret>
  ingress:
    hosts:
    - name: "millefeuille-dev.<domaine>"
      paths:
      - {pathType: "Prefix", path: "/api/", backend: {serviceName: "millefeuille-backend", portNumber: 8000}}
      - {pathType: "Prefix", path: "/", backend: {serviceName: "millefeuille-frontend", portNumber: 8080}}
    - name: "unefeuille-dev.<domaine>"         # UneFeuille, le frontend de l'API éphémère
      paths:
      - {pathType: "Prefix", path: "/api/", backend: {serviceName: "millefeuille-backend", portNumber: 8000}}
      - {pathType: "Prefix", path: "/", backend: {serviceName: "millefeuille-ephemeral-frontend", portNumber: 8080}}

ephemeral_frontend:
  env:                             # lues au démarrage du conteneur
    API_BASE_URL: "https://millefeuille-dev.<domaine>"       # l'hôte de MilleFeuille : là où le cookie de session est posé
    MILLEFEUILLE_URL: "https://millefeuille-dev.<domaine>"   # lien « Accéder à MilleFeuille »

backend:
  env:
    EPHEMERAL_FRONTEND_URL: "https://unefeuille-dev.<domaine>"   # CORS et redirection après la connexion
```

Voir aussi [`ephemeral-frontend/README.md`](../../ephemeral-frontend/README.md) pour UneFeuille.

## Vérifier un jeu de values

```bash
helm lint millefeuille -f millefeuille/values/common-values.yaml -f <values de l'environnement>.yaml

# Les chemins Vault rendus, et leur environnement
helm template t millefeuille -f millefeuille/values/common-values.yaml -f <values de l'environnement>.yaml \
  | grep "^  path: '"

# Les images : toutes doivent être préfixées par le projet
helm template t millefeuille -f millefeuille/values/common-values.yaml -f <values de l'environnement>.yaml \
  | grep -E "^\s+image:"
```
