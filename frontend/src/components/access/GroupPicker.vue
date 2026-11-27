<script setup lang="ts">
import { computed, useId, watch } from "vue";

import { isGroupId, useGroupNames } from "@/composables/useGroupNames";

// Choix de groupes parmi ceux de l'utilisateur (on ne peut associer qu'un
// groupe dont on est membre). Les groupes déjà associés mais hors des
// groupes de l'utilisateur sont affichés et retirables par un administrateur.
const selected = defineModel<string[]>({ required: true });
const props = defineProps<{ options: string[]; legend: string; hint?: string; disabled?: boolean; error?: string | null; required?: boolean }>();
const baseId = useId();
const { resolve, nameOf } = useGroupNames();
watch(
  () => [...props.options, ...selected.value],
  (keys) => resolve(keys),
  { immediate: true },
);

const isMember = (g: string) => props.options.includes(g);

const groups = computed(() =>
  [...new Set([...props.options, ...selected.value])].map((group, index) => ({
    group,
    id: `${baseId}-${index}`,
    label: nameOf(group),
    // Un identifiant ne dit rien à personne : seul un ancien chemin est affiché à côté du nom.
    hint: [isGroupId(group) ? "" : group, isMember(group) ? "" : "vous n'en êtes pas membre"].filter(Boolean).join(" · "),
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
