<script setup lang="ts">
import { computed, ref, watch } from "vue";

import ToolAuthBadge from "@/components/tools/ToolAuthBadge.vue";
import ToolTestPrompt from "@/components/tools/ToolTestPrompt.vue";
import ToolTestResult from "@/components/tools/ToolTestResult.vue";
import { examplePromptOf, runToolTest } from "@/composables/useToolTest";
import { useTools } from "@/composables/useTools";
import type { Tool, ToolTestRun } from "@/types/tool";

const props = defineProps<{ tool: Tool }>();
const opened = defineModel<boolean>("opened", { default: false });

const { servers } = useTools();

const server = computed(() => servers.value.find((candidate) => candidate.id === props.tool.serverId));

const prompt = ref("");
const run = ref<ToolTestRun | null>(null);
const loading = ref(false);
// Un tool qui modifie des données s'exécute pour de vrai : on demande une confirmation explicite.
const confirmed = ref(false);

watch(opened, (isOpened) => {
  if (!isOpened) return;
  prompt.value = examplePromptOf(props.tool);
  run.value = null;
  confirmed.value = false;
});

const canRun = computed(() => !loading.value && prompt.value.trim() !== "" && (!props.tool.sideEffect || confirmed.value));

async function execute() {
  loading.value = true;
  run.value = null;
  try {
    run.value = await runToolTest(props.tool, prompt.value);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <!-- Téléportée : une carte parente avec un transform enfermerait sinon la modale (position: fixed). -->
  <Teleport to="body">
    <DsfrModal
      :opened="opened"
      :title="`Tester « ${tool.name} »`"
      size="xl"
      :actions="[
        { label: 'Fermer', secondary: true, onClick: () => (opened = false) },
        { label: loading ? 'Appel en cours…' : 'Lancer le test', disabled: !canRun, onClick: execute },
      ]"
      @close="opened = false"
    >
      <p class="fr-text--sm tool-test-modal__intro">
        {{ tool.description }}
        <template v-if="server">
          Serveur « {{ server.name }} » <ToolAuthBadge :mode="server.authMode" />
        </template>
        <template v-else>Outil interne.</template>
      </p>
      <p class="fr-text--xs tool-test-modal__identity">
        <VIcon name="ri-flask-line" scale="0.8" /> Test unitaire : seul cet outil est donné au modèle, et seule sa sortie est affichée.
        <template v-if="server?.authMode === 'token_exchange'">Exécuté avec votre identité.</template>
      </p>

      <DsfrAlert v-if="tool.sideEffect" type="warning" small class="fr-mb-2w">
        <p>Cet outil modifie des données : le test l'exécute réellement.</p>
        <DsfrCheckbox v-model="confirmed" name="confirm-test" label="Je comprends, lancer le test pour de vrai" small />
      </DsfrAlert>

      <div class="tool-test-modal__columns">
        <section>
          <h3 class="tool-test-modal__heading">Demande</h3>
          <ToolTestPrompt v-model="prompt" />
        </section>
        <section>
          <h3 class="tool-test-modal__heading">Sortie brute de l'outil</h3>
          <ToolTestResult :run="run" :loading="loading" />
        </section>
      </div>
    </DsfrModal>
  </Teleport>
</template>

<style scoped>
.tool-test-modal__intro {
  margin-bottom: 0.25rem;
}

.tool-test-modal__identity {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  color: var(--text-mention-grey);
}

.tool-test-modal__columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 2rem;
  margin-top: 1rem;
}

.tool-test-modal__heading {
  margin: 0 0 0.75rem;
  font-size: 0.875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-mention-grey);
}
</style>
