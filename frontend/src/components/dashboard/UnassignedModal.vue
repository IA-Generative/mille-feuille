<script setup lang="ts">
import { RouterLink } from "vue-router";

import AppModal from "@/components/AppModal.vue";
import type { DashboardUnassigned } from "@/types/dashboard";
import { formatRelativeTime } from "@/utils/dates";

// Dossiers à prendre en charge (rôles autorisés seulement : le parent décide
// d'afficher ou non le bouton qui ouvre cette fenêtre).
defineProps<{ items: DashboardUnassigned[] }>();
const emit = defineEmits<{ close: [] }>();
</script>

<template>
  <AppModal
    :opened="true"
    title="Dossiers à prendre en charge"
    icon="ri-user-add-line"
    size="lg"
    :actions="[{ label: 'Fermer', onClick: () => emit('close') }]"
    @close="emit('close')"
  >
    <RouterLink v-if="items.length" :to="{ path: '/suivi', query: { assignee: 'none' } }" class="um__all" @click="emit('close')">
      Voir tous les dossiers non affectés dans le suivi
    </RouterLink>
    <p v-if="items.length === 0" class="um__empty">Aucun dossier à prendre en charge.</p>
    <ul v-else class="um__list">
      <li v-for="d in items" :key="d.dossierId">
        <RouterLink :to="`/dossiers/${d.dossierId}`" class="um__row" @click="emit('close')">
          <span class="um__main">
            <span class="um__title">{{ d.dossierName }}</span>
            <span class="um__sub">{{ d.analyseName }}</span>
          </span>
          <span class="um__time">{{ formatRelativeTime(d.createdAt) }}</span>
        </RouterLink>
      </li>
    </ul>
  </AppModal>
</template>

<style scoped>
.um__all {
  display: inline-block;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
}

.um__empty {
  margin: 1.5rem 0;
  text-align: center;
  color: var(--text-mention-grey);
}

.um__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.um__row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0.25rem;
  border-bottom: 1px solid var(--border-default-grey);
  background-image: none;
  color: var(--text-default-grey);
}

.um__row:hover {
  background: var(--background-alt-grey-hover);
}

.um__main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.um__title {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.um__sub,
.um__time {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.um__time {
  flex-shrink: 0;
  white-space: nowrap;
}
</style>
