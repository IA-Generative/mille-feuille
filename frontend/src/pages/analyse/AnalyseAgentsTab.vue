<script setup lang="ts">
import { computed, onMounted, provide, ref } from "vue";
import { useRoute } from "vue-router";

import AddAgentModal from "@/components/analyses/AddAgentModal.vue";
import AgentCard from "@/components/analyses/AgentCard.vue";
import KnowledgeCollectionsField from "@/components/tools/KnowledgeCollectionsField.vue";
import { useAnalyses } from "@/composables/useAnalyses";

const route = useRoute();
const { getById, fetchAnalyse } = useAnalyses();

const analyse = computed(() => getById(String(route.params.id)));
// Le sélecteur d'outils d'un agent compte les collections de cette analyse (outil « Base de connaissances »).
provide("analyseId", String(route.params.id));

onMounted(() => {
  if (!analyse.value) fetchAnalyse(String(route.params.id));
});

const isAddAgentModalOpened = ref(false);
</script>

<template>
  <div v-if="analyse" class="analyse-agents-tab">
    <KnowledgeCollectionsField :analyse-id="analyse.id" />

    <div class="analyse-agents-tab__header">
      <p class="fr-text--sm">
        Agents créés pour un but métier propre à cette analyse (cohérence, rédaction, timeline...).
      </p>
      <DsfrButton label="Créer un agent" icon="ri-robot-line" @click="isAddAgentModalOpened = true" />
    </div>

    <p v-if="analyse.agents.length === 0" class="fr-text--sm">Aucun agent créé pour cette analyse.</p>

    <div v-else class="analyse-agents-tab__list">
      <AgentCard v-for="agent in analyse.agents" :key="agent.id" :analyse-id="analyse.id" :agent="agent" />
    </div>

    <AddAgentModal :analyse-id="analyse.id" v-model:opened="isAddAgentModalOpened" />
  </div>
  <div v-else>
    <p>Chargement…</p>
  </div>
</template>

<style scoped>
.analyse-agents-tab {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.analyse-agents-tab__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.analyse-agents-tab__list {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}
</style>
