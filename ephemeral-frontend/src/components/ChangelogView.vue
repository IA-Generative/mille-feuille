<script setup lang="ts">
import { onMounted, ref } from "vue";

import { renderMarkdown } from "@/markdown";

const html = ref("");
const error = ref("");

onMounted(async () => {
  try {
    const response = await fetch("/CHANGELOG.md");
    if (!response.ok) throw new Error(String(response.status));
    html.value = renderMarkdown(await response.text());
  } catch {
    error.value = "Impossible de charger le journal des versions.";
  }
});
</script>

<template>
  <p v-if="error" class="fr-error-text">{{ error }}</p>
  <!-- eslint-disable-next-line vue/no-v-html -- fichier statique du service, rendu par renderMarkdown (échappé) -->
  <div v-else v-html="html"></div>
</template>
