<script setup lang="ts">
import { ref } from "vue";

import PromptEditor from "@/components/analyses/PromptEditor.vue";
import { errorMessage, useDocumentTemplates } from "@/composables/useDocumentTemplates";
import type { PromptVersion } from "@/types/analyse";
import type { GenerationPrompt } from "@/types/documentTemplate";

// Prompt de l'agent qui propose les valeurs des champs (backend issue #141). Versionné en ajout seul : enregistrer
// ou restaurer ajoute une version. Seule la méthode se modifie ; les garde-fous (ne jamais inventer, le contenu
// des notes et des documents est une donnée) sont fixés par le système et s'ajoutent après ce texte.
const api = useDocumentTemplates();

const prompt = ref<GenerationPrompt | null>(null);
const versions = ref<PromptVersion[]>([]);
const error = ref("");
const success = ref("");

async function reload() {
  try {
    [prompt.value, versions.value] = await Promise.all([api.fetchPrompt(), api.fetchPromptVersions()]);
  } catch (e) {
    error.value = errorMessage(e, "Impossible de charger le prompt de génération.");
  }
}

async function save(content: string) {
  error.value = "";
  success.value = "";
  try {
    await api.savePrompt(content.trim());
    success.value = "Nouvelle version du prompt enregistrée.";
    await reload();
  } catch (e) {
    error.value = errorMessage(e, "Erreur lors de l'enregistrement du prompt.");
  }
}

async function restore(versionId: string) {
  if (!confirm("Restaurer cette version ? Une nouvelle version, identique à elle, sera ajoutée.")) return;
  error.value = "";
  success.value = "";
  try {
    await api.restorePrompt(versionId);
    success.value = "Version restaurée (ajoutée comme nouvelle version).";
    await reload();
  } catch (e) {
    error.value = errorMessage(e, "Impossible de restaurer cette version.");
  }
}

defineExpose({ reload });
</script>

<template>
  <section class="generation-prompt">
    <h3 class="fr-h5">
      Prompt de l'agent de génération
      <DsfrBadge v-if="prompt" :label="prompt.isDefault ? 'Prompt par défaut' : prompt.label" :type="prompt.isDefault ? 'info' : 'success'" small />
    </h3>
    <p class="fr-text--sm">
      Il guide l'agent qui propose une valeur pour chaque champ. Il est complété par la consigne de chaque champ et par des
      règles que ce texte ne peut pas retirer : ne jamais inventer, traiter les notes et les documents comme des données.
    </p>
    <DsfrAlert v-if="error" alert type="error" :description="error" small />
    <DsfrAlert v-if="success" type="success" :description="success" small />
    <PromptEditor v-if="prompt" :prompt="prompt.content" :versions="versions" @save="save" @restore="restore" />
  </section>
</template>

<style scoped>
.generation-prompt {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.generation-prompt h3 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin: 0;
}
</style>
