<script setup lang="ts">
import { ref, watch } from "vue";

import type { LlmCapability } from "@/types/llmModel";

// `capability` : celle qu'on modifie ; `null` avec `opened` : une nouvelle.
const props = defineProps<{ opened: boolean; capability: LlmCapability | null }>();
const emit = defineEmits<{ close: []; save: [input: { id?: string; name: string; description: string }]; remove: [] }>();

const name = ref("");
const description = ref("");

watch(
  () => [props.opened, props.capability] as const,
  () => {
    name.value = props.capability?.name ?? "";
    description.value = props.capability?.description ?? "";
  },
  { immediate: true },
);
</script>

<template>
  <DsfrModal
    :opened="opened"
    :title="capability ? 'Modifier la capacité' : 'Nouvelle capacité'"
    icon="ri-sparkling-line"
    @close="emit('close')"
  >
    <DsfrInput v-model="name" label="Nom" label-visible placeholder="Tâches lourdes" />
    <DsfrInput
      v-model="description"
      label="Description"
      label-visible
      is-textarea
      placeholder="Capable de raisonner sur plusieurs documents et de rédiger de longs textes."
      hint="Ce texte aide à choisir le modèle en mode auto : décrivez ce que le modèle sait faire."
    />
    <div class="capability-modal__actions">
      <DsfrButton
        v-if="capability"
        label="Supprimer"
        tertiary
        no-outline
        icon="ri-delete-bin-line"
        @click="emit('remove')"
      />
      <span v-else />
      <DsfrButton
        label="Enregistrer"
        :disabled="!name.trim() || !description.trim()"
        @click="emit('save', { id: capability?.id, name: name.trim(), description: description.trim() })"
      />
    </div>
  </DsfrModal>
</template>

<style scoped>
.capability-modal__actions {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 1.25rem;
}
</style>
