<script setup lang="ts">
import { nextTick, ref, useId } from "vue";

import type { CustomField, CustomValue } from "@/types/tracking";
import { formatValue, parseInput, validateValue } from "@/utils/trackingFields";

// Édition en cellule d'un champ personnalisé : clic ou Entrée pour éditer,
// Entrée / sortie du champ pour valider, Échap pour annuler. La validation
// suit le type du champ ; une valeur invalide reste en édition avec son message.
const props = defineProps<{ field: CustomField; value: CustomValue | undefined; label: string }>();
const emit = defineEmits<{
  /** Renvoie le message d'erreur du serveur (ou `null`) via le callback. */
  save: [value: CustomValue, done: (error: string | null) => void];
}>();

const editing = ref(false);
// Un <input type="number"> lié par v-model fournit un nombre, les autres une chaîne.
const draft = ref<string | number>("");
const error = ref<string | null>(null);
const errorId = useId();
const input = ref<HTMLInputElement | HTMLSelectElement | null>(null);

function start() {
  draft.value = props.value === null || props.value === undefined ? "" : String(props.value);
  error.value = null;
  editing.value = true;
  nextTick(() => input.value?.focus());
}

function cancel() {
  editing.value = false;
  error.value = null;
}

function commit(raw: string | number | boolean) {
  const value: CustomValue = typeof raw === "boolean" ? raw : parseInput(props.field, raw);
  const invalid = validateValue(props.field, value);
  if (invalid) {
    error.value = invalid;
    return;
  }
  if (value === (props.value ?? null)) return cancel();
  emit("save", value, (serverError) => {
    if (serverError) error.value = serverError;
    else cancel();
  });
}
</script>

<template>
  <!-- Booléen : une case, enregistrée au clic -->
  <input
    v-if="field.type === 'boolean'"
    type="checkbox"
    :checked="Boolean(value)"
    :aria-label="`${field.name} — ${label}`"
    @change="commit(($event.target as HTMLInputElement).checked)"
  />

  <div v-else-if="editing" class="cell">
    <select
      v-if="field.type === 'choice'"
      ref="input"
      v-model="draft"
      class="fr-select cell__input"
      :aria-label="`${field.name} — ${label}`"
      :aria-invalid="!!error"
      :aria-describedby="error ? errorId : undefined"
      @change="commit(draft)"
      @keydown.esc="cancel"
      @blur="cancel"
    >
      <option v-if="!field.required" value="">—</option>
      <option v-for="c in field.choices" :key="c" :value="c">{{ c }}</option>
    </select>
    <input
      v-else
      ref="input"
      v-model="draft"
      class="fr-input cell__input"
      :type="field.type === 'date' ? 'date' : field.type === 'text' ? 'text' : 'number'"
      :step="field.type === 'amount' ? '0.01' : 'any'"
      :aria-label="`${field.name} — ${label}`"
      :aria-invalid="!!error"
      :aria-describedby="error ? errorId : undefined"
      @keydown.enter.prevent="commit(draft)"
      @keydown.esc="cancel"
      @blur="commit(draft)"
    />
    <p v-if="error" :id="errorId" class="fr-error-text fr-mt-1v" role="alert">{{ error }}</p>
  </div>

  <button v-else type="button" class="cell__value" :aria-label="`Modifier ${field.name} — ${label}`" @click="start">
    {{ formatValue(field, value) }}
  </button>
</template>

<style scoped>
.cell {
  min-width: 8rem;
}

.cell__input {
  padding: 0.25rem 0.5rem;
}

.cell__value {
  width: 100%;
  min-height: 1.5rem;
  padding: 0.125rem 0.375rem;
  border: 1px dashed transparent;
  border-radius: 0.25rem;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: text;
}

.cell__value:hover,
.cell__value:focus-visible {
  border-color: var(--border-default-grey);
  background: var(--background-alt-grey);
}
</style>
