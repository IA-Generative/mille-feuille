<script setup lang="ts">
import { ref, watch } from "vue";

import { useAdminTasks } from "@/composables/useAdminTasks";

const { tasks: adminTasks, loading: tasksLoading, error: tasksError, fetchTasks } = useAdminTasks();

const hasLoaded = ref(false);
watch(
  () => adminTasks.value,
  (tasks) => {
    if (tasks) hasLoaded.value = true;
  },
);

defineExpose({ fetchTasks });
</script>

<template>
  <section class="admin-tasks">
    <div class="admin-tasks__header">
      <h2 class="fr-h4">
        <VIcon name="ri-list-check-2" class="fr-mr-1w" />
        Tâches Celery
      </h2>
      <DsfrButton label="Rafraîchir" tertiary size="sm" @click="fetchTasks" />
    </div>

    <DsfrAlert v-if="tasksError" alert type="error" small :description="tasksError" class="fr-mb-2w" />
    <div v-if="tasksLoading && !hasLoaded" class="fr-text--sm">Chargement des tâches…</div>

    <template v-else-if="adminTasks">
      <p v-if="adminTasks.workers.length === 0" class="fr-text--sm">
        Aucun worker Celery actuellement en ligne.
      </p>
      <div v-else class="admin-tasks__workers">
        <DsfrBadge
          v-for="worker in adminTasks.workers"
          :key="worker"
          :label="worker"
          type="success"
        />
      </div>

      <div class="admin-tasks__grid">
        <div class="admin-tasks__panel">
          <h3 class="fr-text--lg fr-mb-1w">
            Actives
            <span class="admin-tasks__count">({{ adminTasks.active.length }})</span>
          </h3>
          <p v-if="adminTasks.active.length === 0" class="fr-text--sm">Aucune tâche active.</p>
          <ul v-else class="admin-tasks__list">
            <li v-for="task in adminTasks.active" :key="task.id ?? task.name" class="admin-tasks__item">
              <span class="admin-tasks__item-name">{{ task.name }}</span>
              <span class="admin-tasks__item-worker">{{ task.worker }}</span>
            </li>
          </ul>
        </div>

        <div class="admin-tasks__panel">
          <h3 class="fr-text--lg fr-mb-1w">
            Réservées
            <span class="admin-tasks__count">({{ adminTasks.reserved.length }})</span>
          </h3>
          <p v-if="adminTasks.reserved.length === 0" class="fr-text--sm">Aucune tâche réservée.</p>
          <ul v-else class="admin-tasks__list">
            <li v-for="task in adminTasks.reserved" :key="task.id ?? task.name" class="admin-tasks__item">
              <span class="admin-tasks__item-name">{{ task.name }}</span>
              <span class="admin-tasks__item-worker">{{ task.worker }}</span>
            </li>
          </ul>
        </div>

        <div class="admin-tasks__panel">
          <h3 class="fr-text--lg fr-mb-1w">
            Enregistrées
            <span class="admin-tasks__count">({{ adminTasks.registered.length }})</span>
          </h3>
          <p v-if="adminTasks.registered.length === 0" class="fr-text--sm">Aucune tâche enregistrée.</p>
          <ul v-else class="admin-tasks__list admin-tasks__list--scroll">
            <li v-for="task in adminTasks.registered" :key="task.name" class="admin-tasks__item">
              <span class="admin-tasks__item-name">{{ task.name }}</span>
              <span class="admin-tasks__item-worker">{{ task.worker }}</span>
            </li>
          </ul>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.admin-tasks {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.admin-tasks__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.admin-tasks__workers {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.admin-tasks__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
  gap: 1rem;
}

.admin-tasks__panel {
  padding: 1.25rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
}

.admin-tasks__count {
  color: var(--text-mention-grey);
  font-weight: 400;
}

.admin-tasks__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.admin-tasks__list--scroll {
  max-height: 12rem;
  overflow-y: auto;
}

.admin-tasks__item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  border-radius: 0.25rem;
  background: var(--background-alt-grey);
}

.admin-tasks__item-name {
  font-family: monospace;
  font-size: 0.8rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-tasks__item-worker {
  font-size: 0.75rem;
  color: var(--text-mention-grey);
  white-space: nowrap;
}
</style>
