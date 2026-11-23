<script setup lang="ts">
import { computed, useId } from "vue";

import { groupLabel } from "@/types/access";

// Choix de groupes parmi ceux de l'utilisateur (on ne peut associer qu'un
// groupe dont on est membre). Les groupes déjà associés mais hors des
// groupes de l'utilisateur sont affichés et retirables par un administrateur.
const selected = defineModel<string[]>({ required: true });
const props = defineProps<{ options: string[]; legend: string; hint?: string; disabled?: boolean; error?: string | null; required?: boolean }>();
const baseId = useId();

const isMember = (g: string) => props.options.includes(g);

const groups = computed(() =>
  [...new Set([...props.options, ...selected.value])].map((group, index) => ({
    group,
    id: `${baseId}-${index}`,
    label: groupLabel(group),
    hint: isMember(group) ? group : `${group} · vous n'en êtes pas membre`,
  })),
);
</script>

<template>
  <DsfrCheckboxSet :disabled="disabled" :error-message="error ?? undefined" :aria-invalid="!!error" small>
    <template #legend>
      {{ legend }}
      <span v-if="required" class="required">&nbsp;*</span>
      <span v-if="hint" class="fr-hint-text">{{ hint }}</span>
    </template>

    <p v-if="options.length === 0" class="fr-text--sm fr-mb-1w">
      Vous n'appartenez à aucun groupe : demandez à un administrateur de vous en attribuer un.
    </p>

    <DsfrCheckbox
      v-for="item in groups"
      :id="item.id"
      :key="item.group"
      v-model="selected"
      :name="`${baseId}-groups`"
      :value="item.group"
      :label="item.label"
      :hint="item.hint"
      small
    />
  </DsfrCheckboxSet>
</template>
