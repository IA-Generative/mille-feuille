<script setup lang="ts">
/** Lien « retour » avec flèche (VIcon, comme le reste de l'app : les icônes DSFR `fr-icon-*` ne sont pas chargées). */
import type { RouteLocationRaw } from "vue-router";

defineProps<{ to: RouteLocationRaw }>();
</script>

<template>
  <RouterLink :to="to" class="fr-link back-link">
    <VIcon name="ri-arrow-left-line" scale="0.9" />
    <slot />
  </RouterLink>
</template>

<style scoped>
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}
</style>
