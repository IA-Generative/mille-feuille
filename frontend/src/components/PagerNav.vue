<script setup lang="ts">
import { computed } from "vue";

// La pagination du DSFR (`DsfrPagination`) compte les pages **à partir de 0**, alors que les API de la plateforme
// (`page=1`) comptent à partir de 1. Ce composant fait la conversion une fois pour toutes : on lui donne un numéro de
// page à partir de 1 et il rend le même numéro. (Brancher `DsfrPagination` directement sur un numéro de page de l'API
// montre la mauvaise page active, et « page 1 » demande la page 0 : la liste apparaît vide.)
const props = defineProps<{ pageCount: number }>();
const page = defineModel<number>("page", { required: true });

const pages = computed(() =>
  Array.from({ length: Math.max(1, props.pageCount) }, (_, i) => ({ label: String(i + 1), title: `Page ${i + 1}` })),
);
</script>

<template>
  <DsfrPagination
    v-if="pageCount > 1"
    :pages="pages"
    :current-page="page - 1"
    @update:current-page="(index: number) => (page = index + 1)"
  />
</template>
