<script setup lang="ts">
/** Choisir les dossiers de départ, par nom ou référence. */
import { computed, ref } from "vue";

import { mockDossiersByIds, mockFindDossiers } from "@/composables/useCrossSearch";

const props = defineProps<{ modelValue: string[] }>();
const emit = defineEmits<{ "update:modelValue": [ids: string[]] }>();

const query = ref("");
const isOpened = ref(false);
const chosen = computed(() => mockDossiersByIds(props.modelValue));
const suggestions = computed(() => mockFindDossiers(query.value, props.modelValue));

function add(id: string) {
  emit("update:modelValue", [...props.modelValue, id]);
  query.value = "";
  isOpened.value = false;
}

const remove = (id: string) => emit("update:modelValue", props.modelValue.filter((other) => other !== id));

/** La liste se ferme quand le focus quitte le champ et ses propositions. */
function onFocusOut(event: FocusEvent) {
  const next = event.relatedTarget as Node | null;
  if (!(event.currentTarget as HTMLElement).contains(next)) isOpened.value = false;
}
</script>

<template>
  <div class="dossier-picker">
    <div class="dossier-picker__field" @focusout="onFocusOut" @keydown.esc="isOpened = false">
      <label class="fr-label" for="dossier-picker-input">Ajouter un dossier</label>
      <input
        id="dossier-picker-input"
        v-model="query"
        class="fr-input"
        type="search"
        autocomplete="off"
        placeholder="Nom ou référence"
        @focus="isOpened = true"
        @input="isOpened = true"
      />
      <ul v-if="isOpened" class="dossier-picker__suggestions">
        <li v-for="dossier in suggestions" :key="dossier.id">
          <button type="button" class="dossier-picker__option" @click="add(dossier.id)">
            <span>{{ dossier.name }}</span>
            <span class="dossier-picker__reference">{{ dossier.reference }}</span>
          </button>
        </li>
        <li v-if="!suggestions.length" class="dossier-picker__option">Aucun dossier à ajouter.</li>
      </ul>
    </div>

    <ul v-if="chosen.length" class="fr-tags-group dossier-picker__chosen" aria-label="Dossiers choisis">
      <li v-for="dossier in chosen" :key="dossier.id">
        <button type="button" class="fr-tag fr-tag--dismiss" :aria-label="`Retirer ${dossier.name}`" @click="remove(dossier.id)">
          {{ dossier.name }}
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.dossier-picker {
  margin-bottom: 1rem;
}

.dossier-picker__field {
  position: relative;
  max-width: 40rem;
}

.dossier-picker__suggestions {
  position: absolute;
  z-index: 10;
  right: 0;
  left: 0;
  max-height: 18rem;
  margin: 0.25rem 0 0;
  padding: 0.25rem;
  overflow-y: auto;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-overlap-grey);
  box-shadow: var(--overlap-shadow);
  list-style: none;
}

.dossier-picker__option {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  width: 100%;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  text-align: left;
}

.dossier-picker__reference {
  color: var(--text-mention-grey);
  white-space: nowrap;
}

.dossier-picker__chosen {
  margin-top: 0.75rem;
}
</style>
