import { ref } from "vue";

import type { DashboardActivity, DashboardData, DashboardUrgency } from "@/types/dashboard";
import type { SlotDraft } from "@/types/schedule";
import { apiFetch, userMessage } from "@/utils/api";

// Tableau de bord branché sur l'API (issue #174) : `GET /api/dashboard` donne les indicateurs, les urgences
// (échéance proche ou dépassée selon les seuils de l'analyse), mes dossiers par statut, les dossiers non affectés
// (administrateurs) et l'activité récente ; chaque urgence porte mon créneau de traitement, s'il y en a un
// (`PUT` / `DELETE /api/dossiers/{id}/slot`, privés). Les rappels de ces créneaux sont des notifications du serveur
// (useNotifications, #219).
// Pour valider les états de l'interface, ajouter `?mock=` à l'URL : `empty` (états vides), `error` (erreur),
// `loading` (chargement sans fin), `nounassigned` (sans droit « non affectés »).

function mapUrgency(api: any): DashboardUrgency {
  const slot = api.slot;
  return {
    dossierId: api.dossier_id,
    dossierName: api.dossier_name,
    analyseId: api.analyse_id,
    analyseName: api.analyse_name,
    statusLabel: api.status_label ?? "",
    dueAt: api.due_at ?? undefined,
    level: api.level,
    plannedStart: slot?.start,
    plannedEnd: slot?.end,
    recurrence: slot?.recurrence ?? undefined,
    reminders: slot?.reminders,
  };
}

/** Dossier ouvert non urgent : même forme qu'une urgence, au niveau « ok ». */
function mapOther(api: any): DashboardUrgency {
  return mapUrgency({ ...api, level: "ok" });
}

function mapActivity(api: any): DashboardActivity {
  return {
    id: api.id,
    kind: api.kind,
    dossierId: api.dossier_id,
    dossierName: api.dossier_name,
    message: api.message,
    at: api.at,
  };
}

/** Les statuts sont propres à chaque analyse : dès que plusieurs analyses sont concernées, le libellé nomme la sienne. */
function mapStatusCounts(api: any[]) {
  const several = new Set(api.map((s) => s.analyse_name)).size > 1;
  return api.map((s) => ({
    statusId: s.status_id,
    label: several ? `${s.label} · ${s.analyse_name}` : s.label,
    count: s.count,
  }));
}

function mapDashboard(api: any): DashboardData {
  return {
    stats: {
      totalDossiers: api.stats.total_dossiers,
      closedDossiers: api.stats.closed_dossiers,
      completedThisWeek: api.stats.completed_this_week,
      completedPrevWeek: api.stats.completed_prev_week,
      weeklyClosed: api.stats.weekly_closed,
      avgProcessingDays: api.stats.avg_processing_days,
      onTimeRate: api.stats.on_time_rate,
    },
    urgencies: api.urgencies.map(mapUrgency),
    others: (api.others ?? []).map(mapOther),
    statusCounts: mapStatusCounts(api.status_counts),
    unassigned:
      api.unassigned === null
        ? null
        : api.unassigned.map((u: any) => ({
            dossierId: u.dossier_id,
            dossierName: u.dossier_name,
            analyseName: u.analyse_name,
            createdAt: u.created_at,
          })),
    activity: api.activity.map(mapActivity),
  };
}

const emptyDashboard = (): DashboardData => ({
  stats: {
    totalDossiers: 0,
    closedDossiers: 0,
    completedThisWeek: 0,
    completedPrevWeek: 0,
    weeklyClosed: [0, 0, 0, 0],
    avgProcessingDays: 0,
    onTimeRate: 0,
  },
  urgencies: [],
  others: [],
  statusCounts: [],
  unassigned: [],
  activity: [],
});

const mockScenario = () => new URLSearchParams(window.location.search).get("mock");

export function useDashboard() {
  const data = ref<DashboardData | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  /** Recharge sans l'état « Chargement » : l'agenda reste affiché. */
  async function refreshDashboard() {
    if (mockScenario()) return;
    data.value = mapDashboard(await apiFetch<any>("/api/dashboard"));
  }

  async function fetchDashboard() {
    loading.value = true;
    error.value = null;
    const scenario = mockScenario();
    try {
      if (scenario === "loading") {
        await new Promise(() => {}); // chargement sans fin, pour juger l'état
      } else if (scenario === "error") {
        throw new Error("Impossible de charger le tableau de bord.");
      } else if (scenario === "empty") {
        data.value = emptyDashboard();
      } else {
        const loaded = mapDashboard(await apiFetch<any>("/api/dashboard"));
        if (scenario === "nounassigned") loaded.unassigned = null;
        data.value = loaded;
      }
    } catch (e) {
      error.value = userMessage(e, "Impossible de charger le tableau de bord.");
    } finally {
      loading.value = false;
    }
  }

  /**
   * Planifie (ou retire, avec `null`) mon créneau de traitement sur un dossier, côté serveur. En cas d'échec
   * l'erreur est relancée et l'agenda reste tel qu'il était.
   */
  async function setSchedule(dossierId: string, slot: SlotDraft | null) {
    const target = [...(data.value?.urgencies ?? []), ...(data.value?.others ?? [])].find((u) => u.dossierId === dossierId);
    if (!target) {
      // Dossier qui n'est pas encore dans mon agenda (choisi parmi tous les dossiers) : le serveur le renvoie ensuite.
      if (!slot) return;
      await apiFetch<any>(`/api/dossiers/${dossierId}/slot`, { method: "PUT", body: JSON.stringify(slot) });
      await refreshDashboard();
      return;
    }
    if (slot) {
      const saved = await apiFetch<any>(`/api/dossiers/${dossierId}/slot`, { method: "PUT", body: JSON.stringify(slot) });
      target.plannedStart = saved.start;
      target.plannedEnd = saved.end;
      target.recurrence = saved.recurrence ?? undefined;
      target.reminders = saved.reminders;
    } else {
      await apiFetch<void>(`/api/dossiers/${dossierId}/slot`, { method: "DELETE" });
      target.plannedStart = target.plannedEnd = target.recurrence = target.reminders = undefined;
      // Un dossier qui n'était là que pour son créneau quitte l'agenda.
      if (data.value) data.value.others = data.value.others.filter((u) => u.dossierId !== dossierId);
    }
  }

  return { data, loading, error, fetchDashboard, setSchedule };
}
