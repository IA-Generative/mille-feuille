<script setup lang="ts">
/**
 * Pagination d'une liste affichée côté interface : choix du nombre d'éléments par page (5, 10 ou 20) et navigation.
 * Rien ne s'affiche tant que la liste tient dans la plus petite page.
 */
import { computed } from "vue";

import { PAGE_SIZE_OPTIONS } from "@/composables/usePageSize";

const props = defineProps<{ total: number; label?: string }>();

// Index de page à partir de 0, comme DsfrPagination.
const pageIndex = defineModel<number>("pageIndex", { required: true });
const pageSize = defineModel<number>("pageSize", { required: true });

const pageCount = computed(() => Math.max(1, Math.ceil(props.total / pageSize.value)));
const pages = computed(() =>
  Array.from({ length: pageCount.value }, (_, i) => ({ label: String(i + 1), title: `Page ${i + 1}` })),
);
const from = computed(() => Math.min(props.total, pageIndex.value * pageSize.value + 1));
const to = computed(() => Math.min(props.total, (pageIndex.value + 1) * pageSize.value));
const selectId = `page-size-${Math.random().toString(36).slice(2, 8)}`;

function changeSize(event: Event) {
  pageSize.value = Number((event.target as HTMLSelectElement).value);
  pageIndex.value = 0;
}
</script>

<template>
  <div v-if="total > PAGE_SIZE_OPTIONS[0]" class="pagination-bar">
    <div class="pagination-bar__summary fr-text--sm">
      <span>{{ from }}–{{ to }} sur {{ total }}</span>
      <label :for="selectId" class="pagination-bar__size">
        {{ label ?? "Par page" }}
        <select :id="selectId" class="fr-select pagination-bar__select" :value="pageSize" @change="changeSize">
          <option v-for="size in PAGE_SIZE_OPTIONS" :key="size" :value="size">{{ size }}</option>
        </select>
      </label>
    </div>
    <DsfrPagination v-if="pageCount > 1" v-model:current-page="pageIndex" :pages="pages" />
  </div>
</template>

<style scoped>
.pagination-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin-top: 0.75rem;
}

.pagination-bar__summary {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 0;
  color: var(--text-mention-grey);
}

.pagination-bar__size {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.pagination-bar__select {
  width: auto;
  margin: 0;
  padding-block: 0.25rem;
}
</style>
