<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

import { useChatAgents } from "@/composables/useChatAgents";

// Les agents de l'analyse, interrogeables dans le chat. Le plan du chat choisit lui-même celui qui répond ; ce menu
// dit seulement qui est là, et propose d'adresser sa question à l'un d'eux (la phrase est placée dans la zone de saisie).
const props = defineProps<{ dossierId: string }>();
const emit = defineEmits<{ pick: [text: string] }>();

const { agents, error, load } = useChatAgents(props.dossierId);
onMounted(load);

const root = ref<HTMLElement>();
const opened = ref(false);

function pick(name: string) {
  emit("pick", `Demande à l'agent ${name} : `);
  opened.value = false;
}

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
  <div v-if="agents.length > 0" ref="root" class="chat-agents-menu">
    <button
      type="button"
      class="chat-agents-menu__trigger"
      aria-label="Agents de l'analyse"
      title="Agents de l'analyse"
      :aria-expanded="opened"
      @click="opened = !opened"
    >
      <VIcon name="ri-robot-2-line" />
    </button>

    <div v-if="opened" class="chat-agents-menu__panel" role="dialog" aria-label="Agents de l'analyse">
      <div class="chat-agents-menu__header">
        <p class="chat-agents-menu__title">Agents de l'analyse</p>
        <p class="chat-agents-menu__hint">
          L'assistant choisit l'agent qui répond selon votre question. Vous pouvez aussi vous adresser à l'un d'eux.
        </p>
      </div>
      <ul class="chat-agents-menu__rows">
        <li v-for="agent in agents" :key="agent.name">
          <button type="button" class="chat-agents-menu__row" @click="pick(agent.name)">
            <span class="chat-agents-menu__name">{{ agent.name }}</span>
            <span class="chat-agents-menu__role">{{ agent.role }}</span>
          </button>
        </li>
      </ul>
      <p v-if="error" class="chat-agents-menu__error" role="alert">{{ error }}</p>
    </div>
  </div>
</template>

<style scoped>
.chat-agents-menu {
  position: relative;
  flex-shrink: 0;
}

.chat-agents-menu__trigger {
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

.chat-agents-menu__trigger:hover {
  background: var(--background-alt-grey-hover);
  color: var(--text-default-grey);
}

.chat-agents-menu__panel {
  position: absolute;
  bottom: calc(100% + 0.75rem);
  left: -0.5rem;
  z-index: 10;
  display: flex;
  flex-direction: column;
  width: 22rem;
  max-width: 90vw;
  border: 1px solid var(--border-default-grey);
  border-radius: 1.25rem;
  background: var(--background-default-grey);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}

.chat-agents-menu__header {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 1rem 1rem 0.5rem;
}

.chat-agents-menu__title {
  margin: 0;
  font-weight: 600;
}

.chat-agents-menu__hint {
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.chat-agents-menu__rows {
  max-height: 20rem;
  margin: 0;
  padding: 0 0.5rem 0.75rem;
  overflow-y: auto;
  list-style: none;
}

.chat-agents-menu__row {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  width: 100%;
  padding: 0.625rem 0.75rem;
  border: none;
  border-radius: 0.75rem;
  background: transparent;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.chat-agents-menu__row:hover,
.chat-agents-menu__row:focus-visible {
  background: var(--background-alt-grey-hover);
}

.chat-agents-menu__name {
  font-weight: 600;
  font-size: 0.875rem;
}

.chat-agents-menu__role {
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.chat-agents-menu__error {
  margin: 0 1rem 0.75rem;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}
</style>
