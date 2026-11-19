import { computed, ref, type Ref } from "vue";

import type { DashboardUrgency } from "@/types/dashboard";
import { dayOffset } from "@/utils/dates";

export type DueFilter = "all" | "overdue" | "today" | "week" | "later";

export const DUE_FILTER_OPTIONS: { value: DueFilter; text: string }[] = [
  { value: "all", text: "Toutes les échéances" },
  { value: "overdue", text: "En retard" },
  { value: "today", text: "Aujourd'hui" },
  { value: "week", text: "Cette semaine" },
  { value: "later", text: "Plus tard" },
];

export function matchesDue(u: DashboardUrgency, filter: DueFilter): boolean {
  if (!u.dueAt) return filter === "all";
  const offset = dayOffset(u.dueAt);
  switch (filter) {
    case "overdue":
      return offset < 0;
    case "today":
      return offset === 0;
    case "week":
      return offset >= 0 && offset <= 7;
    case "later":
      return offset > 7;
    default:
      return true;
  }
}

/**
 * Recherche et filtres des urgences.
 * `searched` (texte + analyse) sert à toutes les vues ; `filtered` y ajoute
 * le filtre d'échéance, propre à la vue liste.
 */
export function useUrgencyFilters(urgencies: Ref<DashboardUrgency[]>, isListView: Ref<boolean>) {
  const search = ref("");
  const dueFilter = ref<DueFilter>("all");
  const analyseFilter = ref("");

  const sorted = computed(() =>
    [...urgencies.value].sort(
      (a, b) => (a.dueAt ? new Date(a.dueAt).getTime() : Infinity) - (b.dueAt ? new Date(b.dueAt).getTime() : Infinity),
    ),
  );

  const analyseOptions = computed(() => [
    { value: "", text: "Toutes les analyses" },
    ...[...new Set(sorted.value.map((u) => u.analyseName))].sort().map((name) => ({ value: name, text: name })),
  ]);

  const searched = computed(() => {
    const query = search.value.trim().toLowerCase();
    return sorted.value.filter(
      (u) =>
        (!analyseFilter.value || u.analyseName === analyseFilter.value) &&
        (!query || `${u.dossierName} ${u.analyseName} ${u.statusLabel}`.toLowerCase().includes(query)),
    );
  });

  const filtered = computed(() => searched.value.filter((u) => matchesDue(u, dueFilter.value)));

  const hasActiveFilters = computed(
    () =>
      search.value.trim() !== "" ||
      analyseFilter.value !== "" ||
      (isListView.value && dueFilter.value !== "all"),
  );

  function reset() {
    search.value = "";
    dueFilter.value = "all";
    analyseFilter.value = "";
  }

  return { search, dueFilter, analyseFilter, sorted, analyseOptions, searched, filtered, hasActiveFilters, reset };
}
