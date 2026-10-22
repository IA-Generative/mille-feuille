<script setup lang="ts">
import { computed, ref, watch } from "vue";

import PaginationBar from "@/components/PaginationBar.vue";
import CollectionRow from "@/components/tools/CollectionRow.vue";
import ToolSearchInput from "@/components/tools/ToolSearchInput.vue";
import { useKnowledgeCollections } from "@/composables/useKnowledgeCollections";
import { matchesSearch } from "@/utils/toolSearch";

const opened = defineModel<boolean>("opened", { default: false });

const { collections, selectedIds, save } = useKnowledgeCollections();

// Brouillon : la sélection n'est sauvegardée pour l'analyse qu'à la validation.
const draft = ref<string[]>([...selectedIds.value]);
const query = ref("");
const pageIndex = ref(0);
const pageSize = ref(5);

watch(opened, (isOpened) => {
  if (!isOpened) return;
  draft.value = [...selectedIds.value];
  query.value = "";
  pageIndex.value = 0;
});
watch(query, () => (pageIndex.value = 0));

const filtered = computed(() => collections.value.filter((c) => matchesSearch(query.value, `${c.name} ${c.description}`)));
const page = computed(() => filtered.value.slice(pageIndex.value * pageSize.value, (pageIndex.value + 1) * pageSize.value));

const allFilteredSelected = computed(() => filtered.value.length > 0 && filtered.value.every((c) => draft.value.includes(c.id)));

function toggleAll() {
  const ids = filtered.value.map((c) => c.id);
  draft.value = allFilteredSelected.value
    ? draft.value.filter((id) => !ids.includes(id))
    : [...new Set([...draft.value, ...ids])];
}

function confirm() {
  save(draft.value);
  opened.value = false;
}
</script>

<template>
  <Teleport to="body">
    <DsfrModal
      :opened="opened"
      title="Collections de la base de connaissances"
      size="lg"
      :actions="[
        { label: 'Annuler', secondary: true, onClick: () => (opened = false) },
        { label: `Enregistrer (${draft.length})`, onClick: confirm },
      ]"
      @close="opened = false"
    >
      <p class="fr-text--sm">
        Choisissez les collections que les agents et le chat de cette analyse peuvent interroger. La sélection est
        enregistrée pour l'analyse, avec son historique.
      </p>
      <div class="collection-picker__search">
        <ToolSearchInput v-model="query" placeholder="Rechercher une collection…" />
        <DsfrButton
          :label="allFilteredSelected ? 'Tout retirer' : 'Tout sélectionner'"
          tertiary
          no-outline
          size="sm"
          @click="toggleAll"
        />
      </div>
      <ul class="collection-picker__list">
        <CollectionRow v-for="item in page" :key="item.id" v-model="draft" :collection="item" />
      </ul>
      <p v-if="filtered.length === 0" class="collection-picker__empty">Aucune collection ne correspond à « {{ query }} ».</p>
      <PaginationBar v-model:page-index="pageIndex" v-model:page-size="pageSize" :total="filtered.length" label="Collections par page" />
    </DsfrModal>
  </Teleport>
</template>

<style scoped>
.collection-picker__search {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1rem 0;
}

.collection-picker__list {
  list-style: none;
  margin: 0 0 0.75rem;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.collection-picker__empty {
  margin: 2rem 0;
  text-align: center;
  color: var(--text-mention-grey);
}
</style>
