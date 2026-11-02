<script setup lang="ts">
import { computed, ref, watch } from "vue";

// La liste des questions fréquentes d'une analyse : ajouter, modifier, retirer, ordonner. Rien n'est enregistré avant le
// bouton : un enregistrement = une version, pas une version par frappe.
const props = defineProps<{ modelValue: string[]; saving?: boolean }>();
const emit = defineEmits<{ save: [questions: string[]] }>();

const draft = ref<string[]>([...props.modelValue]);
const newQuestion = ref("");

watch(
  () => props.modelValue,
  (value) => {
    draft.value = [...value];
  },
);

const cleaned = computed(() => draft.value.map((question) => question.trim()).filter(Boolean));
const isChanged = computed(
  () => cleaned.value.length !== props.modelValue.length || cleaned.value.some((q, i) => q !== props.modelValue[i]),
);

function add() {
  const text = newQuestion.value.trim();
  if (!text) return;
  draft.value.push(text);
  newQuestion.value = "";
}

function remove(index: number) {
  draft.value.splice(index, 1);
}

function move(index: number, by: -1 | 1) {
  const target = index + by;
  if (target < 0 || target >= draft.value.length) return;
  [draft.value[index], draft.value[target]] = [draft.value[target], draft.value[index]];
}

function reset() {
  draft.value = [...props.modelValue];
  newQuestion.value = "";
}

function save() {
  add();
  emit("save", cleaned.value);
}
</script>

<template>
  <div class="questions-editor">
    <ul v-if="draft.length > 0" class="questions-editor__list">
      <li v-for="(_, index) in draft" :key="index" class="questions-editor__row">
        <input
          v-model="draft[index]"
          type="text"
          class="fr-input questions-editor__input"
          maxlength="300"
          :aria-label="`Question ${index + 1}`"
        />
        <button
          type="button"
          class="questions-editor__icon"
          :disabled="index === 0"
          :aria-label="`Monter la question ${index + 1}`"
          @click="move(index, -1)"
        >
          <VIcon name="ri-arrow-up-s-line" />
        </button>
        <button
          type="button"
          class="questions-editor__icon"
          :disabled="index === draft.length - 1"
          :aria-label="`Descendre la question ${index + 1}`"
          @click="move(index, 1)"
        >
          <VIcon name="ri-arrow-down-s-line" />
        </button>
        <button
          type="button"
          class="questions-editor__icon"
          :aria-label="`Retirer la question ${index + 1}`"
          @click="remove(index)"
        >
          <VIcon name="ri-delete-bin-line" />
        </button>
      </li>
    </ul>
    <p v-else class="questions-editor__empty">Aucune question fréquente pour l'instant.</p>

    <form class="questions-editor__add" @submit.prevent="add">
      <input
        v-model="newQuestion"
        type="text"
        class="fr-input"
        maxlength="300"
        placeholder="Ajouter une question, par exemple « Quel est le montant du loyer ? »"
        aria-label="Nouvelle question"
      />
      <DsfrButton label="Ajouter" secondary type="submit" :disabled="!newQuestion.trim()" />
    </form>

    <div class="questions-editor__actions">
      <DsfrButton label="Enregistrer" :disabled="(!isChanged && !newQuestion.trim()) || saving" @click="save" />
      <DsfrButton v-if="isChanged" label="Annuler" tertiary @click="reset" />
    </div>
  </div>
</template>

<style scoped>
.questions-editor {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.questions-editor__list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.questions-editor__row {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.questions-editor__input {
  flex: 1;
}

.questions-editor__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-mention-grey);
  cursor: pointer;
}

.questions-editor__icon:hover:not(:disabled) {
  background: var(--background-alt-grey-hover);
  color: var(--text-default-grey);
}

.questions-editor__icon:disabled {
  opacity: 0.35;
  cursor: default;
}

.questions-editor__empty {
  margin: 0;
  color: var(--text-mention-grey);
}

.questions-editor__add {
  display: flex;
  gap: 0.5rem;
}

.questions-editor__add .fr-input {
  flex: 1;
}

.questions-editor__actions {
  display: flex;
  gap: 0.5rem;
}
</style>
