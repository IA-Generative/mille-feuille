<script setup lang="ts">
/**
 * Ajout de fichiers à un dossier déjà créé, avec leur source. Jamais refusé selon l'état du dossier : si l'analyse a
 * déjà tourné, la page propose ensuite de la relancer pour prendre les nouveaux fichiers en compte.
 */
import { nextTick, ref, useTemplateRef, watch } from "vue";

import AppModal from "@/components/AppModal.vue";
import DocumentFileList from "@/components/dossiers/DocumentFileList.vue";
import SourcePicker from "@/components/dossiers/SourcePicker.vue";
import { fetchDossierSources, resolveSourceChoice } from "@/composables/useDocumentSources";
import { useDossiers } from "@/composables/useDossiers";
import { useSelectedFiles } from "@/composables/useSelectedFiles";
import { NO_SOURCE, type DocumentSource, type SourceChoice } from "@/types/documentSource";
import { userMessage } from "@/utils/api";
import { scrollIntoViewSoft } from "@/utils/scroll";

const props = defineProps<{
  dossierId: string;
  /** Fichiers déjà choisis (ex : joints depuis le chat) : la modale s'ouvre avec eux. */
  initialFiles?: File[];
}>();
const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ added: [count: number] }>();

const { addDocuments } = useDossiers();

// Fichiers choisis : la liste, un résumé visible sous le champ de dépôt et l'erreur d'un type refusé.
const {
  files,
  message: filesMessage,
  error: filesError,
  reset: resetFiles,
  add: addFiles,
  remove: removeFile,
} = useSelectedFiles();
const filesSummary = useTemplateRef<HTMLElement>("filesSummary");
const sources = ref<DocumentSource[]>([]);
const choice = ref<SourceChoice>(NO_SOURCE);
const busy = ref(false);
const error = ref("");

watch(opened, async (isOpened) => {
  if (!isOpened) return;
  resetFiles(props.initialFiles);
  choice.value = NO_SOURCE;
  error.value = "";
  sources.value = await fetchDossierSources(props.dossierId).catch(() => []);
});

async function onFilesSelected(fileList: FileList) {
  addFiles(fileList);
  await nextTick();
  scrollIntoViewSoft(filesSummary.value);
}

async function submit() {
  if (files.value.length === 0 || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const sourceId = await resolveSourceChoice(props.dossierId, choice.value);
    await addDocuments(props.dossierId, files.value, sourceId);
    emit("added", files.value.length);
    opened.value = false;
  } catch (e) {
    error.value = userMessage(e, "L'ajout des fichiers a échoué.");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <AppModal
    :opened="opened"
    :close-on-backdrop="false"
    title="Ajouter des documents"
    size="lg"
    :actions="[
      { label: 'Annuler', secondary: true, onClick: () => (opened = false) },
      { label: busy ? 'Envoi…' : 'Ajouter', onClick: submit, disabled: files.length === 0 || busy },
    ]"
    @close="opened = false"
  >
    <DsfrFileUpload
      id="add-documents"
      label="Fichiers à ajouter au dossier"
      hint="PDF, JPG ou PNG."
      accept=".pdf,image/*"
      multiple
      :error="filesError"
      @change="onFilesSelected"
    />
    <!-- Toujours rendu (même vide) : une zone role="status" créée en même temps que son texte n'est pas annoncée. -->
    <p ref="filesSummary" role="status" class="fr-text--sm fr-mb-0" :class="{ 'fr-mt-1w': filesMessage }">{{ filesMessage }}</p>

    <DocumentFileList :files="files" focus-on-empty="add-documents" @remove="removeFile" />

    <div class="fr-mt-3w">
      <SourcePicker v-model="choice" :sources="sources" id="add-documents-source" />
    </div>

    <DsfrAlert v-if="error" alert type="error" small :description="error" class="fr-mt-2w" />
  </AppModal>
</template>
