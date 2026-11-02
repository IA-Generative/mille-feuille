<script setup lang="ts">
/**
 * Barre de l'assistant pas à pas : indique l'étape en cours (DsfrStepper), rappelle la question de la section
 * et permet d'avancer, de revenir ou de quitter. Chaque étape est une section réelle de l'analyse, éditée juste
 * en dessous ; rien n'est obligatoire, on peut passer une étape.
 */
import { computed } from "vue";

import type { AnalyseSection } from "@/pages/analyse/analyseGroups";

const props = defineProps<{ steps: AnalyseSection[]; current: number }>();
const emit = defineEmits<{ go: [index: number]; quit: [] }>();

const section = computed(() => props.steps[props.current]);
const isLast = computed(() => props.current >= props.steps.length - 1);
</script>

<template>
  <div v-if="section" class="guide-bar">
    <DsfrStepper :steps="steps.map((step) => step.title)" :current-step="current + 1" />
    <p class="guide-bar__hint fr-text--sm fr-mb-0">{{ section.hint }}</p>
    <div class="guide-bar__actions">
      <DsfrButton label="Quitter l'assistant" tertiary no-outline size="sm" @click="emit('quit')" />
      <span class="guide-bar__spacer" />
      <DsfrButton v-if="current > 0" label="Précédent" secondary size="sm" @click="emit('go', current - 1)" />
      <DsfrButton :label="isLast ? 'Terminer' : 'Suivant'" size="sm" @click="isLast ? emit('quit') : emit('go', current + 1)" />
    </div>
  </div>
</template>

<style scoped>
.guide-bar {
  margin-bottom: 2rem;
  padding: 1.25rem 1.5rem;
  border-radius: 1rem;
  background: var(--background-alt-blue-france);
}

.guide-bar__hint {
  margin-top: 0.5rem;
}

.guide-bar__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 1rem;
}

.guide-bar__spacer {
  flex: 1;
}
</style>
