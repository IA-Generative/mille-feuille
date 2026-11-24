<script setup lang="ts">
import { computed, ref, watch } from "vue";

import UrgencyRow from "@/components/dashboard/UrgencyRow.vue";
import PagerNav from "@/components/PagerNav.vue";
import type { DashboardUrgency } from "@/types/dashboard";
import type { SlotDraft } from "@/types/schedule";
import { dayLabel, dayOffset, formatDue } from "@/utils/dates";

// Vue « Liste » : urgences triées par échéance, groupées par jour, paginées.
const props = defineProps<{
  /** Urgences déjà filtrées et triées. */
  urgencies: DashboardUrgency[];
  /** Vrai s'il n'existe aucune urgence, filtres mis à part. */
  noUrgencyAtAll: boolean;
}>();
defineEmits<{ schedule: [dossierId: string, slot: SlotDraft | null] }>();

const PAGE_SIZE = 8;
const page = ref(1);
watch(() => props.urgencies, () => (page.value = 1));

const pageCount = computed(() => Math.max(1, Math.ceil(props.urgencies.length / PAGE_SIZE)));

const groups = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE;
  const out: { label: string; overdue: boolean; items: DashboardUrgency[] }[] = [];
  for (const u of props.urgencies.slice(start, start + PAGE_SIZE)) {
    const label = dayLabel(u.dueAt!); // la liste ne reçoit que des urgences, toutes datées
    const last = out[out.length - 1];
    if (last && last.label === label) last.items.push(u);
    else out.push({ label, overdue: dayOffset(u.dueAt!) < 0, items: [u] });
  }
  return out;
});
</script>

<template>
  <section aria-label="Urgences">
    <p v-if="noUrgencyAtAll" class="list__empty">Aucune urgence.</p>
    <p v-else-if="urgencies.length === 0" class="list__empty">Aucun dossier ne correspond à ces critères.</p>
    <template v-else>
      <section v-for="g in groups" :key="g.label" class="list__day">
        <h2 class="list__day-title" :class="{ 'list__day-title--overdue': g.overdue }">{{ g.label }}</h2>
        <ul class="list__items">
          <li v-for="u in g.items" :key="u.dossierId">
            <UrgencyRow :urgency="u" :meta="formatDue(u.dueAt!)" @schedule="(id, slot) => $emit('schedule', id, slot)" />
          </li>
        </ul>
      </section>
      <PagerNav v-model:page="page" :page-count="pageCount" class="list__pagination" />
    </template>
  </section>
</template>

<style scoped>
.list__empty {
  color: var(--text-mention-grey);
}

.list__day {
  margin-top: 1.25rem;
}

.list__day-title {
  margin: 0 0 0.25rem;
  font-size: 0.875rem;
  font-weight: 700;
  color: var(--text-mention-grey);
}

.list__day-title::first-letter {
  text-transform: uppercase;
}

.list__day-title--overdue {
  color: var(--text-default-error);
}

.list__items {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.list__pagination {
  margin-top: 1rem;
}
</style>
