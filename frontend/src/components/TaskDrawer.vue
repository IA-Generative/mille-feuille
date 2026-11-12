<script setup lang="ts">
/**
 * Drawer listant les tâches asynchrones de l'utilisateur (issue #62).
 *
 * Affiche les tâches avec leur type, statut et progression. Les tâches
 * actives (pending / running) sont affichées en premier, suivies des
 * tâches terminées (success / failure) récentes.
 *
 * Le drawer utilise le même pattern que InfoModal (overlay + panneau)
 * mais glisse depuis la droite plutôt que d'être centré.
 */
import { computed } from "vue";

import { useUserTasks } from "@/composables/useUserTasks";
import type { UserTask, UserTaskStatus } from "@/types/userTask";

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();

const { tasks, activeTasks, loading, refresh } = useUserTasks();

// Tâches triées : actives d'abord, puis par date de création décroissante.
const sortedTasks = computed(() => {
  const isActive = (t: UserTask) => t.status === "pending" || t.status === "running";
  return [...tasks.value].sort((a, b) => {
    const aActive = isActive(a);
    const bActive = isActive(b);
    if (aActive !== bActive) return aActive ? -1 : 1;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });
});

const statusConfig: Record<UserTaskStatus, { label: string; icon: string; class: string }> = {
  pending: { label: "En attente", icon: "ri-time-line", class: "task-drawer__status--pending" },
  running: { label: "En cours", icon: "ri-loader-4-line", class: "task-drawer__status--running" },
  success: { label: "Terminé", icon: "ri-check-line", class: "task-drawer__status--success" },
  failure: { label: "Échec", icon: "ri-error-warning-line", class: "task-drawer__status--failure" },
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

function targetLink(task: UserTask): string | null {
  if (!task.target_id || !task.target_type) return null;
  switch (task.target_type) {
    case "dossier":
      return `/dossiers/${task.target_id}`;
    case "analyse":
      return `/analyses/${task.target_id}`;
    default:
      return null;
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="task-drawer-fade">
      <div v-if="props.open" class="task-drawer__overlay" @click.self="emit('close')">
        <Transition name="task-drawer-slide">
          <aside
            v-if="props.open"
            class="task-drawer"
            aria-label="Tâches en cours"
          >
            <!-- En-tête -->
            <header class="task-drawer__header">
              <div class="task-drawer__title-wrapper">
                <VIcon name="ri-task-line" class="task-drawer__title-icon" />
                <h2 class="task-drawer__title">Tâches</h2>
                <span v-if="activeTasks.length > 0" class="task-drawer__badge">{{ activeTasks.length }}</span>
              </div>
              <button
                type="button"
                class="task-drawer__close"
                aria-label="Fermer"
                @click="emit('close')"
              >
                <VIcon name="ri-close-line" />
              </button>
            </header>

            <!-- Corps -->
            <div class="task-drawer__body">
              <div v-if="loading && tasks.length === 0" class="task-drawer__empty">
                <VIcon name="ri-loader-4-line" class="task-drawer__spinner" />
                <p>Chargement…</p>
              </div>

              <div v-else-if="sortedTasks.length === 0" class="task-drawer__empty">
                <VIcon name="ri-inbox-line" class="task-drawer__empty-icon" />
                <p>Aucune tâche récente.</p>
              </div>

              <ul v-else class="task-drawer__list">
                <li
                  v-for="task in sortedTasks"
                  :key="task.id"
                  class="task-drawer__item"
                  :class="{ 'task-drawer__item--clickable': targetLink(task) }"
                >
                  <component
                    :is="targetLink(task) ? 'router-link' : 'div'"
                    :to="targetLink(task) ?? undefined"
                    class="task-drawer__item-content"
                    @click="targetLink(task) && emit('close')"
                  >
                    <div class="task-drawer__item-header">
                      <span class="task-drawer__item-label">{{ task.label }}</span>
                      <span
                        class="task-drawer__status"
                        :class="statusConfig[task.status].class"
                      >
                        <VIcon
                          :name="statusConfig[task.status].icon"
                          :class="{ 'task-drawer__spinner': task.status === 'running' }"
                        />
                        {{ statusConfig[task.status].label }}
                      </span>
                    </div>
                    <div class="task-drawer__item-meta">
                      <span class="task-drawer__time">{{ formatTime(task.created_at) }}</span>
                      <span v-if="task.error" class="fr-error-text task-drawer__error" :title="task.error">{{ task.error }}</span>
                    </div>
                  </component>
                </li>
              </ul>
            </div>

            <!-- Pied : bouton rafraîchir -->
            <footer class="task-drawer__footer">
              <button
                type="button"
                class="task-drawer__refresh"
                :disabled="loading"
                @click="refresh()"
              >
                <VIcon name="ri-refresh-line" :class="{ 'task-drawer__spinner': loading }" />
                Rafraîchir
              </button>
            </footer>
          </aside>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.task-drawer__overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
}

.task-drawer {
  display: flex;
  flex-direction: column;
  width: 420px;
  max-width: 100vw;
  height: 100vh;
  background: var(--background-default-grey);
  border-left: 1px solid var(--border-default-grey);
  box-shadow: -4px 0 16px rgba(0, 0, 0, 0.1);
}

/* En-tête */
.task-drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-default-grey);
  flex-shrink: 0;
}

