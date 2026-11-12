import { ref } from "vue";

import { apiFetch, userMessage } from "@/utils/api";
import type { AdminStats } from "@/types/admin";

/** Statistiques globales de la plateforme (page Administration). */
export function useAdminStats() {
  const stats = ref<AdminStats | null>(null);
  const loading = ref(false);
  const error = ref("");

  const fetchStats = async () => {
    loading.value = true;
    error.value = "";
    try {
      stats.value = await apiFetch<AdminStats>("/api/admin/stats");
    } catch (e) {
      error.value = userMessage(e, "Erreur lors du chargement des statistiques.");
      stats.value = null;
    } finally {
      loading.value = false;
    }
  };

  return { stats, loading, error, fetchStats };
}
