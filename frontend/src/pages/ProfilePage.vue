<script setup lang="ts">
import { onMounted, ref } from "vue";

import { useAuth } from "@/composables/useAuth";
import { useProfile } from "@/composables/useProfile";
import ThemeChoice from "@/components/ThemeChoice.vue";

const { profile, userName } = useAuth();
const { stats, loading, fetchStats } = useProfile();

const dateFormatter = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeStyle: "short" });
function formatDate(iso: string | null) {
  if (!iso) return "—";
  return dateFormatter.format(new Date(iso));
}

const statCards = ref<{ label: string; value: number; icon: string }[]>([]);

function refreshStats() {
  if (!stats.value) return;
  statCards.value = [
    { label: "Conversations (dossiers)", value: stats.value.conversations_count, icon: "ri-chat-3-line" },
    { label: "Messages envoyés", value: stats.value.messages_sent_count, icon: "ri-mail-send-line" },
    { label: "Conversations avec l'assistant", value: stats.value.agent_conversations_count, icon: "ri-robot-2-line" },
    { label: "Messages à l'assistant", value: stats.value.agent_messages_sent_count, icon: "ri-message-3-line" },
    { label: "Dossiers accessibles", value: stats.value.dossiers_count, icon: "ri-folder-line" },
    { label: "Analyses partagées", value: stats.value.analyses_shared_count, icon: "ri-share-line" },
  ];
}

onMounted(async () => {
  await fetchStats();
  refreshStats();
});

function initials(name: string): string {
  return name
    .split(" ")
    .map((part) => part.charAt(0))
    .slice(0, 2)
    .join("")
    .toUpperCase();
}
</script>

<template>
  <div class="profile-page">
    <div class="fr-container fr-py-6w">
      <h1 class="fr-h2">Mon profil</h1>

      <!-- Carte identité -->
      <div class="fr-card fr-mb-4w">
        <div class="fr-card__body">
          <div class="fr-grid-row fr-grid-row--middle">
            <div class="fr-col-auto">
              <span class="profile-page__avatar" aria-hidden="true">{{ initials(userName) }}</span>
            </div>
            <div class="fr-col fr-ml-3w">
              <h2 class="fr-h3 fr-mb-0">{{ userName }}</h2>
              <p v-if="profile?.email" class="fr-text--sm fr-mb-0 fr-text--muted">{{ profile.email }}</p>
              <DsfrBadge v-if="profile?.isAdmin" label="Administrateur" type="info" />
            </div>
          </div>
        </div>
      </div>

      <!-- Sélecteur de thème -->
      <div class="fr-card fr-mb-4w">
        <div class="fr-card__body">
          <h3 class="fr-h4 fr-mb-2w">
            <VIcon name="ri-palette-line" class="fr-mr-1w" />
            Apparence
          </h3>
          <p class="fr-text--sm fr-text--muted fr-mb-2w">
            Choisissez le thème de l'interface. Le thème « système » s'adapte automatiquement à vos préférences système.
          </p>
          <ThemeChoice />
        </div>
      </div>

      <!-- Statistiques -->
      <div class="fr-card">
        <div class="fr-card__body">
          <h3 class="fr-h4 fr-mb-2w">
            <VIcon name="ri-bar-chart-2-line" class="fr-mr-1w" />
            Statistiques
          </h3>

          <div v-if="loading" class="fr-text--muted">Chargement des statistiques…</div>

          <template v-else>
            <div class="fr-grid-row fr-grid-row--gutters fr-mb-3w">
              <div v-for="card in statCards" :key="card.label" class="fr-col-12 fr-col-md-6 fr-col-lg-4">
                <div class="profile-page__stat">
                  <VIcon :name="card.icon" class="profile-page__stat-icon" />
                  <div>
                    <div class="profile-page__stat-value">{{ card.value }}</div>
                    <div class="profile-page__stat-label">{{ card.label }}</div>
                  </div>
                </div>
              </div>
            </div>

            <div class="fr-grid-row fr-grid-row--middle">
              <div class="fr-col-auto">
                <VIcon name="ri-time-line" class="fr-mr-1w" />
                <span class="fr-text--bold">Dernière activité :</span>
              </div>
              <div class="fr-col fr-ml-1w">
                {{ formatDate(stats?.last_activity_at ?? null) }}
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-page {
  min-height: calc(100vh - var(--header-height, 0px));
}

.profile-page__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 4rem;
  height: 4rem;
  border-radius: 50%;
  background: var(--background-contrast-grey, #f6f6f6);
  color: var(--text-title-grey, #161616);
  font-weight: 700;
  font-size: 1.5rem;
}

.profile-page__stat {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  border: 1px solid var(--border-default-grey, #ddd);
  border-radius: 0.25rem;
  background: var(--background-default-grey, #fff);
  height: 100%;
}

.profile-page__stat-icon {
  font-size: 2rem;
  color: var(--text-action-high-blue-france, #000091);
}

.profile-page__stat-value {
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1;
}

.profile-page__stat-label {
  font-size: 0.875rem;
  color: var(--text-mention-grey, #666);
  margin-top: 0.25rem;
}

.fr-text--muted {
  color: var(--text-mention-grey, #666);
}
</style>
