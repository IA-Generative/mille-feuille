<script setup lang="ts">
import { ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { AGENT_TOOL_LABELS, type Agent, type AgentTool } from "@/types/analyse";

const props = defineProps<{ analyseId: string; agent: Agent }>();

const { updateAgentTools, restoreAgentToolsVersion } = useAnalyses();

const toolOptions = (Object.keys(AGENT_TOOL_LABELS) as AgentTool[]).map((tool) => ({
  name: tool,
  value: tool,
  label: AGENT_TOOL_LABELS[tool],
}));

const draftTools = ref<AgentTool[]>([...props.agent.tools]);
const isDirty = ref(false);

watch(
  () => props.agent.tools,
  (tools) => {
    draftTools.value = [...tools];
    isDirty.value = false;
  },
);

watch(
  draftTools,
  (tools) => {
    isDirty.value = JSON.stringify([...tools].sort()) !== JSON.stringify([...props.agent.tools].sort());
  },
  { deep: true },
);

function save() {
  updateAgentTools(props.analyseId, props.agent.id, draftTools.value);
}

function restoreVersion(versionId: string) {
  restoreAgentToolsVersion(props.analyseId, props.agent.id, versionId);
}

function formatVersionContent(tools: AgentTool[]) {
  return tools.length > 0 ? tools.map((tool) => AGENT_TOOL_LABELS[tool]).join(", ") : "(aucun outil)";
}
</script>

<template>
  <div class="agent-tools-editor">
    <DsfrCheckboxSet v-model="draftTools" legend="Outils disponibles" :options="toolOptions" inline small />
    <DsfrButton label="Enregistrer" :disabled="!isDirty" size="sm" @click="save" />
    <VersionHistory :versions="agent.toolsVersions" :format-content="formatVersionContent" @restore="restoreVersion" />
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
