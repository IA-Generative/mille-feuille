<script setup lang="ts">
/** Vue d'ensemble d'une sélection : ce qui relie les dossiers choisis, puis les autres dossiers liés. */
import { computed } from "vue";

import type { CrossSearchResult, Selection } from "@/types/crossSearch";
import { sharedItems } from "@/utils/linkGraph";

const props = defineProps<{ result: CrossSearchResult }>();
const emit = defineEmits<{ select: [selection: Selection]; add: [id: string] }>();

const chosen = computed(() => props.result.dossiers.filter((d) => props.result.anchorIds.includes(d.id)));

/** Chaque paire de dossiers choisis, avec ce qu'ils ont en commun. */
const pairs = computed(() =>
  chosen.value.flatMap((first, index) =>
    chosen.value.slice(index + 1).map((second) => ({
      first,
      second,
      items: sharedItems(props.result, first.id, second.id),
    })),
  ),
);
const linkedPairs = computed(() => pairs.value.filter((pair) => pair.items.length));
const unlinkedPairs = computed(() => pairs.value.filter((pair) => !pair.items.length));

const related = computed(() =>
  props.result.dossiers
    .filter((d) => !props.result.anchorIds.includes(d.id))
    .map((dossier) => {
      const through = props.result.items.filter(
        (item) => item.dossierIds.includes(dossier.id) && item.dossierIds.some((id) => props.result.anchorIds.includes(id)),
      );
      const reaches = chosen.value.filter((c) => through.some((item) => item.dossierIds.includes(c.id))).length;
      return { dossier, through, reaches };
    })
    // Ceux qui relient le plus de dossiers choisis d'abord.
    .sort((a, b) => b.reaches - a.reaches || b.through.length - a.through.length),
);
</script>

<template>
  <section class="summary">
    <template v-if="chosen.length > 1">
      <h2 class="detail__title">Entre vos dossiers</h2>
      <button v-for="pair in linkedPairs" :key="pair.first.id + pair.second.id" type="button" class="detail__row detail__row--stacked" @click="emit('select', { type: 'pair', dossierIds: [pair.first.id, pair.second.id] })">
        <span>{{ pair.first.name }}</span>
        <span>↔ {{ pair.second.name }}</span>
        <span class="detail__hint">par {{ pair.items.map((i) => i.label).join(", ") }}</span>
      </button>
      <p v-for="pair in unlinkedPairs" :key="pair.first.id + pair.second.id" class="detail__caution">
        Aucun lien direct entre « {{ pair.first.name }} » et « {{ pair.second.name }} ».
      </p>
    </template>

    <template v-if="related.length">
      <h2 class="detail__title">Dossiers liés à votre sélection ({{ related.length }})</h2>
      <div v-for="entry in related" :key="entry.dossier.id" class="summary__related">
        <button type="button" class="detail__row detail__row--stacked" @click="emit('select', { type: 'node', id: entry.dossier.id })">
          <span>{{ entry.dossier.name }}</span>
          <span class="detail__hint">par {{ entry.through.map((i) => i.label).join(", ") }}</span>
          <span v-if="entry.reaches > 1" class="fr-badge fr-badge--sm fr-badge--info fr-badge--no-icon">Lié à {{ entry.reaches }} de vos dossiers</span>
        </button>
        <DsfrButton :label="`Ajouter ${entry.dossier.name} à la sélection`" title="Ajouter à la sélection" icon="ri-add-line" icon-only tertiary size="sm" @click="emit('add', entry.dossier.id)" />
      </div>
    </template>
    <p v-else-if="chosen.length === 1" class="fr-text--sm">Aucun autre dossier lié affiché.</p>
  </section>
</template>

<style scoped src="./detail.css"></style>
<style scoped>
.summary {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.summary__related {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
</style>
