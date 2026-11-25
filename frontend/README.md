# Frontend

Application Vue 3 + [vue-dsfr](https://github.com/laruiss/vue-dsfr), construite avec Vite.

```bash
pnpm install
pnpm dev          # serveur de développement
pnpm typecheck    # vue-tsc : application + fichiers de config Node
pnpm build
```

## Tests unitaires

Outillage : [Vitest](https://vitest.dev) (environnement `jsdom`), [Vue Test Utils](https://test-utils.vuejs.org)
et [Testing Library](https://testing-library.com/docs/vue-testing-library/intro). Les tests Playwright (captures d'écran,
dossier `e2e/`) sont à part : Vitest les ignore.

### Lancer la suite

```bash
pnpm test                                  # une exécution, échoue si un test échoue (celle de la CI)
pnpm test src/utils/paginationPages.test.ts  # un seul fichier
pnpm test -t "annonce les erreurs"         # un seul test, par son nom
pnpm test:watch                            # relance au fil des modifications
pnpm test:coverage                         # + rapport dans coverage/ (texte, lcov, html)
```

La suite ne fait aucun appel réseau et ne dépend ni du fuseau horaire ni de l'heure de la machine : elle passe hors
connexion et quel que soit `TZ`.

### Organisation

- Un test se range **à côté du fichier testé** : `ErrorList.vue` → `ErrorList.test.ts`.
- `vitest.setup.ts` s'exécute avant chaque fichier de test. Il installe `vue-dsfr` exactement comme `main.ts`
  (mêmes noms de composants, mêmes icônes : aucune doublure), fait échouer tout appel `apiFetch` non prévu, nettoie le
  DOM, les horloges et le `localStorage` après chaque test.
- `vitest.global-setup.ts` fixe `TZ=UTC` pour toute la suite.
- `src/test/` contient les outils partagés :

| Fichier | Rôle |
|---|---|
| `mockApi.ts` | simule `apiFetch` |
| `mount.ts` | `mountWithDsfr` : `mount()` avec un router mémoire |
| `clock.ts` | `freezeTime`, `advance`, `FROZEN_NOW` |
| `singletons.ts` | `freshImport` : réinitialise l'état d'un composable |

### Écrire un test

Cherchez les éléments comme le ferait une personne : **par rôle et par nom accessible**, pas par classe CSS.

```ts
import { render, screen } from "@testing-library/vue";
import { describe, expect, it } from "vitest";

import ErrorList from "./ErrorList.vue";

describe("ErrorList", () => {
  it("annonce les erreurs dans une alerte", () => {
    render(ErrorList, { props: { errors: ["Nom requis"] } });
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Nom requis")).toBeTruthy();
  });
});
```

Requêtes à privilégier : `getByRole("button", { name: "Enregistrer" })`, `getByLabelText("Nom du dossier")`, puis
`getByText`. Pour vérifier une absence : `queryByRole(...)` (renvoie `null`). Les imports de Vitest (`describe`, `it`,
`expect`, `vi`) sont **explicites** : les « globals » ne sont pas activés.

Pour monter un composant qui utilise `<RouterLink>`, ou pour lire son rendu avec Vue Test Utils :

```ts
import { mountWithDsfr } from "@/test/mount";

const wrapper = mountWithDsfr(BackLink, { props: { to: "/" }, slots: { default: "Retour" } });
expect(wrapper.get("a").attributes("href")).toBe("/");
```

### Simuler `apiFetch`

`apiFetch` (`@/utils/api`) est remplacé dans tous les tests. `ApiError` et `userMessage` restent les vrais.
**Un appel non prévu fait échouer le test**, même si le code testé avale l'erreur dans un `catch` : c'est vérifié après
chaque test.

```ts
import { mockApi } from "@/test/mockApi";

mockApi.get("/api/me/stats", { dossiers_count: 2 });
mockApi.post("/api/notes", ({ body }) => ({ saved: body }));
mockApi.fail("GET", "/api/me/stats", 403, "Interdit"); // lève un vrai ApiError(403)

expect(mockApi.calls).toEqual([{ method: "POST", path: "/api/notes", body: { text: "a" } }]);
```

Le chemin peut être une chaîne exacte ou une `RegExp`. Pour tester `api.ts` lui-même, importer la vraie version :
`await vi.importActual("@/utils/api")`.

### Figer l'horloge

```ts
import { advance, freezeTime, FROZEN_NOW } from "@/test/clock";

freezeTime();             // 2026-01-15T10:00:00Z (FROZEN_NOW), ou freezeTime("2025-12-31T23:59:59Z")
await advance(5_000);     // avance de 5 s, y compris les minuteurs
```

Les minuteurs réels sont rétablis automatiquement après chaque test. `nextTick` et les micro-tâches ne sont pas
figés : Vue continue de se mettre à jour.

### Réinitialiser un singleton

Les `ref` déclarés hors de la fonction d'un composable (`useProfile`, `useTheme`…) vivent aussi longtemps que le module :
un test peut hériter de l'état du précédent. `freshImport` recharge le module avec un état neuf.

```ts
import { freshImport } from "@/test/singletons";

const { useProfile } = await freshImport(() => import("@/composables/useProfile"));
```

### Annonces `role="status"` et focus

Une annonce vocale s'ajoute au DOM **après** le rendu suivant : attendre `nextTick` avant de la chercher.

```ts
import { nextTick } from "vue";

await button.trigger("click");
await nextTick();
expect(screen.getByRole("status").textContent).toContain("Enregistré");
```

Pour le focus : `expect(document.activeElement).toBe(screen.getByRole("dialog"))` (le composant doit être monté avec
`attachTo: document.body` sous Vue Test Utils).

### Règles d'équipe

1. **Bug : le test d'abord.** Un test qui échoue et reproduit le bug, puis la correction.
2. **Nouvelle fonction de `utils/` ou nouveau composable : livrée avec ses tests.**
3. **Composant portant une règle `aria-*`, une annonce ou un déplacement du focus : livré avec un test
   d'accessibilité** (rôle, nom accessible, annonce, focus).

### Couverture

`pnpm test:coverage` échoue si la couverture globale passe sous les seuils de `vitest.config.ts`
(`coverage.thresholds`).

| | Instructions | Branches | Fonctions | Lignes |
|---|---|---|---|---|
| Valeur de départ mesurée | 0,21 % | 0,04 % | 0,24 % | 0,24 % |
| Seuil fixé (juste en dessous) | 0,2 % | 0,03 % | 0,2 % | 0,2 % |

Cette valeur est basse, c'est normal : seuls les outils de test et deux composants témoins sont couverts.

**Règle de relèvement :** à chaque sous-issue de tests unitaires, lancer `pnpm test:coverage`, puis relever chaque seuil
**au plus près du chiffre mesuré** (en arrondissant vers le bas). Un seuil ne baisse jamais.

Le rapport est aussi publié en artefact (`frontend-coverage`) par le job « Tests frontend » de la CI.
