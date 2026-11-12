/**
 * Composable de suivi des tâches utilisateur (issue #62).
 *
 * Récupère les tâches de l'utilisateur courant via GET /api/me/tasks et
 * rafraîchit périodiquement (polling) tant qu'au moins une tâche est en
 * cours (pending ou running). Le polling s'arrête automatiquement quand
 * toutes les tâches sont terminées (success / failure) ou quand le
 * composant est démonté.
 *
 * Un singleton d'état est partagé entre tous les consommateurs (bouton
 * flottant + drawer) pour éviter les requêtes multiples.
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { apiFetch, userMessage } from "@/utils/api";
import type { UserTask, UserTaskStatus } from "@/types/userTask";

const POLL_INTERVAL_MS = 5_000;

// ── État partagé (singleton) ──────────────────────────────────────────────

const tasks = ref<UserTask[]>([]);
const loading = ref(false);
const lastError = ref<string | null>(null);
let pollTimer: ReturnType<typeof setInterval> | null = null;
let activeConsumers = 0;

// ── Getters réactifs ──────────────────────────────────────────────────────

const activeTasks = computed(() =>
  tasks.value.filter((t) => t.status === "pending" || t.status === "running"),
);

const hasActiveTasks = computed(() => activeTasks.value.length > 0);

const activeCount = computed(() => activeTasks.value.length);

const failedTasks = computed(() => tasks.value.filter((t) => t.status === "failure"));

// ── Logique interne ───────────────────────────────────────────────────────

async function fetchTasks(status?: UserTaskStatus) {
  loading.value = true;
  try {
    const query = status ? `?status=${status}` : "";
    tasks.value = await apiFetch<UserTask[]>(`/api/me/tasks${query}`);
    lastError.value = null;
  } catch (err) {
    lastError.value = userMessage(err, "Impossible de charger les tâches.");
  } finally {
    loading.value = false;
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    // On ne poll que s'il y a des tâches actives, sinon on arrête.
    if (hasActiveTasks.value) {
      fetchTasks();
    } else {
      stopPolling();
    }
  }, POLL_INTERVAL_MS);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// ── API publique ──────────────────────────────────────────────────────────

export function useUserTasks() {
  onMounted(async () => {
    activeConsumers++;
    // Premier chargement immédiat si pas déjà chargé.
    if (tasks.value.length === 0 && !loading.value) {
      await fetchTasks();
    }
    // Démarre le polling s'il y a des tâches actives.
    if (hasActiveTasks.value) {
      startPolling();
    }
  });

  onBeforeUnmount(() => {
    activeConsumers--;
    if (activeConsumers <= 0) {
      stopPolling();
      activeConsumers = 0;
    }
  });

  return {
    tasks,
    activeTasks,
    hasActiveTasks,
    activeCount,
    failedTasks,
    loading: computed(() => loading.value),
    lastError: computed(() => lastError.value),
    fetchTasks,
    /** Force un rafraîchissement immédiat et relance le polling si besoin. */
    refresh: async () => {
      await fetchTasks();
      if (hasActiveTasks.value) startPolling();
    },
  };
}
