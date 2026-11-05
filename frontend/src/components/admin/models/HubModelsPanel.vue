<script setup lang="ts">
import { computed } from "vue";

import ModelTypeChips from "@/components/admin/models/ModelTypeChips.vue";
import type { HubModel } from "@/types/llmModel";

const props = defineProps<{ models: HubModel[]; readAt: Date | null; error: string; refreshing: boolean }>();
const emit = defineEmits<{ add: [model: HubModel]; refresh: [] }>();

const readAgo = computed(() => {
  if (!props.readAt) return "jamais";
  const minutes = Math.round((Date.now() - props.readAt.getTime()) / 60_000);
  return minutes < 1 ? "à l'instant" : `il y a ${minutes} min`;
});
</script>

<template>
  <section class="hub-panel" aria-labelledby="hub-title">
    <div class="hub-panel__header">
      <div>
        <h3 id="hub-title" class="hub-panel__title">Modèles du hub</h3>
        <p class="hub-panel__note">Dernière lecture du hub : {{ readAgo }}. Les types sont lus sur le hub ; vous donnez vous-même ses capacités à chaque modèle ajouté.</p>
      </div>
      <DsfrButton
        label="Relire le hub"
        icon="ri-refresh-line"
        secondary
        size="sm"
        :disabled="refreshing"
        @click="emit('refresh')"
      />
    </div>

    <p v-if="error" class="hub-panel__empty" role="alert">{{ error }}</p>
    <p v-else-if="!models.length" class="hub-panel__empty">Tous les modèles du hub sont déjà dans la liste.</p>
    <ul v-else class="hub-panel__list">
      <li v-for="model in models" :key="model.name" class="hub-panel__item">
        <div class="hub-panel__info">
          <strong>{{ model.name }}</strong>
          <ModelTypeChips :types="model.types" />
        </div>
        <DsfrButton label="Ajouter" icon="ri-add-line" tertiary size="sm" @click="emit('add', model)" />
      </li>
    </ul>
  </section>
</template>

<style scoped>
.hub-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.hub-panel__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.hub-panel__title {
  margin: 0;
  font-size: 1rem;
}

.hub-panel__note,
.hub-panel__empty {
  margin: 0.125rem 0 0;
  font-size: 0.8125rem;
  color: var(--text-mention-grey, #666);
}

.hub-panel__list {
  margin: 0;
  padding: 0;
  list-style: none;
  border: 1px dashed var(--border-default-grey, #ccc);
  border-radius: 0.875rem;
}

.hub-panel__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 1rem;
}

.hub-panel__item + .hub-panel__item {
  border-top: 1px dashed var(--border-default-grey, #ddd);
}

.hub-panel__info {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
</style>
