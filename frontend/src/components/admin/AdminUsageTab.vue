<script setup lang="ts">
import { computed, ref } from "vue";

import UsageCharts from "@/components/usage/UsageCharts.vue";
import UsagePeriodSelector from "@/components/usage/UsagePeriodSelector.vue";
import { useUsage } from "@/composables/useUsage";

const days = ref(30);
const userId = ref<string | null>(null);
// Une seule requête : la liste par personne couvre toujours tout le monde, même restreinte à un user_id.
const { usage, loading, error, reload } = useUsage(days, { admin: true, userId, lazy: true });

const selectedLabel = computed(() => {
  if (!userId.value) return null;
  const row = usage.value?.byUser.find((item) => item.userId === userId.value);
  return row?.display ?? userId.value;
});

defineExpose({ reload });
</script>

<template>
  <section class="admin-usage">
    <div class="admin-usage__header">
      <h2 class="fr-h4">
        <VIcon name="ri-drop-line" class="fr-mr-1w" />
        Consommation
      </h2>
      <UsagePeriodSelector v-model="days" />
    </div>
    <p class="admin-usage__intro">
      Tous les appels aux modèles (chat, assistant, classification, extraction, résumés, génération), pour tout le monde
      ou pour une personne.
    </p>
    <p class="admin-usage__current">
      {{ selectedLabel ? `Consommation de ${selectedLabel}` : "Consommation de tout le monde" }}
    </p>

    <div v-if="error" class="fr-alert fr-alert--error" role="alert">{{ error }}</div>
    <p v-else-if="loading && !usage" class="fr-text--sm">Chargement…</p>
    <p v-else-if="usage && usage.totals.calls === 0 && usage.byUser.length === 0" class="admin-usage__empty">
      Aucune consommation sur les {{ days }} derniers jours.
    </p>
    <UsageCharts v-else-if="usage" :usage="usage" :selected-user="userId" @select-user="userId = $event" />
  </section>
</template>

<style scoped>
.admin-usage {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.admin-usage__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.admin-usage__header h2 {
  margin: 0;
}

.admin-usage__intro,
.admin-usage__current,
.admin-usage__empty {
  margin: 0;
  color: var(--text-mention-grey);
}

.admin-usage__current {
  font-size: 0.75rem;
}

.admin-usage__empty {
  margin: 3rem 0;
  text-align: center;
}
</style>
