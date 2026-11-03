<script setup lang="ts">
import { ref } from "vue";

import type { TrackingView } from "@/types/tracking";

// Vues enregistrées sous forme de pastilles (« Mes dossiers », « Non
// affectés »…), plus l'enregistrement de la vue courante sous un nom.
defineProps<{ views: TrackingView[]; activeId: string; modified: boolean }>();
const emit = defineEmits<{
  select: [id: string];
  save: [name: string];
  delete: [id: string];
}>();

const naming = ref(false);
const name = ref("");

function submit() {
  if (!name.value.trim()) return;
  emit("save", name.value);
  name.value = "";
  naming.value = false;
}
</script>

<template>
  <div class="vb">
    <div class="vb__chips" role="group" aria-label="Vues">
      <span v-for="v in views" :key="v.id" class="vb__item">
        <button
          type="button"
          class="vb__chip"
          :class="{ 'vb__chip--on': v.id === activeId }"
          :aria-pressed="v.id === activeId"
          @click="emit('select', v.id)"
        >
          {{ v.name }}<template v-if="v.id === activeId && modified"> <span class="vb__mod" title="Filtres modifiés">•</span><span class="fr-sr-only"> (modifiée)</span></template>
        </button>
        <button v-if="!v.builtIn" type="button" class="vb__del" :aria-label="`Supprimer la vue ${v.name}`" @click="emit('delete', v.id)">
          <VIcon name="ri-close-line" />
        </button>
      </span>
    </div>

    <form v-if="naming" class="vb__form" @submit.prevent="submit">
      <input v-model="name" class="fr-input vb__input" type="text" placeholder="Nom de la vue" aria-label="Nom de la vue" autofocus />
      <button type="submit" class="fr-btn fr-btn--sm" :disabled="!name.trim()">Enregistrer</button>
      <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary" @click="naming = false">Annuler</button>
    </form>
    <button v-else type="button" class="vb__save" @click="naming = true">
      <VIcon name="ri-bookmark-line" /> Enregistrer cette vue
    </button>
  </div>
</template>

<style scoped>
.vb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.vb__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}

.vb__item {
  display: inline-flex;
  align-items: center;
}

.vb__chip {
  --hover: var(--background-alt-grey-hover);
  --active: var(--background-alt-grey-active);
  padding: 0.25rem 0.875rem;
  border: none;
  border-radius: 1rem;
  background: var(--background-alt-grey);
  color: var(--text-default-grey);
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}

.vb__chip--on {
  --hover: var(--background-action-high-blue-france-hover);
  --active: var(--background-action-high-blue-france-active);
  background: var(--background-action-high-blue-france);
  color: var(--text-inverted-blue-france);
  font-weight: 600;
}

.vb__mod {
  font-weight: 700;
}

.vb__del {
  display: flex;
  padding: 0;
  margin-left: 0.125rem;
  border: none;
  background: none;
  color: var(--text-mention-grey);
  cursor: pointer;
}

.vb__save {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.5rem;
  border: none;
  background: none;
  color: var(--text-action-high-blue-france);
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}

.vb__form {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.vb__input {
  padding: 0.25rem 0.5rem;
}
</style>
