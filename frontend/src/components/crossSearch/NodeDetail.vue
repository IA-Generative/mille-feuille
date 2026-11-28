<script setup lang="ts">
/** Un point commun choisi (ou les dossiers non accessibles d'un thème) : les dossiers qu'il relie. */
import { computed } from "vue";

import { reasonOf, type CrossSearchResult, type HiddenLinks, type Selection, type SharedItem } from "@/types/crossSearch";
import { hiddenNodeId } from "@/utils/linkGraph";

const props = defineProps<{ result: CrossSearchResult; item?: SharedItem; hidden?: HiddenLinks }>();
const emit = defineEmits<{ select: [selection: Selection] }>();

const targetId = computed(() => props.item?.id ?? hiddenNodeId(props.hidden?.themeName ?? null));
const linked = computed(() => {
  const ids = (props.item ?? props.hidden)?.dossierIds ?? [];
  return props.result.dossiers.filter((d) => ids.includes(d.id));
});
</script>

<template>
  <h2 class="fr-h6 fr-mb-0">{{ item ? (item.uncertain ? "≈ " : "") + item.label : "Dossiers non accessibles" }}</h2>
  <p v-if="item" class="fr-text--sm fr-mb-0">{{ reasonOf(item).reason }}</p>
  <p v-else-if="hidden" class="fr-text--sm fr-mb-0">
    {{ hidden.count }} dans le thème « {{ hidden.themeName ?? "Sans thème" }} ». Leur contenu et la nature du lien ne sont
    pas communiqués.
  </p>

  <h3 class="detail__title">Lié à {{ linked.length }} dossier(s)</h3>
  <button v-for="dossier in linked" :key="dossier.id" type="button" class="detail__row" @click="emit('select', { type: 'link', dossierId: dossier.id, targetId })">
    <span>{{ dossier.name }}</span>
    <span class="detail__hint">Pourquoi ?</span>
  </button>
</template>

<style scoped src="./detail.css"></style>
