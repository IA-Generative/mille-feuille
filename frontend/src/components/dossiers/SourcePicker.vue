<script setup lang="ts">
/**
 * Choix de la source d'un dépôt de fichiers : aucune, une source existante, ou une nouvelle (nom + description). Ne
 * crée rien lui-même : il émet le choix, que l'écran résout à l'envoi (une nouvelle source n'existe qu'une fois le
 * dépôt confirmé).
 */
import { computed, useId } from "vue";

import type { DocumentSource, SourceChoice } from "@/types/documentSource";

const props = defineProps<{ sources: DocumentSource[]; id?: string }>();
const choice = defineModel<SourceChoice>({ required: true });

const NEW = "__new__";
const NONE = "__none__";

// Plus d'id en dur : l'`id` fourni par le parent reste prioritaire (AddDocumentsModal le passe encore).
const generatedId = useId();
const selectId = computed(() => props.id ?? generatedId);

const selected = computed({
  get: () => (choice.value.kind === "existing" ? choice.value.id : choice.value.kind === "new" ? NEW : NONE),
  set: (value: string) => {
    if (value === NEW) choice.value = { kind: "new", name: "", description: "" };
    else if (value === NONE) choice.value = { kind: "none" };
    else choice.value = { kind: "existing", id: value };
  },
});

// DsfrSelect attend un tableau d'options { value, text } au lieu de <option> écrits à la main.
const options = computed(() => [
  { value: NONE, text: "Sans source" },
  ...props.sources.map((source) => ({ value: source.id, text: source.name })),
  { value: NEW, text: "+ Nouvelle source…" },
]);

const description = computed(() => {
  const current = choice.value;
  return current.kind === "existing" ? props.sources.find((s) => s.id === current.id)?.description : "";
});

function patchNew(field: "name" | "description", value: string | number | undefined) {
  if (choice.value.kind === "new") choice.value = { ...choice.value, [field]: String(value ?? "") };
}
</script>

<template>
  <div>
    <DsfrSelect
      :model-value="selected"
      :select-id="selectId"
      label="Source des fichiers"
      hint="D'où viennent ces fichiers ? Facultatif."
      :options="options"
      @update:model-value="selected = String($event)"
    />

    <p v-if="description" class="fr-text--sm fr-text-mention--grey fr-mt-1w fr-mb-0">{{ description }}</p>

    <div v-if="choice.kind === 'new'" class="fr-mt-2w">
      <div class="fr-mb-2w">
        <DsfrInput
          :model-value="choice.name"
          label="Nom de la source"
          label-visible
          placeholder="Ex. : Courrier de la préfecture"
          @update:model-value="patchNew('name', $event)"
        />
      </div>
      <DsfrInput
        :model-value="choice.description"
        label="Description"
        hint="Aide à comprendre la pièce : l'IA la reçoit en contexte."
        label-visible
        is-textarea
        @update:model-value="patchNew('description', $event)"
      />
    </div>
  </div>
</template>
