<script setup lang="ts">
/** Signale des liens vers des dossiers non accessibles : un nombre par thème, rien d'autre. */
import type { HiddenLinks } from "@/types/crossSearch";
import { hiddenLabel } from "@/utils/linkGraph";

defineProps<{ links: HiddenLinks[] }>();
</script>

<template>
  <aside v-if="links.length" class="hidden-links">
    <VIcon name="ri-lock-line" />
    <div>
      <p class="fr-text--sm fr-text--bold fr-mb-1v">Il existe aussi des liens avec des dossiers qui ne vous sont pas ouverts</p>
      <ul class="fr-text--sm fr-mb-0">
        <li v-for="link in links" :key="link.themeName ?? ''">{{ hiddenLabel(link.count, link.themeName) }}</li>
      </ul>
    </div>
  </aside>
</template>

<style scoped>
.hidden-links {
  display: flex;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border-radius: 1rem;
  background: var(--background-alt-grey);
}
</style>
