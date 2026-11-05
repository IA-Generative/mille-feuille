<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";

import type { DashboardUrgency } from "@/types/dashboard";

// Planification en deux clics : on touche une heure de l'agenda, puis on choisit
// le dossier. Le créneau d'une heure est créé aussitôt (modifiable ensuite).

const props = defineProps<{
  /** Dossiers qui n'ont pas encore de créneau, les plus urgents en premier. */
  candidates: DashboardUrgency[];
  /** Libellé de l'heure choisie (ex. « 14:00 »). */
  timeLabel: string;
}>();

const emit = defineEmits<{
  pick: [dossierId: string];
  close: [];
}>();

const search = ref("");
const input = ref<HTMLInputElement | null>(null);

const results = computed(() => {
  const q = search.value.trim().toLowerCase();
  return q ? props.candidates.filter((u) => u.dossierName.toLowerCase().includes(q)) : props.candidates;
});

const root = ref<HTMLElement | null>(null);

onMounted(() =>
  nextTick(() => {
    input.value?.focus({ preventScroll: true });
    root.value?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }),
);
</script>

<template>
  <div ref="root" class="qp" role="dialog" aria-label="Planifier un dossier" @keydown.esc.stop="emit('close')">
    <div class="qp__head">
      <span class="qp__title">Planifier à {{ timeLabel }}</span>
      <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline" @click="emit('close')">
        <VIcon name="ri-close-line" />
        <span class="fr-sr-only">Fermer</span>
      </button>
    </div>

    <input
      ref="input"
      v-model="search"
      type="search"
      class="fr-input qp__search"
      placeholder="Rechercher un dossier…"
      aria-label="Rechercher un dossier"
    />

    <ul v-if="results.length" class="qp__list">
      <li v-for="u in results" :key="u.dossierId">
        <button type="button" class="qp__item" @click="emit('pick', u.dossierId)">
          <span class="qp__name">{{ u.dossierName }}</span>
          <span class="qp__sub">{{ u.analyseName }}</span>
          <span v-if="u.level === 'overdue'" class="qp__late">En retard</span>
        </button>
      </li>
    </ul>
    <p v-else class="qp__empty">
      {{ candidates.length ? "Aucun dossier ne correspond." : "Tous vos dossiers sont déjà planifiés." }}
    </p>
  </div>
</template>

<style scoped>
.qp {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  background: var(--background-default-grey);
  box-shadow: var(--lifted-shadow);
}

.qp__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.qp__title {
  font-weight: 700;
}

.qp__list {
  display: flex;
  flex-direction: column;
  max-height: 13rem;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.qp__item {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  width: 100%;
  padding: 0.5rem 0.625rem;
  border: none;
  border-radius: 0.375rem;
  background: none;
  color: var(--text-default-grey);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.qp__item:hover,
.qp__item:focus-visible {
  background: var(--background-alt-grey-hover);
}

.qp__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qp__sub {
  flex-shrink: 0;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.qp__late {
  flex-shrink: 0;
  font-size: 0.75rem;
  color: var(--text-default-error);
}

.qp__empty {
  margin: 0;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}
</style>
