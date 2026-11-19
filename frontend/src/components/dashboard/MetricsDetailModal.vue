<script setup lang="ts">
import { computed } from "vue";

import AppModal from "@/components/AppModal.vue";
import BarList from "@/components/dashboard/BarList.vue";
import MetricCard from "@/components/dashboard/MetricCard.vue";
import type { DashboardStats, DashboardStatusCount, DashboardUrgency } from "@/types/dashboard";
import { occurrenceStarts } from "@/utils/recurrence";

// Détail des indicateurs, sur un ton volontairement neutre : des repères,
// pas des objectifs. Pour ajouter une statistique : un MetricCard ou une
// BarList dans la section qui lui correspond.
const props = defineProps<{
  urgencies: DashboardUrgency[];
  stats: DashboardStats;
  statusCounts: DashboardStatusCount[];
}>();
const emit = defineEmits<{ close: [] }>();

const inProgress = computed(() => Math.max(0, props.stats.totalDossiers - props.stats.closedDossiers));
const planned = computed(() => props.urgencies.filter((u) => u.plannedStart).length);

const weekLabels = ["Il y a 3 semaines", "Il y a 2 semaines", "Semaine dernière", "Cette semaine"];
const rhythm = computed(() => props.stats.weeklyClosed.map((value, i) => ({ label: weekLabels[i] ?? `Semaine ${i + 1}`, value })));

// Chaque ligne renvoie vers le suivi, filtré sur mes dossiers (#186).
const byStatus = computed(() =>
  props.statusCounts.map((s) => ({
    label: s.label,
    value: s.count,
    to: { path: "/suivi", query: { assignee: "me", status: s.statusId } },
  })),
);

const byAnalyse = computed(() => {
  const counts = new Map<string, { id: string; value: number }>();
  for (const u of props.urgencies) {
    const entry = counts.get(u.analyseName) ?? { id: u.analyseId, value: 0 };
    counts.set(u.analyseName, { id: entry.id, value: entry.value + 1 });
  }
  return [...counts]
    .map(([label, { id, value }]) => ({ label, value, to: { path: "/suivi", query: { assignee: "me", analyse: id } } }))
    .sort((a, b) => b.value - a.value);
});

/** Créneaux (récurrents compris) entre aujourd'hui et dans `days` jours. */
function slotsWithin(days: number) {
  const from = new Date();
  from.setHours(0, 0, 0, 0);
  const to = new Date(from);
  to.setDate(to.getDate() + days);
  to.setHours(23, 59, 59, 999);
  return props.urgencies.flatMap((u) => {
    if (!u.plannedStart || !u.plannedEnd) return [];
    const duration = new Date(u.plannedEnd).getTime() - new Date(u.plannedStart).getTime();
    return occurrenceStarts(new Date(u.plannedStart), u.recurrence, from, to).map(() => duration);
  });
}

function formatDuration(ms: number) {
  const minutes = Math.round(ms / 60_000);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${String(m).padStart(2, "0")}`;
}

const today = computed(() => slotsWithin(0));
const week = computed(() => slotsWithin(6));

const weekHint = computed(() => `${props.stats.completedPrevWeek} la semaine dernière`);
</script>

<template>
  <AppModal
    :opened="true"
    title="Mes indicateurs"
    icon="ri-bar-chart-2-line"
    size="lg"
    :actions="[{ label: 'Fermer', onClick: () => emit('close') }]"
    @close="emit('close')"
  >
    <section class="md__section" aria-labelledby="md-glance">
      <h3 id="md-glance" class="md__title">En un coup d'œil</h3>
      <div class="md__grid">
        <MetricCard label="Dossiers" :value="stats.totalDossiers" />
        <MetricCard label="En cours" :value="inProgress" />
        <MetricCard label="Planifiés" :value="planned" />
        <MetricCard label="Clôturés" :value="stats.closedDossiers" tone="success" />
      </div>
    </section>

    <section class="md__section" aria-labelledby="md-rhythm">
      <h3 id="md-rhythm" class="md__title">À votre rythme</h3>
      <div class="md__grid">
        <MetricCard label="Traités cette semaine" :value="stats.completedThisWeek" :hint="weekHint" tone="success" />
        <MetricCard
          label="Délai moyen"
          :value="`${stats.avgProcessingDays.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} j`"
          hint="De l'arrivée à la clôture"
        />
        <MetricCard label="Clos dans les temps" :value="`${Math.round(stats.onTimeRate * 100)} %`" hint="Des dossiers clôturés" />
      </div>
      <p class="md__sub">Dossiers clôturés par semaine</p>
      <BarList :items="rhythm" />
    </section>

    <section v-if="byStatus.length" class="md__section" aria-labelledby="md-status">
      <h3 id="md-status" class="md__title">Où en sont vos dossiers</h3>
      <BarList :items="byStatus" />
    </section>

    <section v-if="byAnalyse.length" class="md__section" aria-labelledby="md-analyse">
      <h3 id="md-analyse" class="md__title">Par analyse</h3>
      <BarList :items="byAnalyse" />
    </section>

    <section class="md__section" aria-labelledby="md-agenda">
      <h3 id="md-agenda" class="md__title">Votre agenda</h3>
      <div class="md__grid">
        <MetricCard label="Aujourd'hui" :value="formatDuration(today.reduce((a, b) => a + b, 0))" :hint="`${today.length} créneau${today.length > 1 ? 'x' : ''}`" />
        <MetricCard label="7 prochains jours" :value="formatDuration(week.reduce((a, b) => a + b, 0))" :hint="`${week.length} créneau${week.length > 1 ? 'x' : ''}`" />
      </div>
    </section>
  </AppModal>
</template>

<style scoped>
.md__section + .md__section {
  margin-top: 1.5rem;
}

.md__title {
  margin: 0 0 0.5rem;
  font-size: 1rem;
}

.md__sub {
  margin: 1rem 0 0.5rem;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.md__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.5rem;
}
</style>
