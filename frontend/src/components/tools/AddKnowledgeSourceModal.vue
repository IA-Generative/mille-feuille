<script setup lang="ts">
import { computed, ref, watch } from "vue";

import KnowledgeSourceForm from "@/components/tools/KnowledgeSourceForm.vue";
import { useKnowledgeSources } from "@/composables/useKnowledgeSources";
import type { KnowledgeSourceDraft } from "@/types/knowledge";

const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ added: [] }>();

const { addSource } = useKnowledgeSources();

const emptyDraft = (): KnowledgeSourceDraft => ({ name: "", url: "", authMode: "token_exchange", audience: "", visibility: "private" });

const draft = ref<KnowledgeSourceDraft>(emptyDraft());
const busy = ref(false);
const error = ref("");

watch(opened, (isOpened) => {
  if (!isOpened) return;
  draft.value = emptyDraft();
  error.value = "";
});

const canSubmit = computed(
  () =>
    draft.value.name.trim() !== "" &&
    /^https?:\/\//.test(draft.value.url.trim()) &&
    (draft.value.authMode !== "token_exchange" || draft.value.audience.trim() !== ""),
);

// La connexion est vérifiée avant l'enregistrement : adresse refusée, fournisseur muet ou hors contrat s'affichent ici.
async function submit() {
  busy.value = true;
  error.value = "";
  try {
    await addSource(draft.value);
    opened.value = false;
    emit("added");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "L'ajout a échoué.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <DsfrModal
      :opened="opened"
      title="Ajouter une source de connaissances"
      size="lg"
      :actions="[
        { label: 'Annuler', secondary: true, onClick: () => (opened = false) },
        { label: busy ? 'Vérification…' : 'Vérifier et ajouter', disabled: !canSubmit || busy, onClick: submit },
      ]"
      @close="opened = false"
    >
      <DsfrAlert v-if="error" type="error" small :description="error" class="fr-mb-2w" />
      <KnowledgeSourceForm v-model="draft" />
    </DsfrModal>
  </Teleport>
</template>
