import VueDsfr from "@gouvminint/vue-dsfr";
import { cleanup } from "@testing-library/vue";
import { config } from "@vue/test-utils";
import { afterEach, beforeEach, vi } from "vitest";

// Identique à main.ts : mêmes noms (DsfrButton, DsfrInput, DsfrAlert, VIcon…), mêmes icônes. Zéro doublure.
config.global.plugins = [VueDsfr];

// Remplace apiFetch dans tous les fichiers de test. ApiError et userMessage restent les vrais.
// Pour tester api.ts lui-même : await vi.importActual("@/utils/api").
vi.mock("@/utils/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/utils/api")>();
  const { dispatch } = await import("./src/test/mockApi");
  return { ...actual, apiFetch: dispatch };
});

// jsdom n'a pas matchMedia ; useTheme l'appelle à l'import.
beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
});

afterEach(async () => {
  // Testing Library ne se nettoie seul que si les « globals » de Vitest sont actifs (ce qui n'est pas le cas ici) :
  // sans ça, le DOM d'un test reste visible pour le suivant.
  cleanup();
  const { mockApi } = await import("./src/test/mockApi");
  const unexpected = mockApi.assertNoUnexpectedCalls; // lu avant reset
  try { unexpected(); } finally { mockApi.reset(); }
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
  document.documentElement.removeAttribute("data-fr-theme");
  document.documentElement.removeAttribute("data-fr-scheme");
});
