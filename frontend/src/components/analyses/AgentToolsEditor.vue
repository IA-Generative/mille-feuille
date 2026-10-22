<script setup lang="ts">
import { onMounted, ref } from "vue";

import ToolSelectionField from "@/components/tools/ToolSelectionField.vue";
import VersionHistory from "@/components/analyses/VersionHistory.vue";
import { useTools } from "@/composables/useTools";
import { AGENT_TOOL_LABELS, type Agent, type AgentTool } from "@/types/analyse";

defineProps<{ analyseId: string; agent: Agent }>();

// Aperçu (phase 1, données simulées) : la sélection n'est pas encore enregistrée. Le branchement sur l'API
// (et sur l'historique ci-dessous) viendra avec le backend des tools.
const { defaultToolIds, fetchTools } = useTools();
const pickedToolIds = ref<string[]>([]);
onMounted(async () => {
  await fetchTools();
  pickedToolIds.value = defaultToolIds();
});

function formatVersionContent(tools: AgentTool[]) {
  return tools.length > 0 ? tools.map((tool) => AGENT_TOOL_LABELS[tool]).join(", ") : "(aucun outil)";
}
</script>

<template>
  <div class="agent-tools-editor">
    <ToolSelectionField v-model="pickedToolIds" />
    <VersionHistory :versions="agent.toolsVersions" :format-content="formatVersionContent" @restore="() => {}" />
  </div>
</template>

<style scoped>
.agent-tools-editor {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.75rem;
}
</style>
