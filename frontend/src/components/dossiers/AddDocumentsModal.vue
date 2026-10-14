<script setup lang="ts">
/**
 * Ajout de fichiers à un dossier déjà créé, avec leur source. Jamais refusé selon l'état du dossier : si l'analyse a
 * déjà tourné, la page propose ensuite de la relancer pour prendre les nouveaux fichiers en compte.
 */
import { ref, watch } from "vue";

import DocumentFileList from "@/components/dossiers/DocumentFileList.vue";
import SourcePicker from "@/components/dossiers/SourcePicker.vue";
import { fetchDossierSources, resolveSourceChoice } from "@/composables/useDocumentSources";
import { useDossiers } from "@/composables/useDossiers";
import { NO_SOURCE, type DocumentSource, type SourceChoice } from "@/types/documentSource";

const props = defineProps<{ dossierId: string }>();
const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ added: [count: number] }>();

const { addDocuments } = useDossiers();

const files = ref<File[]>([]);
const sources = ref<DocumentSource[]>([]);
const choice = ref<SourceChoice>(NO_SOURCE);
const busy = ref(false);
const error = ref("");

watch(opened, async (isOpened) => {
  if (!isOpened) return;
  files.value = [];
  choice.value = NO_SOURCE;
  error.value = "";
  sources.value = await fetchDossierSources(props.dossierId).catch(() => []);
});

function onFilesSelected(fileList: FileList) {
  files.value.push(...Array.from(fileList));
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
    error.value = e instanceof Error ? e.message : "L'ajout des fichiers a échoué.";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <DsfrModal
    :opened="opened"
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
      @change="onFilesSelected"
    />
    <DocumentFileList :files="files" @remove="files.splice($event, 1)" />

    <div class="fr-mt-3w">
      <SourcePicker v-model="choice" :sources="sources" id="add-documents-source" />
    </div>

    <p v-if="error" class="fr-error-text fr-mt-2w" role="alert">{{ error }}</p>
  </DsfrModal>
</template>
