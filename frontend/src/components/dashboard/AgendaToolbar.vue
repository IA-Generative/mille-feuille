<script setup lang="ts">
// Barre d'outils de l'agenda : choix de la vue + bouton de recherche.
export type AgendaView = "day" | "month" | "list";

const view = defineModel<AgendaView>("view", { required: true });
const filtersOpen = defineModel<boolean>("filtersOpen", { required: true });
defineProps<{ filtersActive: boolean }>();

const VIEWS: { value: AgendaView; label: string }[] = [
  { value: "day", label: "Jour" },
  { value: "month", label: "Mois" },
  { value: "list", label: "Liste" },
];
</script>

<template>
  <div class="bar">
    <div class="bar__segmented" role="group" aria-label="Affichage">
      <button
        v-for="v in VIEWS"
        :key="v.value"
        type="button"
        class="bar__seg"
        :class="{ 'bar__seg--on': view === v.value }"
        :aria-pressed="view === v.value"
        @click="view = v.value"
      >
        {{ v.label }}
      </button>
    </div>
    <button
      type="button"
      class="bar__search"
      :class="{ 'bar__search--on': filtersOpen || filtersActive }"
      :aria-expanded="filtersOpen"
      aria-controls="dash-filters"
      @click="filtersOpen = !filtersOpen"
    >
      <VIcon name="ri-search-line" /> Rechercher
    </button>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.bar__segmented {
  display: inline-flex;
  padding: 0.125rem;
  border-radius: 0.625rem;
  background: var(--background-alt-grey);
}

.bar__seg {
  padding: 0.25rem 1rem;
  border: none;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--text-default-grey);
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}

.bar__seg--on {
  background: var(--background-default-grey);
  box-shadow: var(--raised-shadow);
  font-weight: 600;
}

.bar__search {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.5rem;
  border: none;
  background: none;
  color: var(--text-action-high-blue-france);
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}

.bar__search--on {
  font-weight: 700;
}
</style>
