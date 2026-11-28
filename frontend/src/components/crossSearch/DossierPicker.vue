<script setup lang="ts">
/** Choisir les dossiers de départ, par nom, référence ou mot-clé. */
import { computed, onScopeDispose, ref, watch } from "vue";

import { findDossiers, MAX_ANCHORS, MIN_QUERY_LENGTH } from "@/composables/useCrossSearch";
import type { FoundDossier } from "@/types/crossSearch";

const props = defineProps<{ modelValue: string[]; known: FoundDossier[] }>();
const emit = defineEmits<{ "update:modelValue": [ids: string[]] }>();

const query = ref("");
const isOpened = ref(false);
const found = ref<FoundDossier[]>([]);
const status = ref<"loading" | "ready" | "error">("loading");
/** Les noms des dossiers déjà vus, pour nommer la sélection pendant que les liens se calculent. */
const names = ref<Record<string, string>>({});
const suggestions = computed(() => found.value.filter((d) => !props.modelValue.includes(d.id)));
const searchable = computed(() => query.value.trim().length >= MIN_QUERY_LENGTH);
const full = computed(() => props.modelValue.length >= MAX_ANCHORS);

const remember = (dossiers: FoundDossier[]) => dossiers.forEach((d) => (names.value[d.id] = d.name));
watch(() => props.known, remember, { immediate: true });

let timer: ReturnType<typeof setTimeout> | undefined;
let latest = 0;
watch(
  () => query.value.trim(),
  (text) => {
    clearTimeout(timer);
    const request = ++latest;
    found.value = [];
    status.value = "loading";
    if (!searchable.value) return;
    timer = setTimeout(async () => {
      try {
        const dossiers = await findDossiers(text);
        if (request !== latest) return;
        found.value = dossiers;
        status.value = "ready";
      } catch {
        if (request === latest) status.value = "error";
      }
    }, 300);
  },
);
onScopeDispose(() => clearTimeout(timer));

function add(dossier: FoundDossier) {
  remember([dossier]);
  emit("update:modelValue", [...props.modelValue, dossier.id]);
  query.value = "";
  isOpened.value = false;
}

const nameOf = (id: string) => names.value[id] ?? "Dossier";
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
        placeholder="Nom, référence ou mot-clé"
        :disabled="full"
        @focus="isOpened = true"
        @input="isOpened = true"
      />
      <p v-if="full" class="fr-text--xs fr-mt-1v fr-mb-0">{{ MAX_ANCHORS }} dossiers au plus.</p>
      <ul v-if="isOpened && searchable" class="dossier-picker__suggestions">
        <li v-for="dossier in suggestions" :key="dossier.id">
          <button type="button" class="dossier-picker__option" @click="add(dossier)">
            <span>{{ dossier.name }}</span>
            <span class="dossier-picker__reference">{{ dossier.reference }}</span>
          </button>
        </li>
        <li v-if="status === 'loading'" class="dossier-picker__option" role="status">Recherche…</li>
        <li v-else-if="status === 'error'" class="dossier-picker__option" role="alert">La recherche a échoué.</li>
        <li v-else-if="!suggestions.length" class="dossier-picker__option" role="status">Aucun dossier à ajouter.</li>
      </ul>
    </div>

    <ul v-if="modelValue.length" class="fr-tags-group dossier-picker__chosen" aria-label="Dossiers choisis">
      <li v-for="id in modelValue" :key="id">
        <button type="button" class="fr-tag fr-tag--dismiss" :aria-label="`Retirer ${nameOf(id)}`" @click="remove(id)">
          {{ nameOf(id) }}
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
