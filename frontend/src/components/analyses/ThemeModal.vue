<script setup lang="ts">
import { ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import AppModal from "@/components/AppModal.vue";
import { useAnalyseThemes } from "@/composables/useAnalyseThemes";
import type { AnalyseTheme } from "@/types/theme";
import { userMessage } from "@/utils/api";

/** `theme` null : création. */
const props = defineProps<{ opened: boolean; theme: AnalyseTheme | null }>();
const emit = defineEmits<{ close: []; saved: [] }>();

const { createTheme, updateTheme, restoreThemeVersion } = useAnalyseThemes();

const name = ref("");
const description = ref("");
const error = ref("");
const current = ref<AnalyseTheme | null>(null);

function fill(theme: AnalyseTheme | null) {
  current.value = theme;
  name.value = theme?.name ?? "";
  description.value = theme?.description ?? "";
  error.value = "";
}

watch(
  () => props.opened,
  (isOpened) => {
    if (isOpened) fill(props.theme);
  },
);

async function submit() {
  if (!name.value.trim()) return;
  try {
    if (current.value) await updateTheme(current.value.id, name.value, description.value);
    else await createTheme(name.value, description.value);
    emit("saved");
    emit("close");
  } catch (cause) {
    error.value = userMessage(cause, "Le thème n'a pas pu être enregistré.");
  }
}

async function restore(versionId: string) {
  if (!current.value) return;
  try {
    fill(await restoreThemeVersion(current.value.id, versionId));
    emit("saved");
  } catch (cause) {
    error.value = userMessage(cause, "La version n'a pas pu être restaurée.");
  }
}
</script>

<template>
  <AppModal
    :opened="opened"
    :title="theme ? 'Modifier le thème' : 'Créer un thème'"
    :actions="[
      { label: 'Annuler', secondary: true, onClick: () => emit('close') },
      { label: 'Enregistrer', onClick: submit },
    ]"
    @close="emit('close')"
  >
    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
    <DsfrInput v-model="name" label="Nom du thème" label-visible required @keyup.enter="submit" />
    <VersionHistory
      v-if="current"
      :versions="current.nameVersions"
      :format-content="(content: string) => content"
      @restore="restore"
    />
    <div class="fr-mt-3w">
      <DsfrInput
        v-model="description"
        label="Description"
        label-visible
        is-textarea
        hint="Facultative : les dossiers et les analyses que ce thème regroupe."
      />
    </div>
    <VersionHistory
      v-if="current"
      :versions="current.descriptionVersions"
      :format-content="(content: string) => content || '(vide)'"
      @restore="restore"
    />
  </AppModal>
</template>
