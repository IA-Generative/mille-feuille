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

#### À quoi ça sert

La **couverture** indique quelle part du code de l'application est *exécutée* par les tests. Elle sert à deux choses :

1. **Voir ce qui reste à tester** : le rapport montre, fichier par fichier et ligne par ligne, le code qu'aucun test
   n'exécute.
2. **Empêcher qu'elle baisse sans que personne ne le voie** : un **seuil** fait échouer la commande
   `pnpm test:coverage` si la couverture globale passe en dessous. Pour l'instant, cette vérification se fait **en
   local** : la CI ne lance pas encore la couverture (voir [Dans la CI](#dans-la-ci)).

Elle ne dit **pas** si le code est correct : une ligne est « couverte » dès qu'un test l'exécute, même sans la
vérifier (un test sans `expect` couvre du code sans rien prouver). Elle complète la relecture et les
[règles d'équipe](#règles-déquipe), elle ne les remplace pas.

#### Ce qu'il faut faire au quotidien

| Situation | Commande |
|---|---|
| Vérifier que mes tests passent, trouver pourquoi l'un échoue | `pnpm test` (ou `pnpm test:watch`) |
| Voir ce que mes tests couvrent, vérifier les seuils avant une PR (la CI ne le fait pas encore) | `pnpm test:coverage` |

`pnpm test` ne produit aucun rapport et ne regarde pas les seuils. `pnpm test:coverage` lance **les mêmes tests**, plus
la mesure : elle n'aide pas à comprendre un test qui échoue (la sortie de `pnpm test` le fait déjà).

#### Ce qui est mesuré

- Tous les fichiers `src/**/*.ts` et `src/**/*.vue`, **y compris ceux qu'aucun test n'importe** (ils comptent pour 0 %).
  C'est pourquoi le chiffre de départ est très bas.
- Sont exclus : `src/test/**` (les outils de test), les fichiers `*.test.ts`, `src/main.ts` et les `*.d.ts`.
- Les seuils sont **globaux** (une valeur pour l'ensemble de `src/`), pas par fichier.

#### Lire le résultat

`pnpm test:coverage` affiche un tableau dans le terminal et crée le dossier `coverage/` :

| Colonne ou fichier | Signification |
|---|---|
| `% Stmts` (instructions) | part des instructions exécutées |
| `% Branch` (branches) | part des chemins exécutés : chaque `if` / `else`, `? :`, `&&`, `??`… compte pour plusieurs |
| `% Funcs` (fonctions) | part des fonctions appelées au moins une fois |
| `% Lines` (lignes) | part des lignes exécutées |
| `Uncovered Line #s` | numéros des lignes jamais exécutées |
| `coverage/index.html` | le même rapport, à ouvrir dans le navigateur : on y clique fichier par fichier, les lignes non exécutées sont en rouge |
| `coverage/lcov.info` | le même rapport en format standard, pour des outils externes |

Le dossier `coverage/` est **généré** à chaque lancement et ignoré par git : on ne le commite pas, et on peut le
supprimer sans conséquence.

#### Seuils actuels

`pnpm test:coverage` se termine en erreur (code 1) quand une valeur passe sous son seuil, avec un message de la forme
`Coverage for lines (x%) does not meet global threshold (y%)`.

| | Instructions | Branches | Fonctions | Lignes |
|---|---|---|---|---|
| Valeur de départ mesurée | 0,21 % | 0,04 % | 0,24 % | 0,24 % |
| Seuil fixé (juste en dessous) | 0,2 % | 0,03 % | 0,2 % | 0,2 % |

Ces valeurs sont basses, c'est normal : seuls les outils de test et deux composants témoins sont couverts. Elles
montent au fil des sous-issues de tests unitaires.

**Règle de relèvement :** à chaque sous-issue de tests unitaires, lancer `pnpm test:coverage`, puis relever chaque seuil
**au plus près du chiffre mesuré** (en arrondissant vers le bas). Exemple : si la mesure donne 12,7 % de lignes, le
seuil passe à 12. Un seuil ne baisse jamais ; si une PR fait légitimement baisser la couverture (suppression de code
testé, par exemple), en discuter dans la PR avant de toucher au seuil.

#### Où c'est configuré

| Fichier | Rôle |
|---|---|
| `vitest.config.ts`, bloc `coverage` | fichiers mesurés, formats de rapport, **seuils** |
| `package.json` | script `test:coverage` (sans l'option `--coverage`, la mesure n'a pas lieu) et dépendance `@vitest/coverage-v8` |
| `.github/workflows/unit-tests.yml`, job `unit-tests-frontend` | lance `pnpm run test` (sans couverture pour l'instant) |
| `.gitignore`, `frontend/.dockerignore` | empêchent de commiter `coverage/` ou de l'envoyer dans le build Docker |

#### Dans la CI

Le job « Unit Tests / Frontend » lance `pnpm run test` quand `frontend/**` change. Il échoue si un test échoue, et
bloque alors la fusion.

**La couverture n'est pas encore mesurée en CI** : aucun seuil n'y est vérifié et aucun rapport n'y est publié. Elle
sera ajoutée à la CI plus tard, une fois que les sous-issues de tests auront fait monter la couverture. D'ici là :

- les seuils ne se vérifient qu'en local : lancer `pnpm test:coverage` avant d'ouvrir une PR de tests ;
- la couverture sert déjà à voir ce qui reste à tester et à appliquer la règle de relèvement ci-dessus.

Quand elle sera ajoutée, le job lancera `pnpm run test:coverage` à la place de `pnpm run test`, et publiera le dossier
`coverage/` en artefact.
