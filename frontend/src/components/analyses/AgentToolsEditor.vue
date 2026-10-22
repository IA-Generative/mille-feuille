<script setup lang="ts">
import { computed, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import ToolSelectionField from "@/components/tools/ToolSelectionField.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { useTools } from "@/composables/useTools";
import type { Agent } from "@/types/analyse";

const props = defineProps<{ analyseId: string; agent: Agent }>();

const { updateAgentTools, restoreAgentToolsVersion } = useAnalyses();
const { toolNames } = useTools();

const draftTools = ref<string[]>([...props.agent.tools]);
const isSaving = ref(false);
const error = ref("");

// Le brouillon suit l'agent quand il change (enregistrement, restauration d'une version).
watch(
  () => props.agent.tools,
  (tools) => (draftTools.value = [...tools]),
);

const isDirty = computed(
  () => JSON.stringify([...draftTools.value].sort()) !== JSON.stringify([...props.agent.tools].sort()),
);

// Une action qui échoue (outil refusé, droit retiré…) affiche le message de l'API plutôt que de ne rien faire.
async function attempt(action: () => Promise<void>) {
  isSaving.value = true;
  error.value = "";
  try {
    await action();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "L'action a échoué.";
  } finally {
    isSaving.value = false;
  }
}

const save = () => attempt(() => updateAgentTools(props.analyseId, props.agent.id, draftTools.value));
const restoreVersion = (versionId: string) =>
  attempt(() => restoreAgentToolsVersion(props.analyseId, props.agent.id, versionId));

const formatVersionContent = (tools: string[]) => (tools.length > 0 ? toolNames(tools).join(", ") : "(aucun outil)");
</script>

<template>
  <div class="agent-tools-editor">
    <ToolSelectionField v-model="draftTools" />
    <div v-if="error" class="fr-alert fr-alert--error fr-alert--sm" role="alert"><p>{{ error }}</p></div>
    <DsfrButton :label="isSaving ? 'Enregistrement…' : 'Enregistrer'" :disabled="!isDirty || isSaving" size="sm" @click="save" />
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
