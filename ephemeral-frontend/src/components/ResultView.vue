<script setup lang="ts">
import { computed, ref } from "vue";

import ClassificationExplorer from "@/components/ClassificationExplorer.vue";
import ExtractionExplorer from "@/components/ExtractionExplorer.vue";
import type { ClassificationOut, ClassifiedPage, ExtractedPage, ExtractionOut, Mode } from "@/types";

const props = defineProps<{
  mode: Mode;
  classification: ClassificationOut | null;
  extraction: ExtractionOut | null;
}>();

// En mode « les deux », un onglet par résultat ; les deux restent montés pour garder la page et la recherche de chacun.
const tab = ref<"classification" | "extraction">("classification");
const showClassification = computed(() => props.mode === "classification" || (props.mode === "both" && tab.value === "classification"));
const showExtraction = computed(() => props.mode === "extraction" || (props.mode === "both" && tab.value === "extraction"));
</script>

<template>
  <div v-if="mode === 'both'" class="fr-segmented fr-segmented--sm fr-mb-3w" role="tablist" aria-label="Résultats">
    <div class="fr-segmented__elements">
      <div v-for="t in ['classification', 'extraction'] as const" :key="t" class="fr-segmented__element">
        <input :id="`result-tab-${t}`" v-model="tab" type="radio" name="result-tab" :value="t" />
        <label class="fr-label" :for="`result-tab-${t}`">{{ t === "classification" ? "Classification" : "Extraction" }}</label>
      </div>
    </div>
  </div>

  <section v-if="classification" v-show="showClassification" aria-label="Classification">
    <div v-for="doc in classification.documents" :key="doc.name" class="fr-mb-3w">
      <h3 class="fr-h6">{{ doc.name }}</h3>
      <ClassificationExplorer :run-id="classification.run_id" :pages="(doc.pages as ClassifiedPage[])" />
    </div>
  </section>

  <section v-if="extraction" v-show="showExtraction" aria-label="Extraction">
    <div v-for="doc in extraction.documents" :key="doc.name" class="fr-mb-3w">
      <h3 class="fr-h6">{{ doc.name }}</h3>
      <ExtractionExplorer :run-id="extraction.run_id" :pages="(doc.pages as ExtractedPage[])" />
    </div>
  </section>
</template>
