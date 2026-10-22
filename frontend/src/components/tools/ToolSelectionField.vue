<script setup lang="ts">
import { onMounted, ref } from "vue";

import ToolPickerModal from "@/components/tools/ToolPickerModal.vue";
import ToolSelectionSummary from "@/components/tools/ToolSelectionSummary.vue";
import { useTools } from "@/composables/useTools";

const toolIds = defineModel<string[]>({ required: true });
const isPickerOpened = ref(false);

const { fetchTools } = useTools();
onMounted(() => fetchTools());
</script>

<template>
  <div class="tool-selection-field">
    <div class="tool-selection-field__header">
      <span class="tool-selection-field__legend">Outils de l'agent</span>
      <DsfrButton label="Choisir les outils" icon="ri-tools-line" secondary size="sm" @click="isPickerOpened = true" />
    </div>
    <ToolSelectionSummary :tool-ids="toolIds" />
    <ToolPickerModal v-model:opened="isPickerOpened" :tool-ids="toolIds" @confirm="toolIds = $event" />
  </div>
</template>

<style scoped>
.tool-selection-field {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
}

.tool-selection-field__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.tool-selection-field__legend {
  font-weight: 600;
}
</style>
