<script setup lang="ts">
import { ref, watch } from "vue";

import AdminReportsTab from "@/components/admin/AdminReportsTab.vue";
import AdminStatsTab from "@/components/admin/AdminStatsTab.vue";
import AdminTasksTab from "@/components/admin/AdminTasksTab.vue";
import AdminCguTab from "@/components/admin/AdminCguTab.vue";
import AdminDocumentGenerationTab from "@/components/admin/AdminDocumentGenerationTab.vue";
import AdminUsageTab from "@/components/admin/AdminUsageTab.vue";

// ── Onglets ─────────────────────────────────────────────────────────────
// Les données sont chargées paresseusement à la première ouverture de chaque
// onglet, pour éviter de tout charger d'un coup au montage de la page.
const selectedTab = ref(0);
const tabs = [
  { title: "Signalements", icon: "ri-bug-line", tabId: "tab-reports", panelId: "panel-reports" },
  { title: "Statistiques", icon: "ri-bar-chart-2-line", tabId: "tab-stats", panelId: "panel-stats" },
  { title: "Tâches Celery", icon: "ri-list-check-2", tabId: "tab-tasks", panelId: "panel-tasks" },
  { title: "CGU", icon: "ri-file-text-line", tabId: "tab-cgu", panelId: "panel-cgu" },
  { title: "Génération des documents", icon: "ri-file-word-2-line", tabId: "tab-generation", panelId: "panel-generation" },
  { title: "Consommation", icon: "ri-drop-line", tabId: "tab-usage", panelId: "panel-usage" },
] as const;

const loadedTabs = ref(new Set<number>());

// Refs vers les composants pour déclencher le chargement paresseux.
const reportsTabRef = ref<InstanceType<typeof AdminReportsTab>>();
const statsTabRef = ref<InstanceType<typeof AdminStatsTab>>();
const tasksTabRef = ref<InstanceType<typeof AdminTasksTab>>();
const cguTabRef = ref<InstanceType<typeof AdminCguTab>>();
const generationTabRef = ref<InstanceType<typeof AdminDocumentGenerationTab>>();
const usageTabRef = ref<InstanceType<typeof AdminUsageTab>>();

watch(selectedTab, (idx) => {
  if (loadedTabs.value.has(idx)) return;
  loadedTabs.value.add(idx);
  if (idx === 0) reportsTabRef.value?.reload();
  if (idx === 1) statsTabRef.value?.fetchStats();
  if (idx === 2) tasksTabRef.value?.fetchTasks();
  if (idx === 3) cguTabRef.value?.reload();
  if (idx === 4) generationTabRef.value?.reload();
  if (idx === 5) usageTabRef.value?.reload();
}, { immediate: true });
</script>

<template>
  <div class="administration-page">
    <h1 class="fr-h2">Administration</h1>

    <DsfrTabs
      v-model="selectedTab"
      tab-list-name="Sections d'administration"
      :tab-titles="tabs"
    >
      <DsfrTabContent :panel-id="tabs[0].panelId" :tab-id="tabs[0].tabId">
        <AdminReportsTab ref="reportsTabRef" />
      </DsfrTabContent>

      <DsfrTabContent :panel-id="tabs[1].panelId" :tab-id="tabs[1].tabId">
        <AdminStatsTab ref="statsTabRef" />
      </DsfrTabContent>

      <DsfrTabContent :panel-id="tabs[2].panelId" :tab-id="tabs[2].tabId">
        <AdminTasksTab ref="tasksTabRef" />
      </DsfrTabContent>

      <DsfrTabContent :panel-id="tabs[3].panelId" :tab-id="tabs[3].tabId">
        <AdminCguTab ref="cguTabRef" />
      </DsfrTabContent>

      <DsfrTabContent :panel-id="tabs[4].panelId" :tab-id="tabs[4].tabId">
        <AdminDocumentGenerationTab ref="generationTabRef" />
      </DsfrTabContent>

      <DsfrTabContent :panel-id="tabs[5].panelId" :tab-id="tabs[5].tabId">
        <AdminUsageTab ref="usageTabRef" />
      </DsfrTabContent>
    </DsfrTabs>
  </div>
</template>

<style scoped>
.administration-page {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}
</style>
