<script setup lang="ts">
import { ref } from "vue";

import MarkdownText from "@/components/MarkdownText.vue";

// Le résumé du dossier : quelques lignes d'abord, la suite à un clic.
defineProps<{ content: string }>();

const expanded = ref(false);
const LINES = 5;
</script>

<template>
  <div class="presentation-summary">
    <MarkdownText :content="content" :lines="expanded ? 0 : LINES" class="presentation-summary__text" />
    <button type="button" class="presentation-summary__toggle" :aria-expanded="expanded" @click="expanded = !expanded">
      {{ expanded ? "Réduire" : "Lire la suite" }}
    </button>
  </div>
</template>

<style scoped>
.presentation-summary__text {
  line-height: 1.6;
}

.presentation-summary__toggle {
  margin-top: 0.25rem;
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  font-size: 0.875rem;
  color: var(--text-action-high-blue-france);
  cursor: pointer;
}

.presentation-summary__toggle:hover {
  text-decoration: underline;
}
</style>
