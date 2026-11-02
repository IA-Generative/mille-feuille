<script setup lang="ts">
import type { SuggestedQuestion } from "@/types/dossierPresentation";

// Les questions dont la réponse est déjà prête : un clic l'affiche tout de suite dans la conversation.
defineProps<{ questions: SuggestedQuestion[] }>();
const emit = defineEmits<{ ask: [question: SuggestedQuestion] }>();
</script>

<template>
  <section v-if="questions.length > 0" class="suggested-questions" aria-label="Questions suggérées">
    <p class="suggested-questions__title">Questions fréquentes</p>
    <ul class="suggested-questions__list">
      <li v-for="question in questions" :key="question.id">
        <button type="button" class="suggested-questions__chip" @click="emit('ask', question)">
          {{ question.question }}
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.suggested-questions__title {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-mention-grey);
}

.suggested-questions__list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.suggested-questions__chip {
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 999px;
  background: var(--background-default-grey);
  font: inherit;
  font-size: 0.875rem;
  text-align: left;
  cursor: pointer;
}

.suggested-questions__chip:hover {
  background: var(--background-alt-grey-hover);
}

.suggested-questions__chip:focus-visible {
  outline: 2px solid var(--border-active-blue-france);
  outline-offset: 2px;
}
</style>
