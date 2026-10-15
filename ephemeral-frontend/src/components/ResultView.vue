<script setup lang="ts">
import { computed } from "vue";

import ClassificationExplorer from "@/components/ClassificationExplorer.vue";
import ExtractionExplorer from "@/components/ExtractionExplorer.vue";
import type { ClassifiedPage, ExtractedPage, RunOut } from "@/types";

const props = defineProps<{ result: RunOut; mode: "classification" | "extraction" }>();

const isExtraction = computed(() => props.mode === "extraction");
</script>

<template>
  <div v-for="doc in result.documents" :key="doc.name" class="fr-mb-3w">
    <h3 class="fr-h6">{{ doc.name }}</h3>
    <ExtractionExplorer v-if="isExtraction" :run-id="result.run_id" :pages="(doc.pages as ExtractedPage[])" />
    <ClassificationExplorer v-else :run-id="result.run_id" :pages="(doc.pages as ClassifiedPage[])" />
  </div>
</template>
