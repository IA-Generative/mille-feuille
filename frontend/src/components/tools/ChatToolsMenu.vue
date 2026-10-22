<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, toRef, watch } from "vue";

import ChatToolsMenuRow from "@/components/tools/ChatToolsMenuRow.vue";
import ToolSearchInput from "@/components/tools/ToolSearchInput.vue";
import { useConversationTools } from "@/composables/useConversationTools";
import type { ChatTool } from "@/types/chatTool";
import { matchesSearch } from "@/utils/toolSearch";

// Les outils que l'analyse autorise pour cette conversation. L'assistant choisit lui-même parmi ceux qui sont activés ;
// la personne ne peut que retirer, jamais ajouter un outil que l'analyse n'autorise pas.
const props = defineProps<{ dossierId: string; conversationId: string | undefined }>();

const { tools, excluded, unavailable, error, load, setExcluded } = useConversationTools(
  props.dossierId,
  toRef(props, "conversationId"),
);
onMounted(load);
watch(() => props.conversationId, load);

const root = ref<HTMLElement>();
const opened = ref(false);
const query = ref("");

interface Section {
  id: string;
  title: string;
  tools: ChatTool[];
}

const sections = computed<Section[]>(() => {
  const matching = tools.value.filter((tool) =>
    matchesSearch(query.value, `${tool.name} ${tool.description} ${tool.serverName ?? ""}`),
  );
  const internal = matching.filter((tool) => tool.kind === "internal");
  const byServer = new Map<string, ChatTool[]>();
  for (const tool of matching.filter((candidate) => candidate.kind === "mcp")) {
    byServer.set(tool.serverName ?? "", [...(byServer.get(tool.serverName ?? "") ?? []), tool]);
  }
  return [
    { id: "internal", title: "Outils internes", tools: internal },
    ...[...byServer].map(([name, list]) => ({ id: name, title: name, tools: list })),
  ].filter((section) => section.tools.length > 0);
});

const activeCount = computed(() => tools.value.filter((tool) => !excluded.value.includes(tool.id)).length);
const isRestricted = computed(() => activeCount.value < tools.value.length);
const hasAnything = computed(() => tools.value.length > 0 || unavailable.value.length > 0);

const isActive = (tool: ChatTool) => !excluded.value.includes(tool.id);

function setActive(id: string, active: boolean) {
  setExcluded(active ? excluded.value.filter((removed) => removed !== id) : [...excluded.value, id]);
}

const enableAll = () => setExcluded([]);

function onDocumentClick(event: MouseEvent) {
  if (opened.value && root.value && !root.value.contains(event.target as Node)) opened.value = false;
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") opened.value = false;
}

onMounted(() => {
  document.addEventListener("click", onDocumentClick);
  document.addEventListener("keydown", onKeydown);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", onDocumentClick);
  document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div v-if="hasAnything" ref="root" class="chat-tools-menu">
    <button
      type="button"
      class="chat-tools-menu__trigger"
      :class="{ 'chat-tools-menu__trigger--restricted': isRestricted }"
      aria-label="Outils de la conversation"
      title="Outils de la conversation"
      :aria-expanded="opened"
      @click="opened = !opened"
    >
      <VIcon name="ri-tools-line" />
      <span v-if="isRestricted" class="chat-tools-menu__count">{{ activeCount }}</span>
    </button>

    <div v-if="opened" class="chat-tools-menu__panel" role="dialog" aria-label="Outils de la conversation">
      <div class="chat-tools-menu__header">
        <p class="chat-tools-menu__title">Outils de la conversation</p>
        <p class="chat-tools-menu__hint">L'assistant choisit lui-même parmi les outils activés.</p>
        <ToolSearchInput v-model="query" />
      </div>

      <div class="chat-tools-menu__list">
        <section v-for="section in sections" :key="section.id">
          <h4 class="chat-tools-menu__section">{{ section.title }}</h4>
          <ul class="chat-tools-menu__rows">
            <ChatToolsMenuRow
              v-for="tool in section.tools"
              :key="tool.id"
              :model-value="isActive(tool)"
              :tool="tool"
              @update:model-value="setActive(tool.id, $event)"
            />
          </ul>
        </section>
        <p v-if="sections.length === 0" class="chat-tools-menu__empty">Aucun outil ne correspond.</p>
        <p v-if="unavailable.length > 0" class="chat-tools-menu__unavailable">
          {{ unavailable.length }} outil{{ unavailable.length > 1 ? "s" : "" }} prévu{{ unavailable.length > 1 ? "s" : "" }}
          par l'analyse {{ unavailable.length > 1 ? "ne sont" : "n'est" }} pas utilisable{{ unavailable.length > 1 ? "s" : "" }}
          avec vos droits.
        </p>
        <p v-if="error" class="chat-tools-menu__unavailable" role="alert">{{ error }}</p>
      </div>

      <div class="chat-tools-menu__footer">
        <span>{{ activeCount }} sur {{ tools.length }} activés</span>
        <button v-if="isRestricted" type="button" class="chat-tools-menu__link" @click="enableAll">Tout activer</button>
        <RouterLink to="/outils" class="chat-tools-menu__link">Gérer mes outils</RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-tools-menu {
  position: relative;
  flex-shrink: 0;
}

.chat-tools-menu__trigger {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-mention-grey);
  cursor: pointer;
}

.chat-tools-menu__trigger:hover {
  background: var(--background-alt-grey-hover);
  color: var(--text-default-grey);
}

.chat-tools-menu__trigger--restricted {
  color: #4b3fd9;
}

.chat-tools-menu__count {
  position: absolute;
  top: 0;
  right: 0;
  min-width: 1rem;
  padding: 0 0.25rem;
  border-radius: 999px;
  background: #4b3fd9;
  color: #fff;
  font-size: 0.625rem;
  line-height: 1rem;
  text-align: center;
}

.chat-tools-menu__panel {
  position: absolute;
  bottom: calc(100% + 0.75rem);
  left: -0.5rem;
  z-index: 10;
  display: flex;
  flex-direction: column;
  width: 24rem;
  max-width: 90vw;
  border: 1px solid var(--border-default-grey);
  border-radius: 1.25rem;
  background: var(--background-default-grey);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}

.chat-tools-menu__header {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem 1rem 0.5rem;
}

.chat-tools-menu__title {
  margin: 0;
  font-weight: 600;
}

.chat-tools-menu__hint {
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.chat-tools-menu__list {
  max-height: 24rem;
  overflow-y: auto;
  padding: 0 0.5rem;
}

.chat-tools-menu__section {
  margin: 0.75rem 0.75rem 0.25rem;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-mention-grey);
}

.chat-tools-menu__rows {
  list-style: none;
  margin: 0;
  padding: 0;
}

.chat-tools-menu__empty {
  margin: 1.5rem 0;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}

.chat-tools-menu__unavailable {
  margin: 0.75rem 0.75rem 0.25rem;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.chat-tools-menu__footer {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--border-default-grey);
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.chat-tools-menu__footer span {
  margin-right: auto;
}

.chat-tools-menu__link {
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  color: #4b3fd9;
  cursor: pointer;
  text-decoration: underline;
}
</style>
