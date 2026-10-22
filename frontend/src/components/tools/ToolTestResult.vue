<script setup lang="ts">
import { computed } from "vue";

import type { ToolTestRun } from "@/types/tool";

const props = defineProps<{ run: ToolTestRun | null; loading: boolean }>();

const output = computed(() => JSON.stringify(props.run?.output, null, 2));
const request = computed(() => JSON.stringify(props.run?.request, null, 2));

function copy() {
  navigator.clipboard?.writeText(output.value);
}
</script>

<template>
  <div class="tool-test-result">
    <p v-if="loading" class="tool-test-result__placeholder"><VIcon name="ri-loader-4-line" class="tool-test-result__spin" /> Appel en cours…</p>
    <p v-else-if="!run" class="tool-test-result__placeholder">Écrivez une demande puis lancez le test : la sortie brute de l'outil s'affichera ici.</p>
    <template v-else>
      <div class="tool-test-result__status">
        <DsfrBadge :label="run.ok ? 'Succès' : 'Erreur'" :type="run.ok ? 'success' : 'error'" small />
        <span class="tool-test-result__duration">{{ run.durationMs }} ms</span>
        <DsfrButton label="Copier" icon="ri-file-copy-line" tertiary no-outline size="sm" class="tool-test-result__copy" @click="copy" />
      </div>
      <pre class="tool-test-result__output" :class="{ 'tool-test-result__output--error': !run.ok }">{{ output }}</pre>
      <details class="tool-test-result__request">
        <summary>Appel fait par le modèle</summary>
        <pre>{{ request }}</pre>
      </details>
    </template>
  </div>
</template>

<style scoped>
.tool-test-result {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-height: 10rem;
}

.tool-test-result__placeholder {
  margin: auto 0;
  text-align: center;
  color: var(--text-mention-grey);
  font-size: 0.875rem;
}

.tool-test-result__spin {
  animation: tool-test-spin 1s linear infinite;
}

@keyframes tool-test-spin {
  to {
    transform: rotate(360deg);
  }
}

.tool-test-result__status {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.tool-test-result__duration {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.tool-test-result__copy {
  margin-left: auto;
}

pre {
  margin: 0;
  padding: 0.75rem 1rem;
  border-radius: 0.75rem;
  background: var(--background-alt-grey);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.75rem;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.tool-test-result__output--error {
  background: #ce05001a;
}

.tool-test-result__request {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.tool-test-result__request summary {
  cursor: pointer;
  margin-bottom: 0.5rem;
}
</style>
