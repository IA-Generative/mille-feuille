<script setup lang="ts">
import { formatDayLabel } from '@/utils/dates';

// En-tête : titre, date du jour et boutons ronds (notifications, dossiers
// non affectés, activité récente). Chaque bouton ouvre une fenêtre.
defineProps<{
  unreadCount: number;
  /** Nombre de dossiers non affectés ; `null` si l'utilisateur n'a pas le droit de les voir. */
  unassignedCount: number | null;
}>();
defineEmits<{
  "open-notifications": [];
  "open-unassigned": [];
  "open-activity": [];
}>();

const todayLabel = formatDayLabel(new Date());

const plural = (n: number, one: string, many: string) => `${n} ${n > 1 ? many : one}`;
</script>

<template>
  <header class="head">
    <div>
      <h1 class="head__title">Aujourd'hui</h1>
      <p class="head__date">{{ todayLabel }}</p>
    </div>

    <div class="head__actions">
      <button
        v-if="unassignedCount !== null"
        type="button"
        class="head__btn"
        :aria-label="`Dossiers à prendre en charge, ${plural(unassignedCount, 'dossier', 'dossiers')}`"
        title="Dossiers à prendre en charge"
        @click="$emit('open-unassigned')"
      >
        <VIcon name="ri-user-add-line" />
        <span v-if="unassignedCount" class="head__count" aria-hidden="true">{{ unassignedCount }}</span>
      </button>

      <button type="button" class="head__btn" aria-label="Activité récente" title="Activité récente" @click="$emit('open-activity')">
        <VIcon name="ri-history-line" />
      </button>

      <button
        type="button"
        class="head__btn"
        :aria-label="`Notifications, ${plural(unreadCount, 'non lue', 'non lues')}`"
        title="Notifications"
        @click="$emit('open-notifications')"
      >
        <VIcon name="ri-notification-3-line" />
        <span v-if="unreadCount" class="head__count" aria-hidden="true">{{ unreadCount }}</span>
      </button>
    </div>
  </header>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.head__title {
  margin: 0;
  font-size: 2rem;
  font-weight: 800;
}

.head__date {
  margin: 0;
  color: var(--text-mention-grey);
}

.head__date::first-letter {
  text-transform: uppercase;
}

.head__actions {
  display: flex;
  gap: 0.5rem;
}

.head__btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border: none;
  border-radius: 50%;
  background: var(--background-alt-grey);
  color: var(--text-default-grey);
  font-size: 1.125rem;
  cursor: pointer;
}

.head__btn:hover {
  background: var(--background-alt-grey-hover);
}

.head__count {
  position: absolute;
  top: -0.125rem;
  right: -0.125rem;
  min-width: 1.125rem;
  padding: 0 0.25rem;
  border-radius: 0.5625rem;
  background: var(--background-flat-error);
  color: var(--text-inverted-grey);
  font-size: 0.6875rem;
  font-weight: 700;
  line-height: 1.125rem;
  text-align: center;
}
</style>
