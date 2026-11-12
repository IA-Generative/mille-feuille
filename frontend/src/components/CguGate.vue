<script setup lang="ts">
/**
 * Portail CGU : bloque l'application tant que l'utilisateur connecté n'a pas
 * accepté la version active des Conditions Générales d'Utilisation.
 *
 * Le composant est monté dans App.vue, au-dessus du shell principal. Il
 * n'apparaît que si :
 *   - l'utilisateur est authentifié, ET
 *   - une version active des CGU existe, ET
 *   - l'utilisateur ne l'a pas encore acceptée.
 *
 * Une fois acceptées, le statut est persisté côté backend (table
 * cgu_acceptances) et le composant disparaît jusqu'à la prochaine
 * activation d'une nouvelle version par l'administrateur.
 */
import { computed, onMounted, ref, watch } from "vue";

import { useAuth } from "@/composables/useAuth";
import { useCgu } from "@/composables/useCgu";
import { renderMarkdown } from "@/utils/markdown";

const { isAuthenticated } = useAuth();
const { acceptanceStatus, acceptanceLoading, fetchAcceptanceStatus, acceptCgu } = useCgu();

const cguHtml = ref("");
const errorMessage = ref("");
const accepting = ref(false);

/** Vrai si le gate doit bloquer l'app (CGU non acceptées). */
const mustBlock = computed(
  () =>
    isAuthenticated.value &&
    acceptanceStatus.value.cgu !== null &&
    !acceptanceStatus.value.accepted,
);

async function loadCguContent() {
  const cgu = acceptanceStatus.value.cgu;
  if (!cgu) return;
  cguHtml.value = renderMarkdown(cgu.content);
}

async function handleAccept() {
  accepting.value = true;
  errorMessage.value = "";
  try {
    await acceptCgu();
  } catch {
    errorMessage.value = "Impossible d'enregistrer votre acceptation. Réessayez.";
  } finally {
    accepting.value = false;
  }
}

// Quand l'utilisateur se connecte, on vérifie son statut d'acceptation.
watch(
  () => isAuthenticated.value,
  async (authed) => {
    if (authed) {
      await fetchAcceptanceStatus();
    }
  },
  { immediate: true },
);

// Quand le statut change et qu'une CGU est à accepter, on rend le Markdown.
watch(
  () => acceptanceStatus.value.cgu,
  async () => {
    if (mustBlock.value) await loadCguContent();
  },
  { immediate: true },
);

onMounted(async () => {
  if (isAuthenticated.value) {
    await fetchAcceptanceStatus();
    if (mustBlock.value) await loadCguContent();
  }
});
</script>

<template>
  <div v-if="mustBlock" class="cgu-gate">
    <div class="cgu-gate__card">
      <header class="cgu-gate__header">
        <h1 class="cgu-gate__title">Conditions d'utilisation</h1>
        <p class="cgu-gate__subtitle">
          Vous devez accepter les conditions générales d'utilisation avant de
          pouvoir continuer.
        </p>
      </header>

      <div v-if="acceptanceLoading" class="cgu-gate__loading">
        Chargement…
      </div>

      <template v-else>
        <div class="cgu-gate__content">
          <!-- eslint-disable-next-line vue/no-v-html — contenu rendu par renderMarkdown (échappé) -->
          <div class="markdown" v-html="cguHtml" />
        </div>

        <DsfrAlert v-if="errorMessage" alert type="error" small :description="errorMessage" class="fr-mx-3w fr-mb-2w" />

        <footer class="cgu-gate__footer">
          <p class="cgu-gate__version">
            Version {{ acceptanceStatus.cgu?.version }}
          </p>
          <button
            type="button"
            class="cgu-gate__accept"
            :disabled="accepting"
            @click="handleAccept"
          >
            {{ accepting ? "Enregistrement…" : "J'accepte les conditions d'utilisation" }}
          </button>
        </footer>
      </template>
    </div>
  </div>
</template>

<style scoped>
.cgu-gate {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
  padding: 1.5rem;
}

.cgu-gate__card {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 48rem;
  max-height: 85vh;
  background: var(--background-default-grey);
  border-radius: 0.5rem;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}

.cgu-gate__header {
  padding: 1.5rem 1.5rem 1rem;
  border-bottom: 1px solid var(--border-default-grey);
}

.cgu-gate__title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-title-grey);
}

.cgu-gate__subtitle {
  margin: 0.5rem 0 0;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}

.cgu-gate__loading {
  padding: 3rem;
  text-align: center;
  color: var(--text-mention-grey);
}

.cgu-gate__content {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

.cgu-gate__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-default-grey);
}

.cgu-gate__version {
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.cgu-gate__accept {
  padding: 0.625rem 1.5rem;
  background: var(--background-action-high-blue-france);
  color: var(--text-inverted-blue-france);
  border: none;
  border-radius: 0.25rem;
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: background 0.15s;
}

.cgu-gate__accept:hover:not(:disabled) {
  background: var(--background-action-high-blue-france-hover);
}

.cgu-gate__accept:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
