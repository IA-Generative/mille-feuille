<script setup lang="ts">
import { EVENT_CATEGORIES, type DossierEventActor, type EventCategory } from "@/types/dossierEvent";

// Filtres de l'historique : catégories d'événements (pastilles à activer ou non) et auteur. Les consultations,
// très nombreuses, sont masquées par défaut.
const categories = defineModel<EventCategory[]>("categories", { required: true });
const actor = defineModel<string>("actor", { required: true });
defineProps<{ actors: DossierEventActor[]; total: number }>();

function toggle(value: EventCategory) {
  categories.value = categories.value.includes(value)
    ? categories.value.filter((c) => c !== value)
    : [...categories.value, value];
}
</script>

<template>
  <div class="ef">
    <div class="ef__chips" role="group" aria-label="Types d'événements">
      <button
        v-for="c in EVENT_CATEGORIES"
        :key="c.value"
        type="button"
        class="ef__chip"
        :class="{ 'ef__chip--on': categories.includes(c.value) }"
        :aria-pressed="categories.includes(c.value)"
        @click="toggle(c.value)"
      >
        <VIcon :name="c.icon" /> {{ c.label }}
      </button>
    </div>

    <div class="ef__row">
      <div>
        <label for="ef-actor" class="ef__label">Auteur</label>
        <select id="ef-actor" v-model="actor" class="fr-select ef__select">
          <option value="">Tous les auteurs</option>
          <option v-for="a in actors" :key="a.actorId" :value="a.actorId">{{ a.actorName ?? a.actorId }}</option>
        </select>
      </div>
      <p class="ef__count" role="status">{{ total }} événement{{ total > 1 ? "s" : "" }}</p>
    </div>
  </div>
</template>

<style scoped>
.ef {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.ef__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.ef__chip {
  --hover: var(--background-alt-grey-hover);
  --active: var(--background-alt-grey-active);
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.875rem;
  border: none;
  border-radius: 1rem;
  background: var(--background-alt-grey);
  color: var(--text-default-grey);
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}

.ef__chip--on {
  --hover: var(--background-action-high-blue-france-hover);
  --active: var(--background-action-high-blue-france-active);
  background: var(--background-action-high-blue-france);
  color: var(--text-inverted-blue-france);
  font-weight: 600;
}

.ef__row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.ef__label {
  display: block;
  margin-bottom: 0.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
}

.ef__select {
  min-width: 14rem;
}

.ef__count {
  margin: 0;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}
</style>
