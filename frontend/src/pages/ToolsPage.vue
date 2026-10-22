<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import AddKnowledgeSourceModal from "@/components/tools/AddKnowledgeSourceModal.vue";
import AddToolServerModal from "@/components/tools/AddToolServerModal.vue";
import InternalToolRow from "@/components/tools/InternalToolRow.vue";
import KnowledgeSourceCard from "@/components/tools/KnowledgeSourceCard.vue";
import ToolSearchInput from "@/components/tools/ToolSearchInput.vue";
import ToolServerCard from "@/components/tools/ToolServerCard.vue";
import ToolsListSection from "@/components/tools/ToolsListSection.vue";
import { useKnowledgeSources } from "@/composables/useKnowledgeSources";
import { useTools } from "@/composables/useTools";
import { matchesSearch } from "@/utils/toolSearch";

const { internalTools, servers, loading, error, fetchTools, removeServer, refreshServer } = useTools();
const {
  sources: knowledgeSources,
  error: sourcesError,
  fetchSources,
  checkSource,
  removeSource,
} = useKnowledgeSources();
const isAddOpened = ref(false);
const isAddSourceOpened = ref(false);
const actionError = ref("");
const actionNotice = ref("");

onMounted(() => Promise.all([fetchTools(true), fetchSources(true)]));

// Une action sur un serveur (actualiser, supprimer) peut échouer : on le dit plutôt que de ne rien faire.
async function run(action: () => Promise<void>, notice = "") {
  actionError.value = "";
  actionNotice.value = "";
  try {
    await action();
    actionNotice.value = notice;
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : "L'action a échoué.";
  }
}
const query = ref("");

const filteredSources = computed(() =>
  knowledgeSources.value.filter((source) => matchesSearch(query.value, `${source.name} ${source.url}`)),
);

const filteredInternalTools = computed(() =>
  internalTools.value.filter((tool) => matchesSearch(query.value, `${tool.name} ${tool.description}`)),
);

// Un serveur dont le nom ou l'adresse correspond reste entier ; sinon on n'en garde que les tools qui correspondent.
const filteredServers = computed(() =>
  servers.value.flatMap((server) => {
    if (matchesSearch(query.value, `${server.name} ${server.url}`)) return [server];
    const tools = server.tools.filter((tool) => matchesSearch(query.value, `${tool.name} ${tool.description}`));
    return tools.length > 0 ? [{ ...server, tools }] : [];
  }),
);
</script>

<template>
  <div class="tools-page">
    <div class="tools-page__header">
      <h1 class="fr-h2">Mes outils</h1>
      <div class="tools-page__buttons">
        <DsfrButton label="Ajouter une source de connaissances" icon="ri-book-2-line" secondary @click="isAddSourceOpened = true" />
        <DsfrButton label="Ajouter un serveur MCP" icon="ri-add-line" @click="isAddOpened = true" />
      </div>
    </div>
    <p class="tools-page__intro">
      Les outils que les agents peuvent utiliser. Les outils internes sont fournis par la plateforme ; les serveurs MCP
      et les sources de connaissances sont ajoutés par les utilisateurs. Chaque agent choisit, dans son analyse, ceux
      dont il a besoin, et l'analyse choisit les collections qu'ils peuvent interroger.
    </p>

    <div v-if="error || sourcesError || actionError" class="fr-alert fr-alert--error" role="alert">
      {{ error || sourcesError || actionError }}
    </div>
    <div v-else-if="actionNotice" class="fr-alert fr-alert--success fr-alert--sm" role="status">{{ actionNotice }}</div>
    <p v-else-if="loading && servers.length === 0 && internalTools.length === 0" class="tools-page__empty">Chargement…</p>

    <ToolSearchInput v-model="query" class="tools-page__search" />

    <ToolsListSection title="Serveurs MCP" :total="filteredServers.length" :reset-key="query">
      <template #default="{ start, end }">
        <ToolServerCard
          v-for="server in filteredServers.slice(start, end)"
          :key="server.id"
          :server="server"
          @remove="run(() => removeServer($event))"
          @refresh="run(() => refreshServer($event))"
        />
      </template>
      <template #empty>
        <p class="tools-page__empty">{{ query ? "Aucun serveur ne correspond." : "Aucun serveur MCP pour le moment." }}</p>
      </template>
    </ToolsListSection>

    <ToolsListSection title="Bases de connaissances" :total="filteredSources.length" :reset-key="query">
      <template #default="{ start, end }">
        <KnowledgeSourceCard
          v-for="source in filteredSources.slice(start, end)"
          :key="source.id"
          :source="source"
          @remove="run(() => removeSource($event))"
          @check="run(() => checkSource($event), 'La source répond comme le contrat de la base de connaissances.')"
        />
      </template>
      <template #empty>
        <p class="tools-page__empty">{{ query ? "Aucune source ne correspond." : "Aucune source de connaissances pour le moment." }}</p>
      </template>
    </ToolsListSection>

    <ToolsListSection title="Outils internes" :total="filteredInternalTools.length" :reset-key="query">
      <template #default="{ start, end }">
        <ul class="tools-page__internal">
          <InternalToolRow v-for="tool in filteredInternalTools.slice(start, end)" :key="tool.id" :tool="tool" />
        </ul>
      </template>
      <template #empty>
        <p class="tools-page__empty">Aucun outil interne ne correspond.</p>
      </template>
    </ToolsListSection>

    <AddToolServerModal v-model:opened="isAddOpened" />
    <AddKnowledgeSourceModal v-model:opened="isAddSourceOpened" />
  </div>
</template>

<style scoped>
.tools-page {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.tools-page__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.tools-page__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.tools-page__header h1 {
  margin: 0;
}

.tools-page__intro {
  margin: 0;
  color: var(--text-mention-grey);
}

.tools-page__search {
  max-width: 32rem;
}

.tools-page__internal {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tools-page__empty {
  color: var(--text-mention-grey);
}
</style>
