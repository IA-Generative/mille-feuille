<script setup lang="ts">
import { computed, useId } from "vue";

import { groupLabel } from "@/types/access";
import { DsfrCheckboxSet } from "@gouvminint/vue-dsfr";

// Choix de groupes parmi ceux de l'utilisateur (on ne peut associer qu'un
// groupe dont on est membre). `locked` : groupes déjà associés mais hors des
// groupes de l'utilisateur, affichés et retirables par un administrateur.
const selected = defineModel<string[]>({ required: true });
const props = defineProps<{ options: string[]; legend: string; hint?: string; disabled?: boolean; error?: string | null }>();
const baseId = useId();

const isMember = (g: string) => props.options.includes(g);

// Mêmes groupes qu'avant : ceux de l'utilisateur + ceux déjà associés (non-membre).
const checkboxes = computed(() =>
[...new Set([...props.options, ...selected.value])].map((g) => ({
  id: `${baseId}-${g}`,
  name: `${baseId}-groups`,
  value: g,
  label: groupLabel(g),
  // L'identifiant technique et la mention « non-membre » deviennent l'aide DSFR du choix.
  hint: isMember(g) ? g : `${g} · vous n'en êtes pas membre`,
})),
);
</script>

<template>
  <p v-if="options.length === 0" class="fr-text--sm">
    Vous n'appartenez à aucun groupe : demandez à un administrateur de vous en attribuer un.
  </p>
  <DsfrCheckboxSet
    v-else
    v-model="selected"
    :options="checkboxes"
    :disabled="disabled"
    :error-message="error ?? undefined"
    :aria-invalid="!!error"
    small
  >
    <template #legend>
      {{ legend }}
      <span v-if="hint" class="fr-hint-text">{{ hint }}</span>
    </template>
  </DsfrCheckboxSet>
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
