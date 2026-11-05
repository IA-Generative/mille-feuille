<script setup lang="ts">
import { computed, onMounted } from "vue";

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

// computed plutôt que ref + refreshStats() : plus d'état dupliqué à resynchroniser
const statCards = computed(() => {
  const s = stats.value;
  if (!s) return [];
  return [
    { label: "Conversations (dossiers)", value: s.conversations_count, icon: "ri-chat-3-line" },
    { label: "Messages envoyés", value: s.messages_sent_count, icon: "ri-mail-send-line" },
    { label: "Conversations avec l'assistant", value: s.agent_conversations_count, icon: "ri-robot-2-line" },
    { label: "Messages à l'assistant", value: s.agent_messages_sent_count, icon: "ri-message-3-line" },
    { label: "Dossiers accessibles", value: s.dossiers_count, icon: "ri-folder-line" },
    { label: "Analyses partagées", value: s.analyses_shared_count, icon: "ri-share-line" },
  ];
});

onMounted(fetchStats);

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
    <h1 class="fr-h2">Mon profil</h1>

    <!-- Identité : pleine largeur, sans cadre -->
    <section class="profile-page__identity fr-mb-4w" aria-labelledby="profile-identity-title">
      <span class="profile-page__avatar" aria-hidden="true">{{ initials(userName) }}</span>
      <div>
        <h2 id="profile-identity-title" class="fr-h3 fr-mb-1v">{{ userName }}</h2>
        <p v-if="profile?.email" class="fr-text--sm fr-mb-1w fr-text-mention--grey">{{ profile.email }}</p>
        <DsfrBadge v-if="profile?.isAdmin" label="Administrateur" type="info" />
      </div>
    </section>

    <div class="fr-grid-row fr-grid-row--gutters">
      <!-- Colonne gauche : Apparence, dans un panneau bleu pâle -->
      <div class="fr-col-12 fr-col-lg-5">
        <section class="profile-page__panel" aria-labelledby="profile-theme-title">
          <h2 id="profile-theme-title" class="fr-h4 fr-mb-2w">
            <VIcon name="ri-palette-line" class="fr-mr-1w" aria-hidden="true" />
            Apparence
          </h2>
          <p class="fr-text--sm fr-text-mention--grey fr-mb-2w">
            Choisissez le thème de l'interface. Le thème « système » s'adapte automatiquement à vos préférences système.
          </p>
          <ThemeChoice />
        </section>
      </div>

      <!-- Colonne droite : Statistiques, au même niveau qu'Apparence -->
      <div class="fr-col-12 fr-col-lg-7">
        <section aria-labelledby="profile-stats-title">
          <h2 id="profile-stats-title" class="fr-h4 fr-mb-2w">
            <VIcon name="ri-bar-chart-2-line" class="fr-mr-1w" aria-hidden="true" />
            Statistiques
          </h2>

          <!-- Toujours dans le DOM : c'est le changement de contenu que le lecteur d'écran annonce -->
          <div role="status">
            <p v-if="loading" class="fr-text-mention--grey">Chargement des statistiques…</p>
          </div>

          <template v-if="!loading">
            <ul class="profile-page__stats">
              <li v-for="card in statCards" :key="card.label" class="profile-page__stat">
                <div class="profile-page__stat-head">
                  <span class="profile-page__stat-icon" aria-hidden="true">
                    <VIcon :name="card.icon" aria-hidden="true" />
                  </span>
                  <span class="profile-page__stat-value">{{ card.value }}</span>
                </div>
                <span class="profile-page__stat-label">{{ card.label }}</span>
              </li>
            </ul>

            <p class="fr-text--sm fr-mt-3w fr-mb-0">
              <VIcon name="ri-time-line" class="fr-mr-1w" aria-hidden="true" />
              <span class="fr-text--bold">Dernière activité : </span>
              <time v-if="stats?.last_activity_at" :datetime="stats.last_activity_at">
                {{ formatDate(stats.last_activity_at) }}
              </time>
              <span v-else>—</span>
            </p>
          </template>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-page__identity {
  display: flex;
  align-items: center;
  gap: 1.25rem;
}

.profile-page__avatar {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 5rem;
  height: 5rem;
  border-radius: 50%;
  background: var(--background-action-low-blue-france);
  color: var(--text-action-high-blue-france);
  font-size: 1.75rem;
  font-weight: 700;
}

/* Panneau « Apparence » : même rayon que les tuiles, fond bleu pâle pour le distinguer des aplats gris */
.profile-page__panel {
  padding: 1.5rem;
  border-radius: 0.75rem;
  background: var(--background-alt-blue-france);
}

.profile-page__stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* Même recette que MetricCard : aplat sans bordure, rayon 0.75rem */
.profile-page__stat {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
  padding: 1rem 1.25rem;
  border-radius: 0.75rem;
  background: var(--background-alt-grey);
  color: var(--text-default-grey);
}

.profile-page__stat-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

/* Pastille bleu pâle, comme .welcome__step-tile sur la landing page */
.profile-page__stat-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.75rem;
  background: var(--background-action-low-blue-france);
  color: var(--text-action-high-blue-france);
}

.profile-page__stat-value {
  font-size: 1.75rem;
  font-weight: 800;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.profile-page__stat-label {
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}
</style>
