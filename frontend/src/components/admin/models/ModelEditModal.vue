<script setup lang="ts">
import { ref, watch } from "vue";

import ModelTypeChips from "@/components/admin/models/ModelTypeChips.vue";
import type { LlmCapability, LlmModel } from "@/types/llmModel";

const props = defineProps<{ model: LlmModel | null; capabilities: LlmCapability[] }>();
const emit = defineEmits<{ close: []; save: [capabilityIds: string[]]; remove: [] }>();

const selected = ref<string[]>([]);

watch(
  () => props.model,
  (model) => {
    selected.value = model ? [...model.capabilityIds] : [];
  },
  { immediate: true },
);
</script>

<template>
  <DsfrModal :opened="!!model" :title="model?.name ?? ''" icon="ri-cpu-line" @close="emit('close')">
    <ModelTypeChips v-if="model" :types="model.types" class="edit-modal__types" />

    <fieldset class="edit-modal__group">
      <legend class="fr-text--sm">Capacités de ce modèle</legend>
      <p v-if="!capabilities.length" class="edit-modal__empty">
        Aucune capacité n'est définie : créez-en dans la section « Capacités ».
      </p>
      <label v-for="capability in capabilities" :key="capability.id" class="edit-modal__choice">
        <input v-model="selected" type="checkbox" :value="capability.id" />
        <span>
          <strong>{{ capability.name }}</strong>
          <small>{{ capability.description }}</small>
        </span>
      </label>
    </fieldset>

    <div class="edit-modal__actions">
      <DsfrButton label="Retirer de la liste" tertiary no-outline icon="ri-delete-bin-line" @click="emit('remove')" />
      <DsfrButton label="Enregistrer" @click="emit('save', selected)" />
    </div>
  </DsfrModal>
</template>

<style scoped>
.edit-modal__types {
  margin-bottom: 1rem;
}

.edit-modal__group {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  border: 0;
  margin: 0 0 1.25rem;
  padding: 0;
}

.edit-modal__choice {
  display: flex;
  align-items: flex-start;
  gap: 0.625rem;
}

.edit-modal__choice span {
  display: flex;
  flex-direction: column;
}

.edit-modal__choice small,
.edit-modal__empty {
  color: var(--text-mention-grey, #666);
}

.edit-modal__actions {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}
</style>
