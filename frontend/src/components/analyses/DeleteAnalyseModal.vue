<script setup lang="ts">
/**
 * Confirmation de la suppression d'une analyse. Le backend refuse (409) tant qu'elle a des dossiers : son message
 * s'affiche tel quel, rien n'est perdu.
 */
import { ref, watch } from "vue";

import { useAnalyses } from "@/composables/useAnalyses";
import type { Analyse } from "@/types/analyse";

const props = defineProps<{ analyse: Analyse }>();
const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ deleted: [] }>();

const { remove } = useAnalyses();
const error = ref("");
const isDeleting = ref(false);

watch(opened, (isOpened) => {
  if (isOpened) error.value = "";
});

async function confirm() {
  isDeleting.value = true;
  error.value = "";
  try {
    await remove(props.analyse.id);
    opened.value = false;
    emit("deleted");
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : "Échec de la suppression.";
  } finally {
    isDeleting.value = false;
  }
}
</script>

<template>
  <DsfrModal
    :opened="opened"
    title="Supprimer l'analyse ?"
    @close="opened = false"
    :actions="[
      { label: 'Annuler', secondary: true, onClick: () => (opened = false) },
      { label: 'Supprimer', disabled: isDeleting, onClick: confirm },
    ]"
  >
    <p>
      « {{ analyse.name }} » sera supprimée avec ses agents, ses labels, ses entités, ses statuts et tout son
      historique. Cette action est définitive.
    </p>
    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
  </DsfrModal>
</template>
