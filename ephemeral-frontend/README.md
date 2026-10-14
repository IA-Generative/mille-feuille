# UneFeuille (ephemeral-frontend)

Version restreinte de MilleFeuille pour l'API éphémère : on dépose un document, on le classe ou on en extrait des
informations, sans créer d'analyse. Vue 3 et DSFR.

## Configuration au démarrage du conteneur

L'image est **la même pour tous les environnements** : son adresse d'API et son lien vers MilleFeuille ne sont pas figés
au build. Au démarrage, `docker/40-runtime-config.sh` écrit `/tmp/config.js` à partir de variables d'environnement, nginx
le sert à `/config.js` (sans cache) et l'interface le lit au chargement (`src/config.ts`).

| Variable | Rôle |
|---|---|
| `API_BASE_URL` | Adresse du backend. Vide : même hôte que ce frontend. **À renseigner avec l'adresse de MilleFeuille quand ce frontend a un autre hôte** : le cookie de session est posé là où le backend reçoit la connexion (`BACKEND_PUBLIC_URL`), il faut donc appeler l'API depuis cet hôte. |
| `MILLEFEUILLE_URL` | Adresse du frontend MilleFeuille, pour le lien « Accéder à MilleFeuille ». Vide : pas de lien. |

Exemple (Helm, dans les values de l'environnement) :

```yaml
ephemeral_frontend:
  env:
    API_BASE_URL: "https://millefeuille-dev.example.com"
    MILLEFEUILLE_URL: "https://millefeuille-dev.example.com"
backend:
  env:
    EPHEMERAL_FRONTEND_URL: "https://unefeuille-dev.example.com"   # CORS et redirection après la connexion
```

Pourquoi l'API de MilleFeuille et pas celle de l'hôte d'UneFeuille : la connexion Keycloak revient toujours sur l'hôte de
`BACKEND_PUBLIC_URL`, qui y pose le cookie de session. Deux sous-domaines d'un même domaine sont « du même site » : le
navigateur envoie ce cookie aux appels d'UneFeuille vers MilleFeuille (le CORS est ouvert par `EPHEMERAL_FRONTEND_URL`).

En développement (`pnpm dev`), `public/config.js` est vide et les variables `VITE_API_BASE_URL` et `VITE_MILLEFEUILLE_URL`
servent de repli. Avec docker compose, les deux variables ci-dessus sont posées sur le service `ephemeral-frontend`.

## Développement

```bash
pnpm install
pnpm dev          # http://localhost:5174
pnpm typecheck
pnpm build
```
