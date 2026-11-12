<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { useAdminStats } from "@/composables/useAdminStats";

const { stats: adminStats, loading: statsLoading, error: statsError, fetchStats } = useAdminStats();

const hasLoaded = ref(false);
watch(
  () => adminStats.value,
  (stats) => {
    if (stats) hasLoaded.value = true;
  },
);

const DOSSIER_STATUS_LABELS: Record<string, string> = {
  en_attente: "En attente",
  en_cours: "En cours",
  termine: "Terminé",
  echec: "Échec",
};

const statCards = computed(() => {
  if (!adminStats.value) return [];
  return [
    { label: "Analyses", value: adminStats.value.analyses_count, icon: "ri-file-search-line" },
    { label: "Dossiers", value: adminStats.value.dossiers_count, icon: "ri-folder-line" },
    { label: "Conversations", value: adminStats.value.conversations_count, icon: "ri-chat-3-line" },
    { label: "Messages", value: adminStats.value.messages_count, icon: "ri-mail-send-line" },
    { label: "Conversations assistant", value: adminStats.value.agent_conversations_count, icon: "ri-robot-2-line" },
    { label: "Messages assistant", value: adminStats.value.agent_messages_count, icon: "ri-message-3-line" },
    { label: "Signalements", value: adminStats.value.reports_count, icon: "ri-bug-line" },
    { label: "Utilisateurs (préférences)", value: adminStats.value.users_count, icon: "ri-user-line" },
  ];
});

const maxDailyCount = computed(() => {
  if (!adminStats.value) return 0;
  return Math.max(1, ...adminStats.value.daily_creations.map((d) => d.count));
});

const dayFormatter = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short" });
function formatDay(iso: string) {
  return dayFormatter.format(new Date(iso));
}

defineExpose({ fetchStats });
</script>

<template>
  <section class="admin-stats">
    <h2 class="fr-h4">
      <VIcon name="ri-bar-chart-2-line" class="fr-mr-1w" />
      Statistiques
    </h2>

    <DsfrAlert v-if="statsError" alert type="error" small :description="statsError" class="fr-mb-2w" />
    <div v-if="statsLoading && !hasLoaded" class="fr-text--sm">Chargement des statistiques…</div>

    <template v-else-if="adminStats">
      <div class="admin-stats__cards">
        <div v-for="card in statCards" :key="card.label" class="admin-stats__card">
          <VIcon :name="card.icon" class="admin-stats__card-icon" />
          <div>
            <div class="admin-stats__card-value">{{ card.value }}</div>
            <div class="admin-stats__card-label">{{ card.label }}</div>
          </div>
        </div>
      </div>

      <div class="admin-stats__grid">
        <div class="admin-stats__panel">
          <h3 class="fr-text--lg fr-mb-1w">Dossiers par statut</h3>
          <ul class="admin-stats__status-list">
            <li v-for="(count, key) in adminStats.dossiers_by_status" :key="key" class="admin-stats__status-item">
              <span class="admin-stats__status-label">{{ DOSSIER_STATUS_LABELS[key] ?? key }}</span>
              <span class="admin-stats__status-count">{{ count }}</span>
            </li>
          </ul>
        </div>

        <div class="admin-stats__panel">
          <h3 class="fr-text--lg fr-mb-1w">Créations de dossiers (7 derniers jours)</h3>
          <div v-if="adminStats.daily_creations.length === 0" class="fr-text--sm">Aucune création récente.</div>
          <div v-else class="admin-stats__chart">
            <div
              v-for="day in adminStats.daily_creations"
              :key="day.date"
              class="admin-stats__chart-bar"
              :title="`${formatDay(day.date)}: ${day.count}`"
            >
              <div
                class="admin-stats__chart-fill"
                :style="{ height: `${(day.count / maxDailyCount) * 100}%` }"
              />
              <span class="admin-stats__chart-label">{{ formatDay(day.date) }}</span>
              <span class="admin-stats__chart-value">{{ day.count }}</span>
            </div>
          </div>
        </div>

        <div class="admin-stats__panel">
          <h3 class="fr-text--lg fr-mb-1w">Top modèles LLM</h3>
          <div v-if="adminStats.top_models.length === 0" class="fr-text--sm">Aucun modèle utilisé.</div>
          <ul v-else class="admin-stats__models">
            <li v-for="(model, i) in adminStats.top_models" :key="model.model" class="admin-stats__model">
              <span class="admin-stats__model-rank">{{ i + 1 }}</span>
              <span class="admin-stats__model-name">{{ model.model }}</span>
              <span class="admin-stats__model-count">{{ model.count }}</span>
            </li>
          </ul>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.admin-stats {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.admin-stats__cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
  gap: 1rem;
}

.admin-stats__card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
}

.admin-stats__card-icon {
  font-size: 1.75rem;
  color: var(--text-action-high-blue-france);
}

.admin-stats__card-value {
  font-size: 1.5rem;
  font-weight: 700;
  line-height: 1;
}

.admin-stats__card-label {
  font-size: 0.8rem;
  color: var(--text-mention-grey);
  margin-top: 0.25rem;
}

.admin-stats__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
  gap: 1rem;
}

.admin-stats__panel {
  padding: 1.25rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
}

.admin-stats__status-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.admin-stats__status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.admin-stats__status-label {
  color: var(--text-mention-grey);
}

.admin-stats__status-count {
  font-weight: 600;
}

.admin-stats__chart {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  height: 8rem;
}

.admin-stats__chart-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  flex: 1;
  min-width: 2.5rem;
}

.admin-stats__chart-fill {
  width: 60%;
  min-height: 2px;
  background: var(--background-action-high-blue-france);
  border-radius: 0.25rem 0.25rem 0 0;
  transition: height 0.3s ease;
}

.admin-stats__chart-label {
  font-size: 0.7rem;
  color: var(--text-mention-grey);
}

.admin-stats__chart-value {
  font-size: 0.75rem;
  font-weight: 600;
}

.admin-stats__models {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.admin-stats__model {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.admin-stats__model-rank {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: var(--background-contrast-grey);
  font-size: 0.75rem;
  font-weight: 700;
}

.admin-stats__model-name {
  flex: 1;
  font-family: monospace;
  font-size: 0.85rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-stats__model-count {
  font-weight: 600;
}
</style>
