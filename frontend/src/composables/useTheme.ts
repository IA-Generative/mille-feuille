import { ref } from "vue";

import { apiFetch } from "@/utils/api";
import type { Theme, UserPreferences } from "@/types/profile";

// Gestion du thème DSFR (clair/sombre/système) via l'attribut `data-fr-theme`
// sur <html>. La préférence est persistée côté backend (table
// user_preferences) ET en localStorage (pour application immédiate au
// chargement, avant que l'API ne réponde - évite le flash de thème).

const STORAGE_KEY = "mille-feuille-theme";
const theme = ref<Theme>("system");
let initialized = false;

const darkQuery = window.matchMedia("(prefers-color-scheme: dark)")

/** DSFR ne connaît que « light » et « dark » : « system » est résolu ici d'après l'appareil. */
function resolveTheme(value: Theme): "light" | "dark" {
  if (value === "system") return darkQuery.matches ? "dark" : "light";
  return value
}

function applyThemeToDom(value: Theme) {
  document.documentElement.dataset.frScheme = value; // choix de la personne (convention DSFR)
  document.documentElement.dataset.frTheme = resolveTheme(value); // thème réellement appliqué
}

// Si l'appareil bascule (coucher du soleil, réglage système) alors que « Système » est choisi.
darkQuery.addEventListener("change", () => {
  if (theme.value === "system") applyThemeToDom("system");
});

/** Applique le thème au chargement de l'app, avant tout rendu, pour éviter
 *  le flash. Lit localStorage en premier (synchrone), puis tente de
 *  synchroniser avec le backend si l'utilisateur est connecté. */
export function initTheme() {
  if (initialized) return;
  initialized = true;

  // 1. Application immédiate depuis localStorage (synchrone, pas de flash)
  const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
  if (stored && ["light", "dark", "system"].includes(stored)) {
    theme.value = stored;
  }
  applyThemeToDom(theme.value);

  // 2. Synchronisation avec le backend (si connecté) - silencieux si 401
  syncThemeFromBackend();
}

async function syncThemeFromBackend() {
  try {
    const prefs = await apiFetch<UserPreferences>("/api/me/preferences");
    theme.value = prefs.theme;
    applyThemeToDom(theme.value);
    localStorage.setItem(STORAGE_KEY, prefs.theme);
  } catch {
    // Non connecté ou erreur réseau : on garde le thème local
  }
}

export function useTheme() {
  const setTheme = async (value: Theme) => {
    theme.value = value;
    applyThemeToDom(value);
    localStorage.setItem(STORAGE_KEY, value);

    // Persistance backend (best-effort, silencieux si non connecté)
    try {
      await apiFetch<UserPreferences>("/api/me/preferences", {
        method: "PATCH",
        body: JSON.stringify({ theme: value }),
      });
    } catch {
      // Non connecté : la préférence reste en localStorage
    }
  };

  return {
    theme,
    setTheme,
  };
}
