<script setup lang="ts">
import { ref } from "vue";

import UsageCharts from "@/components/usage/UsageCharts.vue";
import UsagePeriodSelector from "@/components/usage/UsagePeriodSelector.vue";
import { useUsage } from "@/composables/useUsage";

const days = ref(30);
const { usage, loading, error } = useUsage(days);
</script>

<template>
  <div class="usage-page">
    <div class="usage-page__header">
      <h1 class="fr-h2">Ma consommation</h1>
      <UsagePeriodSelector v-model="days" />
    </div>
    <p class="usage-page__intro">
      Les tokens consommés pour vous par les modèles : vos questions dans le chat, l'assistant, l'aide à la rédaction,
      les traitements que vous avez lancés (notes, génération de documents) et vos runs via l'API éphémère. La
      classification, l'extraction et les résumés d'un dossier classique ne sont rattachés à personne : ils
      n'apparaissent pas ici.
    </p>

    <div v-if="error" class="fr-alert fr-alert--error" role="alert">{{ error }}</div>
    <p v-else-if="loading && !usage" class="usage-page__empty">Chargement…</p>
    <p v-else-if="usage && usage.totals.calls === 0" class="usage-page__empty">
      Aucune consommation sur les {{ days }} derniers jours.
    </p>
    <UsageCharts v-else-if="usage" :usage="usage" />
  </div>
</template>

<style scoped>
.usage-page {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.usage-page__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.usage-page__header h1 {
  margin: 0;
}

.usage-page__intro {
  margin: 0;
  color: var(--text-mention-grey);
}

.usage-page__empty {
  margin: 3rem 0;
  text-align: center;
  color: var(--text-mention-grey);
}
</style>
