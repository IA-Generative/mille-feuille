<script setup lang="ts">
import type { RoutingMode } from "@/types/llmModel";

defineProps<{ mode: RoutingMode }>();
const emit = defineEmits<{ change: [mode: RoutingMode] }>();

const options: { value: RoutingMode; title: string; hint: string }[] = [
  { value: "first", title: "Un seul modèle", hint: "Le premier modèle actif fait tout." },
  { value: "auto", title: "Auto", hint: "Le modèle est choisi selon les capacités que la demande demande." },
];
</script>

<template>
  <section class="mode-card" aria-labelledby="mode-title">
    <h3 id="mode-title" class="mode-card__title">Choix du modèle</h3>
    <div class="mode-card__options" role="group" aria-labelledby="mode-title">
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        class="mode-card__option"
        :class="{ 'mode-card__option--on': mode === option.value }"
        :aria-pressed="mode === option.value"
        @click="emit('change', option.value)"
      >
        <strong>{{ option.title }}</strong>
        <span>{{ option.hint }}</span>
      </button>
    </div>
    <p class="mode-card__note">Un modèle choisi sur une conversation ou un agent reste prioritaire.</p>
  </section>
</template>

<style scoped>
.mode-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.mode-card__title {
  margin: 0;
  font-size: 1rem;
}

.mode-card__options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.75rem;
}

.mode-card__option {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.875rem 1rem;
  border: 1px solid var(--border-default-grey, #ddd);
  border-radius: 0.875rem;
  background: var(--background-default-grey, #fff);
  text-align: left;
  cursor: pointer;
}

.mode-card__option span {
  font-size: 0.875rem;
  color: var(--text-mention-grey, #666);
}

.mode-card__option--on {
  border-color: var(--background-action-high-blue-france, #000091);
  box-shadow: inset 0 0 0 1px var(--background-action-high-blue-france, #000091);
}

.mode-card__note {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--text-mention-grey, #666);
}
</style>
