<script setup lang="ts">
import { computed, onMounted } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";

import MarkdownText from "@/components/MarkdownText.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { useAuth } from "@/composables/useAuth";

const route = useRoute();
const router = useRouter();
const { getById, fetchAnalyse } = useAnalyses();
const { isAdmin } = useAuth();

const analyse = computed(() => getById(String(route.params.id)));

onMounted(() => {
  if (!analyse.value) fetchAnalyse(String(route.params.id));
});

// Les onglets sont pilotés par la route : chaque onglet correspond à une
// route enfant (classification, extraction, agents). L'index actif est
// déduit du nom de la route courante. Les champs tabId/panelId sont
// requis par DsfrTabs pour les attributs ARIA.
const allTabs = [
  { title: "Classification documentaire", icon: "ri-price-tag-3-line", tabId: "tab-classification", panelId: "panel-classification", routeName: "analyse-classification" },
  { title: "Extraction d'entités nommées", icon: "ri-braces-line", tabId: "tab-extraction", panelId: "panel-extraction", routeName: "analyse-extraction" },
  { title: "Agents", icon: "ri-robot-line", tabId: "tab-agents", panelId: "panel-agents", routeName: "analyse-agents" },
  { title: "Statuts et échéance", icon: "ri-flag-line", tabId: "tab-statuses", panelId: "panel-statuses", routeName: "analyse-statuses" },
  { title: "Sources", icon: "ri-inbox-archive-line", tabId: "tab-sources", panelId: "panel-sources", routeName: "analyse-sources" },
  { title: "Suivi", icon: "ri-table-line", tabId: "tab-tracking", panelId: "panel-tracking", routeName: "analyse-tracking" },
  // Modèles de document de l'analyse : réservés aux administrateurs, comme leur API (backend issue #138).
  { title: "Documents", icon: "ri-file-word-2-line", tabId: "tab-documents", panelId: "panel-documents", routeName: "analyse-documents", adminOnly: true },
] as const;

const tabs = computed(() => allTabs.filter((tab) => !("adminOnly" in tab && tab.adminOnly) || isAdmin.value));

const activeTabIndex = computed(() => {
  const index = tabs.value.findIndex((tab) => tab.routeName === route.name);
  return index === -1 ? 0 : index;
});


function selectTab(index: number) {
  const tab = tabs.value[index];
  if (tab) {
    router.push({ name: tab.routeName, params: route.params });
  }
}
</script>

<template>
  <div v-if="analyse">
    <RouterLink to="/analyses" class="fr-link fr-icon-arrow-left-line fr-link--icon-left analyse-detail__back">
      Retour aux analyses
    </RouterLink>

    <div class="analyse-detail__header">
      <div>
        <h1 class="fr-h2">{{ analyse.name }}</h1>
        <MarkdownText :content="analyse.description" class="fr-text--lead" />
      </div>
    </div>

    <DsfrTabs
      :model-value="activeTabIndex"
      tab-list-name="Sections de l'analyse"
      :tab-titles="tabs"
      @update:model-value="selectTab"
    >
      <!-- Un panneau par onglet : DsfrTabs mesure le panneau de l'onglet actif (panels[index]) pour dimensionner la
           zone, avec un seul panneau les onglets autres que le premier étaient coupés. Seule la route active est rendue. -->
      <DsfrTabContent v-for="tab in tabs" :key="tab.tabId" :panel-id="tab.panelId" :tab-id="tab.tabId">
        <RouterView v-if="tab.routeName === route.name" />
      </DsfrTabContent>
    </DsfrTabs>
  </div>
  <div v-else>
    <p>Chargement…</p>
    <RouterLink to="/analyses" class="fr-link">Retour aux analyses</RouterLink>
  </div>
</template>

<style scoped>
.analyse-detail__back {
  display: inline-flex;
  margin-bottom: 1.5rem;
}

.analyse-detail__header {
  margin-bottom: 2rem;
}
</style>
