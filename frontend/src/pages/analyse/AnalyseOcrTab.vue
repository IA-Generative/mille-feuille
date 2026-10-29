<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import ModelPicker from "@/components/ModelPicker.vue";
import { useAnalyseOcr } from "@/composables/useAnalyseOcr";

// Onglet « Lecture » d'une analyse : le modèle du hub qui décrit les images et les tableaux des documents scannés,
// versionné comme le reste. Il vaut pour les documents extraits ensuite ; ceux qui l'ont déjà été gardent leurs
// descriptions.
const route = useRoute();
const analyseId = computed(() => String(route.params.id));
const { data, loading, error, load, save, restore } = useAnalyseOcr(analyseId);

const message = ref("");

onMounted(load);

async function onSave(model: string) {
  message.value = "";
  if (await save(model)) message.value = "Modèle enregistré. Le précédent est dans l'historique.";
}

async function onRestore(versionId: string) {
  message.value = "";
  if (await restore(versionId)) message.value = "Version restaurée.";
}

const formatVersion = (content: { captionModel: string }) => content.captionModel || "Modèle par défaut";
</script>

<template>
  <div v-if="data" class="analyse-ocr">
    <p class="fr-text--sm">
      Les images et les tableaux des documents scannés de cette analyse sont décrits par un modèle du hub, et la description
      est ajoutée au texte de la page. Le changement vaut pour les documents importés ensuite.
    </p>
    <ModelPicker
      :model-value="data.captionModel"
      label="Modèle de description des images"
      show-label
      @update:model-value="onSave"
    />
    <VersionHistory :versions="data.versions" :format-content="formatVersion" @restore="onRestore" />
    <p v-if="message" class="analyse-ocr__ok" role="status">{{ message }}</p>
    <p v-if="error" class="analyse-ocr__error" role="alert">{{ error }}</p>
  </div>
  <p v-else-if="loading">Chargement…</p>
  <p v-else-if="error" class="analyse-ocr__error" role="alert">{{ error }}</p>
</template>

<style scoped>
.analyse-ocr {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.analyse-ocr p {
  margin: 0;
}

.analyse-ocr__ok {
  color: var(--text-default-success);
}

.analyse-ocr__error {
  color: var(--text-default-error);
}
</style>
