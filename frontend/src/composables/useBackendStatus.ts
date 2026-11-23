import { onMounted, onUnmounted, ref } from "vue";

import { API_BASE_URL } from "@/utils/api";

/** `healthy` : tout répond ; `unhealthy` : le backend répond mais une dépendance est en panne ;
 * `unreachable` : le backend ne répond pas ; `unknown` : pas encore de réponse. */
export type BackendHealth = "unknown" | "healthy" | "unhealthy" | "unreachable";

const REFRESH_MS = 30_000;

/** Version et santé du backend (routes publiques `/api/version` et `/api/health/ready`), relues périodiquement. */
export function useBackendStatus() {
  const version = ref("");
  const health = ref<BackendHealth>("unknown");
  let timer: ReturnType<typeof setInterval> | undefined;

  const refresh = async () => {
    // `apiFetch` lève sur un 503 : on lit la réponse à la main pour distinguer « en panne » de « injoignable ».
    try {
      const ready = await fetch(`${API_BASE_URL}/api/health/ready`);
      health.value = ready.ok ? "healthy" : ready.status === 503 ? "unhealthy" : "unreachable";
    } catch {
      health.value = "unreachable";
    }
    if (health.value === "unreachable") return;
    try {
      const response = await fetch(`${API_BASE_URL}/api/version`);
      if (response.ok) version.value = (await response.json()).version ?? "";
    } catch {
      // La version reste celle déjà connue : l'indicateur de santé suffit à signaler le problème.
    }
  };

  onMounted(() => {
    void refresh();
    timer = setInterval(refresh, REFRESH_MS);
  });
  onUnmounted(() => clearInterval(timer));

  return { version, health };
}
