<script setup lang="ts">
import type { PresentationEntity } from "@/types/dossierPresentation";

defineProps<{ entities: PresentationEntity[] }>();
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

@media (max-width: 36rem) {
  .presentation-entities__row {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
