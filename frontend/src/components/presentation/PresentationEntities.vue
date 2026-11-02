<script setup lang="ts">
import type { PresentationEntity } from "@/types/dossierPresentation";

defineProps<{ entities: PresentationEntity[]; detailable?: boolean }>();
const emit = defineEmits<{ detail: [] }>();
</script>

<template>
  <dl class="presentation-entities">
    <div v-for="entity in entities" :key="entity.name" class="presentation-entities__row">
      <dt>{{ entity.name }}</dt>
      <dd>
        {{ entity.value }}
        <span v-if="entity.page" class="presentation-entities__page">p. {{ entity.page }}</span>
      </dd>
    </div>
  </dl>
  <button v-if="detailable" type="button" class="presentation-entities__detail" @click="emit('detail')">
    Voir le détail par page
  </button>
</template>

<style scoped>
.presentation-entities {
  display: grid;
  gap: 0.5rem;
  margin: 0;
}

.presentation-entities__row {
  display: grid;
  grid-template-columns: minmax(8rem, 40%) 1fr;
  gap: 0.75rem;
  font-size: 0.9375rem;
}

.presentation-entities dt {
  color: var(--text-mention-grey);
}

.presentation-entities dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.presentation-entities__page {
  margin-left: 0.5rem;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.presentation-entities__detail {
  margin-top: 0.75rem;
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  font-size: 0.875rem;
  color: var(--text-action-high-blue-france);
  cursor: pointer;
}

.presentation-entities__detail:hover {
  text-decoration: underline;
}

@media (max-width: 36rem) {
  .presentation-entities__row {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
