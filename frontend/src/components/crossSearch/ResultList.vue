<script setup lang="ts">
/** Les dossiers trouvés : le plus pertinent d'abord, avec un extrait. On peut en cocher pour voir leurs liens. */
import { ref, watch } from "vue";

import type { FoundDossier } from "@/types/crossSearch";

const props = defineProps<{ dossiers: FoundDossier[] }>();
const emit = defineEmits<{ select: [id: string]; explore: [ids: string[]] }>();

const checked = ref<string[]>([]);
watch(
  () => props.dossiers,
  (dossiers) => (checked.value = checked.value.filter((id) => dossiers.some((d) => d.id === id))),
);
</script>

<template>
  <div>
    <div class="result-list__bar">
      <span class="fr-text--xs fr-mb-0">Cochez des dossiers pour voir leurs liens.</span>
      <DsfrButton :label="`Voir les liens (${checked.length})`" size="sm" :disabled="!checked.length" @click="emit('explore', checked)" />
    </div>
    <ul class="result-list">
      <li v-for="dossier in dossiers" :key="dossier.id" class="result-list__row">
        <div class="fr-checkbox-group fr-checkbox-group--sm">
          <input :id="`pick-${dossier.id}`" v-model="checked" type="checkbox" :value="dossier.id" />
          <label class="fr-label" :for="`pick-${dossier.id}`"><span class="fr-sr-only">Sélectionner {{ dossier.name }}</span></label>
        </div>
        <button type="button" class="result-list__item" @click="emit('select', dossier.id)">
          <span class="fr-text--bold">{{ dossier.name }}</span>
          <span class="result-list__meta">{{ dossier.reference }} · {{ dossier.themeName ?? "Sans thème" }}</span>
          <span v-if="dossier.excerpts[0]" class="result-list__excerpt">« {{ dossier.excerpts[0].text }} »</span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.result-list__bar {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.result-list__row {
  display: flex;
  align-items: flex-start;
  gap: 0.25rem;
}

.result-list__item {
  display: flex;
  flex-direction: column;
  flex: 1;
  gap: 0.25rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  text-align: left;
}

.result-list__meta,
.result-list__excerpt {
  color: var(--text-mention-grey);
  font-size: 0.8125rem;
}
</style>
