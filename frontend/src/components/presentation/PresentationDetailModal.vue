<script setup lang="ts">
import type { ChatWindowSource } from "@/components/ChatWindow.vue";
import DossierResultsDetail from "@/components/dossiers/DossierResultsDetail.vue";

// Le détail de la classification (répartition par fichier et par page) ou des entités (explorateur avec page source et
// zones encadrées) : les vues qu'ouvraient les cartes de résultats, depuis la présentation.
defineProps<{ opened: boolean; dossierId: string; kind: "label" | "entity" }>();
const emit = defineEmits<{ close: []; viewPage: [source: ChatWindowSource] }>();
</script>

<template>
  <DsfrModal
    :opened="opened"
    :title="kind === 'label' ? 'Classification' : 'Informations extraites'"
    :icon="kind === 'label' ? 'ri-price-tag-3-line' : 'ri-braces-line'"
    :size="kind === 'entity' ? 'lg' : undefined"
    @close="emit('close')"
  >
    <DossierResultsDetail v-if="opened" :key="kind" :dossier-id="dossierId" :kind="kind" @view-page="emit('viewPage', $event)" />
  </DsfrModal>
</template>
