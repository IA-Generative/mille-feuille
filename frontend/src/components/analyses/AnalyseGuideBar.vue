<script setup lang="ts">
/**
 * Barre de l'assistant pas à pas : indique l'étape en cours (DsfrStepper), rappelle la question de la section
 * et permet d'avancer, de revenir ou de quitter. Chaque étape est une section réelle de l'analyse, éditée juste
 * en dessous ; rien n'est obligatoire, on peut passer une étape.
 */
import { computed, nextTick, onMounted, ref } from "vue";

import type { AnalyseSection } from "@/pages/analyse/analyseGroups";

const props = defineProps<{ steps: AnalyseSection[]; current: number }>();
const emit = defineEmits<{ go: [index: number]; quit: [] }>();

const section = computed(() => props.steps[props.current]);
const isLast = computed(() => props.current >= props.steps.length - 1);

const root = ref<HTMLElement>();
const nextButton = ref<{ $el: HTMLElement } | null>(null);

// À l'ouverture (création ou bouton) : le focus arrive sur la barre, annoncée comme une région nommée.
onMounted(() => root.value?.focus());

async function goPrevious() {
  emit("go", props.current - 1);
  // « Précédent » disparaît à la première étape : sans cela, le focus tomberait sur la page.
  if (props.current - 1 === 0) {
    await nextTick();
    nextButton.value?.$el.focus();
  }
}
</script>

<template>
  <section v-if="section" ref="root" class="guide-bar" tabindex="-1" aria-label="Assistant pas à pas">
    <!-- Annonce le changement d'étape aux lecteurs d'écran (le titre du stepper ne l'annonce pas de lui-même). -->
    <p class="fr-sr-only" role="status">Étape {{ current + 1 }} sur {{ steps.length }} : {{ section.title }}</p>
    <DsfrStepper :steps="steps.map((step) => step.title)" :current-step="current + 1" />
    <ul v-if="section.checks" class="fr-text--sm fr-mb-0 guide-bar__checks">
      <li v-for="check in section.checks" :key="check.label">
        <span v-if="check.optional">(Optionnel) </span> {{ check.label }}
      </li>
    </ul>
    <p v-else class="guide-bar__hint fr-text--sm fr-mb-0">{{ section.hint }}</p>
    <div class="guide-bar__actions">
      <DsfrButton label="Quitter l'assistant" tertiary no-outline size="sm" @click="emit('quit')" />
      <span class="guide-bar__spacer" />
      <DsfrButton v-if="current > 0" label="Précédent" secondary size="sm" @click="goPrevious" />
      <DsfrButton
        ref="nextButton"
        :label="isLast ? 'Terminer' : 'Suivant'"
        size="sm"
        @click="isLast ? emit('quit') : emit('go', current + 1)"
      />
    </div>
  </section>
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

.guide-bar__checks {
  margin-top: 0.5rem;
  padding-left: 1.25rem;
}

.guide-bar__spacer {
  flex: 1;
}
</style>
