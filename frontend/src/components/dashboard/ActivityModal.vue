<script setup lang="ts">
import { RouterLink } from "vue-router";

import AppModal from "@/components/AppModal.vue";
import type { ActivityKind, DashboardActivity } from "@/types/dashboard";
import { formatRelativeTime } from "@/utils/dates";

// Derniers changements sur mes dossiers (statut, document, analyse).
defineProps<{ items: DashboardActivity[] }>();
const emit = defineEmits<{ close: [] }>();

const ICONS: Record<ActivityKind, string> = {
  status_changed: "ri-flag-line",
  document_added: "ri-file-add-line",
  analysis_done: "ri-checkbox-circle-line",
  analysis_failed: "ri-error-warning-line",
};
</script>

<template>
  <AppModal
    :opened="true"
    title="Activité récente"
    icon="ri-history-line"
    size="lg"
    :actions="[{ label: 'Fermer', onClick: () => emit('close') }]"
    @close="emit('close')"
  >
    <p v-if="items.length === 0" class="am__empty">Aucune activité récente sur vos dossiers.</p>
    <ul v-else class="am__list">
      <li v-for="a in items" :key="a.id">
        <RouterLink :to="`/dossiers/${a.dossierId}`" class="am__row" @click="emit('close')">
          <VIcon :name="ICONS[a.kind]" />
          <span class="am__main">
            <span class="am__title">{{ a.dossierName }}</span>
            <span class="am__sub">{{ a.message }}</span>
          </span>
          <span class="am__time">{{ formatRelativeTime(a.at) }}</span>
        </RouterLink>
      </li>
    </ul>
  </AppModal>
</template>

<style scoped>
.am__empty {
  margin: 1.5rem 0;
  text-align: center;
  color: var(--text-mention-grey);
}

.am__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.am__row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0.25rem;
  border-bottom: 1px solid var(--border-default-grey);
  background-image: none;
  color: var(--text-default-grey);
}

.am__row:hover {
  background: var(--background-alt-grey-hover);
}

.am__main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.am__title {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.am__sub,
.am__time {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.am__time {
  flex-shrink: 0;
  white-space: nowrap;
}
</style>
