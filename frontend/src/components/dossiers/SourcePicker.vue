<script setup lang="ts">
/**
 * Choix de la source d'un dépôt de fichiers : aucune, une source existante, ou une nouvelle (nom + description). Ne
 * crée rien lui-même : il émet le choix, que l'écran résout à l'envoi (une nouvelle source n'existe qu'une fois le
 * dépôt confirmé).
 */
import { computed } from "vue";

import type { DocumentSource, SourceChoice } from "@/types/documentSource";

const props = defineProps<{ sources: DocumentSource[]; id?: string }>();
const choice = defineModel<SourceChoice>({ required: true });

const NEW = "__new__";
const NONE = "__none__";

const selected = computed({
  get: () => (choice.value.kind === "existing" ? choice.value.id : choice.value.kind === "new" ? NEW : NONE),
  set: (value: string) => {
    if (value === NEW) choice.value = { kind: "new", name: "", description: "" };
    else if (value === NONE) choice.value = { kind: "none" };
    else choice.value = { kind: "existing", id: value };
  },
});

const description = computed(() => {
  const current = choice.value;
  return current.kind === "existing" ? props.sources.find((s) => s.id === current.id)?.description : "";
});

function patchNew(patch: Partial<{ name: string; description: string }>) {
  if (choice.value.kind === "new") choice.value = { ...choice.value, ...patch };
}
</script>

<template>
  <div class="source-picker">
    <div class="fr-select-group">
      <label class="fr-label" :for="id ?? 'source-picker'">
        Source des fichiers
        <span class="fr-hint-text">D'où viennent ces fichiers ? Facultatif.</span>
      </label>
      <select :id="id ?? 'source-picker'" v-model="selected" class="fr-select">
        <option :value="NONE">Sans source</option>
        <option v-for="source in sources" :key="source.id" :value="source.id">{{ source.name }}</option>
        <option :value="NEW">+ Nouvelle source…</option>
      </select>
    </div>

    <p v-if="description" class="fr-text--sm source-picker__description">{{ description }}</p>

    <div v-if="choice.kind === 'new'" class="source-picker__new">
      <DsfrInput
        :model-value="choice.name"
        label="Nom de la source"
        label-visible
        placeholder="Ex. : Courrier de la préfecture"
        @update:model-value="patchNew({ name: $event })"
      />
      <DsfrInput
        :model-value="choice.description"
        label="Description"
        hint="Aide à comprendre la pièce : l'IA la reçoit en contexte."
        label-visible
        is-textarea
        @update:model-value="patchNew({ description: $event })"
      />
    </div>
  </div>
</template>

<style scoped>
.source-picker__description {
  margin: 0.5rem 0 0;
  color: var(--text-mention-grey);
}

.source-picker__new {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-top: 1rem;
  padding: 1rem;
  border: 1px solid var(--border-default-grey);
  border-left: 3px solid var(--border-action-high-blue-france);
  border-radius: 0.5rem;
}
</style>
