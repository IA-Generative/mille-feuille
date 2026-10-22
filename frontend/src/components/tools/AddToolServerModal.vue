<script setup lang="ts">
import { computed, ref, watch } from "vue";

import ToolImportList from "@/components/tools/ToolImportList.vue";
import ToolServerForm from "@/components/tools/ToolServerForm.vue";
import { useTools } from "@/composables/useTools";
import type { Tool, ToolServerDraft } from "@/types/tool";

const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ added: [] }>();

const { discoverTools, addServer } = useTools();

const emptyDraft = (): ToolServerDraft => ({ name: "", url: "", authMode: "token_exchange", audience: "", visibility: "private" });

const step = ref<"form" | "import">("form");
const draft = ref<ToolServerDraft>(emptyDraft());
const discovered = ref<Tool[]>([]);
const selected = ref<string[]>([]);
const busy = ref(false);
const error = ref("");

watch(opened, (isOpened) => {
  if (!isOpened) return;
  step.value = "form";
  draft.value = emptyDraft();
  discovered.value = [];
  selected.value = [];
  error.value = "";
});

const canImport = computed(
  () =>
    draft.value.name.trim() !== "" &&
    /^https?:\/\//.test(draft.value.url.trim()) &&
    (draft.value.authMode !== "token_exchange" || draft.value.audience.trim() !== ""),
);

// Un appel qui échoue (adresse refusée, serveur muet, mode pas encore disponible…) affiche le message de l'API.
async function attempt(action: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await action();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "L'action a échoué.";
  } finally {
    busy.value = false;
  }
}

const importTools = () =>
  attempt(async () => {
    discovered.value = await discoverTools(draft.value);
    // Les tools qui modifient des données ne sont pas cochés d'office.
    selected.value = discovered.value.filter((tool) => !tool.sideEffect).map((tool) => tool.id);
    step.value = "import";
  });

const submit = () =>
  attempt(async () => {
    await addServer(draft.value, selected.value);
    opened.value = false;
    emit("added");
  });

const actions = computed(() =>
  step.value === "form"
    ? [
        { label: "Annuler", secondary: true, onClick: () => (opened.value = false) },
        { label: busy.value ? "Import en cours…" : "Importer les tools", disabled: !canImport.value || busy.value, onClick: importTools },
      ]
    : [
        { label: "Retour", secondary: true, onClick: () => (step.value = "form") },
        { label: "Ajouter le serveur", disabled: selected.value.length === 0 || busy.value, onClick: submit },
      ],
);
</script>

<template>
  <!-- Téléportée : une carte parente avec un transform enfermerait sinon la modale (position: fixed). -->
  <Teleport to="body">
  <DsfrModal
    :opened="opened"
    :title="step === 'form' ? 'Ajouter un serveur MCP' : `Tools de ${draft.name}`"
    size="lg"
    :actions="actions"
    @close="opened = false"
  >
    <DsfrAlert v-if="error" type="error" small :description="error" class="fr-mb-2w" />
    <ToolServerForm v-if="step === 'form'" v-model="draft" />
    <ToolImportList v-else v-model="selected" :tools="discovered" />
  </DsfrModal>
  </Teleport>
</template>
