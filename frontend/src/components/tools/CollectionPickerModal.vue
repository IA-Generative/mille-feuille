<script setup lang="ts">
import { computed, ref, watch } from "vue";

import PaginationBar from "@/components/PaginationBar.vue";
import CollectionRow from "@/components/tools/CollectionRow.vue";
import CollectionSourceChoice from "@/components/tools/CollectionSourceChoice.vue";
import ToolSearchInput from "@/components/tools/ToolSearchInput.vue";
import { useKnowledgeSources } from "@/composables/useKnowledgeSources";
import { useSourceCollections } from "@/composables/useSourceCollections";
import type { CollectionRef, KnowledgeCollection } from "@/types/knowledge";

const props = defineProps<{ chosen: CollectionRef[]; error: string }>();
const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ save: [refs: CollectionRef[]] }>();

const { sources, fetchSources } = useKnowledgeSources();

// Brouillon : le choix n'est enregistré pour l'analyse qu'à la validation.
const key = (sourceId: string, collectionId: string) => `${sourceId}::${collectionId}`;
const draft = ref<CollectionRef[]>([]);
const sourceId = ref("");
const query = ref("");
const pageIndex = ref(0);
const pageSize = ref(5);

const { collections, total, loading, error: listError, load } = useSourceCollections(computed(() => sourceId.value || undefined));

const isChosen = (collection: KnowledgeCollection) =>
  draft.value.some((ref) => ref.sourceId === sourceId.value && ref.collectionId === collection.id);

function toggle(collection: KnowledgeCollection) {
  draft.value = isChosen(collection)
    ? draft.value.filter((r) => key(r.sourceId, r.collectionId) !== key(sourceId.value, collection.id))
    : [...draft.value, { sourceId: sourceId.value, collectionId: collection.id }];
}

const allPageChosen = computed(() => collections.value.length > 0 && collections.value.every(isChosen));

function togglePage() {
  const onPage = collections.value.map((c) => key(sourceId.value, c.id));
  draft.value = allPageChosen.value
    ? draft.value.filter((r) => !onPage.includes(key(r.sourceId, r.collectionId)))
    : [...draft.value, ...collections.value.filter((c) => !isChosen(c)).map((c) => ({ sourceId: sourceId.value, collectionId: c.id }))];
}

watch(opened, async (isOpened) => {
  if (!isOpened) return;
  draft.value = props.chosen.map((r) => ({ ...r }));
  query.value = "";
  pageIndex.value = 0;
  await fetchSources();
  if (!sources.value.some((s) => s.id === sourceId.value)) sourceId.value = sources.value[0]?.id ?? "";
  await load(query.value, 1, pageSize.value);
});

// La recherche part chez le fournisseur : on attend que la personne ait fini de taper.
let typing: ReturnType<typeof setTimeout> | undefined;
watch(query, () => {
  pageIndex.value = 0;
  clearTimeout(typing);
  typing = setTimeout(() => load(query.value, 1, pageSize.value), 300);
});
watch(sourceId, () => {
  if (!opened.value) return;
  pageIndex.value = 0;
  load(query.value, 1, pageSize.value);
});
watch([pageIndex, pageSize], () => opened.value && load(query.value, pageIndex.value + 1, pageSize.value));
</script>

<template>
  <Teleport to="body">
    <DsfrModal
      :opened="opened"
      title="Collections de la base de connaissances"
      size="lg"
      :actions="[
        { label: 'Annuler', secondary: true, onClick: () => (opened = false) },
        { label: `Enregistrer (${draft.length})`, onClick: () => emit('save', draft) },
      ]"
      @close="opened = false"
    >
      <p class="fr-text--sm">
        Choisissez les collections que les agents et le chat de cette analyse peuvent interroger. Vous ne voyez que celles
        auxquelles vous avez droit chez le fournisseur. Le choix est enregistré pour l'analyse, avec son historique.
      </p>
      <DsfrAlert v-if="error" type="error" small :description="error" class="fr-mb-2w" />

      <p v-if="sources.length === 0" class="collection-picker__empty">
        Aucune source de connaissances.
        <RouterLink to="/outils" @click="opened = false">Ajoutez-en une dans « Mes outils »</RouterLink>.
      </p>
      <template v-else>
        <CollectionSourceChoice v-model="sourceId" :sources="sources" />
        <div class="collection-picker__search">
          <ToolSearchInput v-model="query" placeholder="Rechercher une collection…" />
          <DsfrButton
            :label="allPageChosen ? 'Retirer la page' : 'Sélectionner la page'"
            tertiary
            no-outline
            size="sm"
            :disabled="collections.length === 0"
            @click="togglePage"
          />
        </div>
        <DsfrAlert v-if="listError" type="warning" small :description="listError" class="fr-mb-2w" />
        <ul class="collection-picker__list" :aria-busy="loading">
          <CollectionRow
            v-for="item in collections"
            :key="item.id"
            :collection="item"
            :checked="isChosen(item)"
            @toggle="toggle(item)"
          />
        </ul>
        <p v-if="!loading && !listError && collections.length === 0" class="collection-picker__empty">
          {{ query ? `Aucune collection ne correspond à « ${query} ».` : "Cette source n'a aucune collection pour vous." }}
        </p>
        <PaginationBar v-model:page-index="pageIndex" v-model:page-size="pageSize" :total="total" label="Collections par page" />
      </template>
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
