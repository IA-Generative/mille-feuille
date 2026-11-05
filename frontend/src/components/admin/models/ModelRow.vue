<script setup lang="ts">
import ModelCapabilityChips from "@/components/admin/models/ModelCapabilityChips.vue";
import type { LlmCapability, LlmModel } from "@/types/llmModel";

defineProps<{
  model: LlmModel;
  capabilities: LlmCapability[];
  isDefault: boolean;
  first: boolean;
  last: boolean;
}>();
const emit = defineEmits<{ edit: []; move: [direction: -1 | 1]; toggle: [enabled: boolean] }>();
</script>

<template>
  <li class="model-row" :class="{ 'model-row--off': !model.enabled }">
    <div class="model-row__order">
      <button type="button" aria-label="Monter" :disabled="first" @click="emit('move', -1)">
        <VIcon name="ri-arrow-up-s-line" />
      </button>
      <button type="button" aria-label="Descendre" :disabled="last" @click="emit('move', 1)">
        <VIcon name="ri-arrow-down-s-line" />
      </button>
    </div>

    <div class="model-row__main">
      <div class="model-row__name">
        <strong>{{ model.name }}</strong>
        <DsfrBadge v-if="isDefault" label="Par défaut" type="info" small no-icon />
      </div>
      <ModelCapabilityChips :capabilities="capabilities" />
    </div>

    <DsfrToggleSwitch
      :model-value="model.enabled"
      :label="model.enabled ? 'Actif' : 'Inactif'"
      no-text
      @update:model-value="emit('toggle', $event)"
    />

    <button type="button" class="model-row__edit" :aria-label="`Modifier ${model.name}`" @click="emit('edit')">
      <VIcon name="ri-pencil-line" />
    </button>
  </li>
</template>

<style scoped>
.model-row {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  align-items: center;
  gap: 1rem;
  padding: 0.875rem 1rem;
}

.model-row + .model-row {
  border-top: 1px solid var(--border-default-grey, #eee);
}

.model-row--off .model-row__main {
  opacity: 0.55;
}

.model-row__order {
  display: flex;
  flex-direction: column;
}

.model-row__order button,
.model-row__edit {
  border: 0;
  background: none;
  cursor: pointer;
  color: var(--text-mention-grey, #666);
  line-height: 1;
  padding: 0.125rem;
}

.model-row__order button:disabled {
  opacity: 0.25;
  cursor: default;
}

.model-row__main {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
}

.model-row__name {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

</style>
