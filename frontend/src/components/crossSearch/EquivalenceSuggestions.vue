<script setup lang="ts">
/** Les entités qui ressemblent à celles d'un critère : proposées, jamais ajoutées sans l'accord de l'administrateur. */
import { computed } from "vue";

import { similarTo } from "@/composables/mockEntityCatalog";

const props = defineProps<{ entityIds: string[]; refusedIds: string[] }>();
const emit = defineEmits<{ accept: [id: string]; refuse: [id: string]; reconsider: [id: string] }>();

const proposed = computed(() => similarTo(props.entityIds).filter((e) => !props.refusedIds.includes(e.id)));
</script>

<template>
  <div v-if="proposed.length || refusedIds.length" class="suggestions">
    <template v-if="proposed.length">
      <p class="suggestions__hint">Entités qui y ressemblent, à confirmer :</p>
      <ul class="suggestions__list">
        <li v-for="entity in proposed" :key="entity.id" class="suggestions__row">
          <span>{{ entity.name }} <span class="suggestions__hint">· {{ entity.analyseName }}</span></span>
          <span class="suggestions__actions">
            <button type="button" class="fr-btn fr-btn--sm fr-btn--secondary" :aria-label="`Accepter ${entity.id}`" @click="emit('accept', entity.id)">Accepter</button>
            <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline" :aria-label="`Refuser ${entity.id}`" @click="emit('refuse', entity.id)">Refuser</button>
          </span>
        </li>
      </ul>
    </template>

    <details v-if="refusedIds.length">
      <summary class="suggestions__hint">Refusées ({{ refusedIds.length }})</summary>
      <ul class="suggestions__list">
        <li v-for="id in refusedIds" :key="id" class="suggestions__row">
          <span>{{ id }}</span>
          <button type="button" class="fr-link fr-text--sm" :aria-label="`Reproposer ${id}`" @click="emit('reconsider', id)">Reproposer</button>
        </li>
      </ul>
    </details>
  </div>
</template>

<style scoped>
.suggestions {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.suggestions__hint {
  margin: 0;
  color: var(--text-mention-grey);
  font-size: 0.8125rem;
}

.suggestions__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.suggestions__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.suggestions__actions {
  display: flex;
  gap: 0.25rem;
}
</style>
