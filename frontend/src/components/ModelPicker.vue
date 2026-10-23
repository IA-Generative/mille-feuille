<script setup lang="ts">
/**
 * Sélecteur de modèle LLM, le même partout dans l'application : un bouton
 * (nom du modèle + chevron) qui ouvre une liste flottante avec le choix
 * courant coché. Charge lui-même le catalogue du hub (useModels), il suffit de
 * lui lier la valeur. "" = pas de préférence (modèle par défaut du hub).
 * Construit avec les classes et jetons du DSFR plutôt qu'avec un <select>.
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { useModels } from "@/composables/useModels";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    /** Libellé accessible ; affiché au-dessus du bouton si `showLabel`. */
    label?: string;
    showLabel?: boolean;
    disabled?: boolean;
    /** Côté d'ancrage de la liste : "right" quand le bouton est près du bord droit. */
    align?: "left" | "right";
    /** Le bouton occupe toute la largeur du conteneur (formulaires). */
    block?: boolean;
  }>(),
  { label: "Modèle", showLabel: false, disabled: false, align: "left", block: false },
);
const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const { models, fetchModels } = useModels();
onMounted(fetchModels);

const options = computed(() => [
  { value: "", text: "Modèle par défaut" },
  ...models.value.map((id) => ({ value: id, text: id })),
]);

const rootRef = ref<HTMLElement | null>(null);
const triggerRef = ref<HTMLElement | null>(null);
const isOpen = ref(false);
const listId = `model-picker-${Math.random().toString(36).slice(2, 8)}`;

const selectedText = computed(
  () => options.value.find((option) => option.value === props.modelValue)?.text ?? props.modelValue,
);

function open() {
  isOpen.value = true;
}

function close() {
  isOpen.value = false;
}

function toggle() {
  if (props.disabled) return;
  if (isOpen.value) close();
  else open();
}

function select(value: string, event?: Event) {
  // Le clic ne doit pas remonter : l'option est retirée du DOM dès la fermeture, et une modale (DsfrModal) qui
  // reçoit un clic dont la cible n'est plus dans son corps se ferme, pensant à un clic à l'extérieur.
  event?.stopPropagation();
  close();
  if (value !== props.modelValue) emit("update:modelValue", value);
}

function onDocumentClick(event: MouseEvent) {
  if (isOpen.value && rootRef.value && !rootRef.value.contains(event.target as Node)) close();
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && isOpen.value) {
    // Échap ne ferme que la liste, pas la modale qui la contient.
    event.stopPropagation();
    close();
    triggerRef.value?.focus();
  }
}

onMounted(() => document.addEventListener("click", onDocumentClick));
onBeforeUnmount(() => document.removeEventListener("click", onDocumentClick));
</script>

<template>
  <div ref="rootRef" class="model-picker" :class="{ 'model-picker--block': block }" @keydown="onKeydown">
    <span v-if="showLabel" class="fr-label model-picker__label">{{ label }}</span>
    <button
      ref="triggerRef"
      type="button"
      class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm model-picker__trigger"
      :class="{ 'model-picker__trigger--block': block }"
      :aria-label="label"
      aria-haspopup="listbox"
      :aria-expanded="isOpen"
      :aria-controls="listId"
      :disabled="disabled"
      @click="toggle"
    >
      <span class="model-picker__value">{{ selectedText }}</span>
      <VIcon name="ri-arrow-down-s-line" class="model-picker__chevron" :class="{ 'model-picker__chevron--open': isOpen }" />
    </button>

    <ul
      v-if="isOpen"
      :id="listId"
      class="model-picker__menu"
      :class="{ 'model-picker__menu--right': align === 'right', 'model-picker__menu--block': block }"
      role="listbox"
      :aria-label="label"
    >
      <li
        v-for="option in options"
        :key="option.value"
        role="option"
        :aria-selected="option.value === modelValue"
        class="model-picker__option"
        :class="{ 'model-picker__option--selected': option.value === modelValue }"
        tabindex="0"
        @click="select(option.value, $event)"
        @keydown.enter.prevent="select(option.value, $event)"
        @keydown.space.prevent="select(option.value, $event)"
      >
        <span class="model-picker__option-text">{{ option.text }}</span>
        <VIcon v-if="option.value === modelValue" name="ri-check-line" />
      </li>
    </ul>
  </div>
</template>

<style scoped>
.model-picker {
  position: relative;
  display: inline-block;
  max-width: 100%;
}

.model-picker--block {
  display: block;
}

.model-picker__label {
  display: block;
  margin-bottom: 0.5rem;
}

.model-picker__trigger--block {
  width: 100%;
  justify-content: space-between;
  border: 1px solid var(--border-default-grey);
}

.model-picker__trigger {
  max-width: 100%;
  gap: 0.25rem;
  font-weight: 600;
  font-size: 1rem;
  color: var(--text-title-grey);
}

.model-picker__value {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-picker__chevron {
  flex-shrink: 0;
  transition: transform 0.15s ease;
}

.model-picker__chevron--open {
  transform: rotate(180deg);
}

/* Ancrée sous le bouton (le wrapper est en position: relative). */
.model-picker__menu {
  position: absolute;
  z-index: 2000;
  top: calc(100% + 0.25rem);
  left: 0;
  min-width: 14rem;
  max-width: min(22rem, 90vw);
  max-height: 20rem;
  overflow-y: auto;
  margin: 0;
  padding: 0.375rem;
  list-style: none;
  background: var(--background-overlap-grey);
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
}

.model-picker__menu--right {
  left: auto;
  right: 0;
}

.model-picker__menu--block {
  right: 0;
  max-width: none;
}

.model-picker__option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0.625rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-size: 0.9rem;
  color: var(--text-default-grey);
}

.model-picker__option:hover,
.model-picker__option:focus-visible {
  background: var(--background-overlap-grey-hover);
  outline: none;
}

.model-picker__option--selected {
  font-weight: 600;
}

.model-picker__option-text {
  overflow-wrap: anywhere;
}
</style>
