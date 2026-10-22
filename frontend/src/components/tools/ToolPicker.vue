<script setup lang="ts">
import { computed, ref, watch } from "vue";

import PaginationBar from "@/components/PaginationBar.vue";
import AddToolServerModal from "@/components/tools/AddToolServerModal.vue";
import ToolPickerGroup from "@/components/tools/ToolPickerGroup.vue";
import ToolSearchInput from "@/components/tools/ToolSearchInput.vue";
import ToolSourceFilter, { type ToolSourceOption } from "@/components/tools/ToolSourceFilter.vue";
import { useTools } from "@/composables/useTools";
import { matchesSearch } from "@/utils/toolSearch";
import type { Tool, ToolAuthMode } from "@/types/tool";

const selected = defineModel<string[]>({ required: true });


const { internalTools, servers } = useTools();

const query = ref("");
const source = ref("all");
const isAddOpened = ref(false);
const pageIndex = ref(0);
const pageSize = ref(5);

watch([query, source], () => (pageIndex.value = 0));

interface Group {
  id: string;
  title: string;
  authMode?: ToolAuthMode;
  tools: Tool[];
}

const groups = computed<Group[]>(() => [
  { id: "internal", title: "Outils internes", tools: internalTools.value },
  ...servers.value.map((server) => ({
    id: server.id,
    title: server.name,
    authMode: server.authMode,
    tools: server.tools.filter((tool) => tool.enabled),
  })),
].filter((group) => group.tools.length > 0));

const normalize = (text: string) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// Un tool est retenu s'il correspond à la recherche (nom, description ou nom du serveur).
const visibleGroups = computed(() => {
  return groups.value
    .filter((group) => source.value === "all" || group.id === source.value)
    .map((group) => ({
      ...group,
      tools: group.tools.filter((tool) => matchesSearch(query.value, `${tool.name} ${tool.description} ${group.title}`)),
    }))
    .filter((group) => group.tools.length > 0);
});

const totalVisible = computed(() => visibleGroups.value.reduce((total, group) => total + group.tools.length, 0));

// La pagination porte sur les tools à plat ; chaque page regroupe ensuite ses lignes par source.
const pageGroups = computed(() => {
  const rows = visibleGroups.value.flatMap((group) => group.tools.map((tool) => ({ group, tool })));
  const start = pageIndex.value * pageSize.value;
  const pageRows = rows.slice(start, start + pageSize.value);
  return visibleGroups.value
    .map((group) => ({ ...group, scope: group.tools, tools: pageRows.filter((row) => row.group === group).map((row) => row.tool) }))
    .filter((group) => group.tools.length > 0);
});

const sourceOptions = computed<ToolSourceOption[]>(() => [
  { id: "all", label: "Tous", count: groups.value.reduce((total, group) => total + group.tools.length, 0) },
  ...groups.value.map((group) => ({
    id: group.id,
    label: group.id === "internal" ? "Internes" : group.title,
    count: group.tools.length,
  })),
]);
</script>

<template>
  <div class="tool-picker">
    <div class="tool-picker__search">
      <ToolSearchInput v-model="query" />
      <DsfrButton label="Ajouter un serveur MCP" icon="ri-add-line" tertiary no-outline size="sm" @click="isAddOpened = true" />
    </div>
    <ToolSourceFilter v-model="source" :options="sourceOptions" />

    <div class="tool-picker__list">
      <ToolPickerGroup
        v-for="group in pageGroups"
        :key="group.id"
        v-model="selected"
        :title="group.title"
        :tools="group.tools"
        :scope="group.scope"
        :auth-mode="group.authMode"
      />
      <p v-if="totalVisible === 0" class="tool-picker__empty">Aucun outil ne correspond à « {{ query }} ».</p>
    </div>

    <PaginationBar v-model:page-index="pageIndex" v-model:page-size="pageSize" :total="totalVisible" label="Outils par page" />

    <AddToolServerModal v-model:opened="isAddOpened" />
  </div>
</template>

<style scoped>
.tool-picker {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
}

.tool-picker__search {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.tool-picker__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.tool-picker__empty {
  margin: 2rem 0;
  text-align: center;
  color: var(--text-mention-grey);
}
</style>
