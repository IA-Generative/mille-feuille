<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import { useNotifications } from "@/composables/useNotifications";
import {
  NOTIFICATION_CATEGORIES,
  categoryOf,
  type NotificationCategory,
  type NotificationKind,
} from "@/types/dashboard";
import { formatRelativeTime } from "@/utils/dates";

const emit = defineEmits<{ close: [] }>();

const {
  notifications,
  unreadCount,
  markRead,
  markAllRead,
  browserPermission,
  browserEnabled,
  enableBrowserNotifications,
  disableBrowserNotifications,
} = useNotifications();

const ICONS: Record<NotificationKind, string> = {
  assigned: "ri-user-received-line",
  due_soon: "ri-time-line",
  overdue: "ri-alarm-warning-line",
  status_changed: "ri-flag-line",
  analysis_done: "ri-checkbox-circle-line",
  analysis_failed: "ri-error-warning-line",
  reminder: "ri-notification-badge-line",
};

const filter = ref<NotificationCategory | "all">("all");

const chips = computed(() => [
  { value: "all" as const, label: "Toutes", unread: unreadCount.value },
  ...NOTIFICATION_CATEGORIES.map((c) => ({
    value: c.value,
    label: c.label,
    unread: notifications.value.filter((n) => !n.readAt && categoryOf(n.kind) === c.value).length,
  })),
]);

const visible = computed(() =>
  filter.value === "all" ? notifications.value : notifications.value.filter((n) => categoryOf(n.kind) === filter.value),
);

const actions = computed(() => [
  { label: "Tout marquer comme lu", secondary: true, disabled: unreadCount.value === 0, onClick: markAllRead },
  { label: "Fermer", onClick: () => emit("close") },
]);

function open(id: string) {
  markRead(id);
  emit("close");
}
</script>

<template>
  <DsfrModal :opened="true" title="Notifications" icon="ri-notification-3-line" size="lg" :actions="actions" @close="emit('close')">
    <!-- Alertes du navigateur : activables d'un clic, l'autorisation est demandée à ce moment-là. -->
    <div v-if="browserPermission !== 'unsupported'" class="notifs__browser">
      <p v-if="browserPermission === 'denied'" class="notifs__browser-text">
        <VIcon name="ri-notification-off-line" /> Les notifications sont bloquées pour ce site. Autorisez-les dans les
        réglages de votre navigateur pour les activer.
      </p>
      <template v-else>
        <p class="notifs__browser-text">
          <VIcon name="ri-computer-line" />
          {{ browserEnabled ? "Alertes du navigateur activées." : "Recevoir une alerte du navigateur pour les rappels et nouveautés." }}
        </p>
        <button
          type="button"
          class="fr-btn fr-btn--sm"
          :class="{ 'fr-btn--secondary': browserEnabled }"
          @click="browserEnabled ? disableBrowserNotifications() : enableBrowserNotifications()"
        >
          {{ browserEnabled ? "Désactiver" : "Activer" }}
        </button>
      </template>
    </div>

    <div class="notifs__chips" role="group" aria-label="Catégories de notifications">
      <button
        v-for="c in chips"
        :key="c.value"
        type="button"
        class="notifs__chip"
        :class="{ 'notifs__chip--on': filter === c.value }"
        :aria-pressed="filter === c.value"
        @click="filter = c.value"
      >
        {{ c.label }}
        <span v-if="c.unread" class="notifs__count">
          {{ c.unread }}<span class="fr-sr-only"> non lue{{ c.unread > 1 ? "s" : "" }}</span>
        </span>
      </button>
    </div>

    <p v-if="visible.length === 0" class="notifs__empty">Aucune notification.</p>
    <ul v-else class="notifs__list">
      <li v-for="n in visible" :key="n.id">
        <!-- Accès retiré (#177) : la notification reste dans la liste mais sans lien ni nom de dossier. -->
        <div v-if="!n.accessible" class="notifs__row notifs__row--revoked">
          <span class="notifs__dot" aria-hidden="true" />
          <VIcon name="ri-lock-line" />
          <span class="notifs__main">
            <span class="notifs__title">Dossier non accessible</span>
            <span class="notifs__sub">Vous n'avez plus accès à ce dossier.</span>
          </span>
          <span class="notifs__time">{{ formatRelativeTime(n.createdAt) }}</span>
        </div>
        <RouterLink v-else :to="`/dossiers/${n.dossierId}`" class="notifs__row" @click="open(n.id)">
          <span class="notifs__dot" :class="{ 'notifs__dot--on': !n.readAt }" aria-hidden="true" />
          <VIcon :name="ICONS[n.kind]" />
          <span class="notifs__main">
            <span class="notifs__title"><span v-if="!n.readAt" class="fr-sr-only">Non lue : </span>{{ n.dossierName }}</span>
            <span class="notifs__sub">{{ n.message }}</span>
          </span>
          <span class="notifs__time">{{ formatRelativeTime(n.createdAt) }}</span>
        </RouterLink>
      </li>
    </ul>
  </DsfrModal>
</template>

<style scoped>
.notifs__browser {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  background: var(--background-alt-grey);
}

.notifs__browser-text {
  margin: 0;
  font-size: 0.875rem;
}

.notifs__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-bottom: 1rem;
}

.notifs__chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.125rem 0.75rem;
  border: none;
  border-radius: 1rem;
  background: var(--background-alt-grey);
  color: var(--text-default-grey);
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}

.notifs__chip--on {
  background: var(--background-action-high-blue-france);
  color: var(--text-inverted-blue-france);
}

.notifs__count {
  min-width: 1.125rem;
  border-radius: 0.5625rem;
  background: var(--background-flat-error);
  color: var(--text-inverted-grey);
  font-size: 0.6875rem;
  font-weight: 700;
  line-height: 1.125rem;
  text-align: center;
}

.notifs__empty {
  margin: 1.5rem 0;
  text-align: center;
  color: var(--text-mention-grey);
}

.notifs__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.notifs__row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0.25rem;
  border-bottom: 1px solid var(--border-default-grey);
  background-image: none;
  color: var(--text-default-grey);
}

.notifs__row:hover {
  background: var(--background-alt-grey-hover);
}

.notifs__row--revoked {
  color: var(--text-mention-grey);
}

.notifs__dot {
  flex-shrink: 0;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
}

.notifs__dot--on {
  background: var(--background-action-high-blue-france);
}

.notifs__main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.notifs__title {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notifs__sub,
.notifs__time {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.notifs__time {
  flex-shrink: 0;
  white-space: nowrap;
}
</style>