.task-drawer__title-wrapper {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.task-drawer__title-icon {
  font-size: 1.25rem;
  color: var(--text-mention-grey);
}

.task-drawer__title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 700;
  color: var(--text-default-grey);
}

.task-drawer__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.375rem;
  border-radius: 0.625rem;
  background: var(--background-action-high-blue-france);
  color: var(--text-inverted-blue-france);
  font-size: 0.75rem;
  font-weight: 700;
}

.task-drawer__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  padding: 0;
  border: none;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--text-mention-grey);
  cursor: pointer;
  font-size: 1.25rem;
}

.task-drawer__close:hover {
  background: var(--background-alt-grey-hover);
  color: var(--text-default-grey);
}

/* Corps */
.task-drawer__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0.5rem;
}

.task-drawer__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 3rem 1rem;
  color: var(--text-mention-grey);
  text-align: center;
}

.task-drawer__empty-icon {
  font-size: 2rem;
  opacity: 0.5;
}

/* Liste */
.task-drawer__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.task-drawer__item {
  border-radius: 0.5rem;
  transition: background-color 0.15s ease;
}

.task-drawer__item--clickable {
  cursor: pointer;
}

.task-drawer__item--clickable:hover {
  background: var(--background-alt-grey-hover);
}

.task-drawer__item-content {
  display: block;
  padding: 0.75rem;
  text-decoration: none;
  color: inherit;
}

.task-drawer__item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}

.task-drawer__item-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-default-grey);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-drawer__status {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.task-drawer__status--pending {
  color: var(--text-mention-grey);
}

.task-drawer__status--running {
  color: var(--text-active-blue-france);
}

.task-drawer__status--success {
  color: var(--text-default-success);
}

.task-drawer__status--failure {
  color: var(--text-default-error);
}

.task-drawer__item-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.task-drawer__time {
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.task-drawer__error {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

/* Pied */
.task-drawer__footer {
  flex-shrink: 0;
  padding: 0.75rem 1.25rem;
  border-top: 1px solid var(--border-default-grey);
  display: flex;
  justify-content: flex-end;
}

.task-drawer__refresh {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.375rem;
  background: transparent;
  color: var(--text-default-grey);
  cursor: pointer;
  font-size: 0.8125rem;
  font-family: inherit;
  transition: background-color 0.15s ease;
}

.task-drawer__refresh:hover:not(:disabled) {
  background: var(--background-alt-grey-hover);
}

.task-drawer__refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Spinner */
.task-drawer__spinner {
  animation: task-drawer-spin 1s linear infinite;
}

@keyframes task-drawer-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Transitions */
.task-drawer-fade-enter-active,
.task-drawer-fade-leave-active {
  transition: opacity 0.2s ease;
}

.task-drawer-fade-enter-from,
.task-drawer-fade-leave-to {
  opacity: 0;
}

.task-drawer-slide-enter-active,
.task-drawer-slide-leave-active {
  transition: transform 0.25s ease;
}

.task-drawer-slide-enter-from,
.task-drawer-slide-leave-to {
  transform: translateX(100%);
}
</style>
