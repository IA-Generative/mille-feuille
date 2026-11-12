<script setup lang="ts">
import { useId } from "vue";

import { groupLabel } from "@/types/access";

// Choix de groupes parmi ceux de l'utilisateur (on ne peut associer qu'un
// groupe dont on est membre). `locked` : groupes déjà associés mais hors des
// groupes de l'utilisateur, affichés et retirables par un administrateur.
const selected = defineModel<string[]>({ required: true });
const props = defineProps<{ options: string[]; legend: string; hint?: string; disabled?: boolean; error?: string | null }>();
const errorId = useId();

function toggle(group: string, checked: boolean) {
  selected.value = checked ? [...selected.value, group] : selected.value.filter((g) => g !== group);
}

const isMember = (g: string) => props.options.includes(g);
const all = () => [...new Set([...props.options, ...selected.value])];
</script>

<template>
  <fieldset class="gp" :disabled="disabled" :aria-describedby="error ? errorId : undefined">
    <legend class="gp__legend">{{ legend }}</legend>
    <p v-if="hint" class="gp__hint">{{ hint }}</p>
    <ul class="gp__list">
      <li v-for="g in all()" :key="g">
        <label class="gp__item">
          <input type="checkbox" :checked="selected.includes(g)" @change="toggle(g, ($event.target as HTMLInputElement).checked)" />
          <span :title="g">{{ groupLabel(g) }}</span>
          <span v-if="!isMember(g)" class="gp__note">vous n'en êtes pas membre</span>
        </label>
      </li>
    </ul>
    <p v-if="options.length === 0" class="gp__hint">Vous n'appartenez à aucun groupe : demandez à un administrateur de vous en attribuer un.</p>
    <p v-if="error" :id="errorId" class="fr-error-text fr-mt-1w">{{ error }}</p>
  </fieldset>
</template>

<style scoped>
.gp {
  margin: 0;
  padding: 0;
  border: none;
}

.gp__legend {
  margin-bottom: 0.25rem;
  font-weight: 600;
}

.gp__hint {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.gp__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.gp__item {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.25rem 0;
  cursor: pointer;
}

.gp__note {
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}
</style>
