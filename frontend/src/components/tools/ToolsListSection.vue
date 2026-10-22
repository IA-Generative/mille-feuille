<script setup lang="ts">
import { ref, watch } from "vue";

import PaginationBar from "@/components/PaginationBar.vue";

const props = defineProps<{ title: string; total: number; resetKey: string }>();

// Pagination côté interface : la section reçoit la page demandée par `pageIndex`/`pageSize` via le slot.
const pageIndex = ref(0);
const pageSize = ref(5);

watch(() => props.resetKey, () => (pageIndex.value = 0));
</script>

<template>
  <section class="tools-list-section">
    <h2 class="fr-h5 tools-list-section__title">
      {{ title }} <span class="tools-list-section__count">{{ total }}</span>
    </h2>
    <slot :start="pageIndex * pageSize" :end="(pageIndex + 1) * pageSize" />
    <slot v-if="total === 0" name="empty" />
    <PaginationBar v-model:page-index="pageIndex" v-model:page-size="pageSize" :total="total" label="Par page" />
  </section>
</template>

<style scoped>
.tools-list-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-top: 0.5rem;
}

.tools-list-section__title {
  margin: 0;
}

.tools-list-section__count {
  margin-left: 0.25rem;
  font-size: 0.875rem;
  font-weight: 400;
  color: var(--text-mention-grey);
}
</style>
