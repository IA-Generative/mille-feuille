<script setup lang="ts">
import type { ChatTool } from "@/types/chatTool";

defineProps<{ tool: ChatTool }>();
const active = defineModel<boolean>({ required: true });
</script>

<template>
  <li class="chat-tools-row">
    <span class="chat-tools-row__icon"><VIcon :name="tool.kind === 'mcp' ? 'ri-plug-line' : 'ri-tools-line'" scale="0.9" /></span>
    <span class="chat-tools-row__text" :title="tool.description">
      <span class="chat-tools-row__name">
        {{ tool.name }}
        <VIcon v-if="tool.sideEffect" name="ri-edit-2-line" scale="0.7" class="chat-tools-row__edit" />
      </span>
      <span class="chat-tools-row__description">
        <template v-if="tool.sideEffect">Modifie des données : votre accord sera demandé · </template>{{ tool.description }}
      </span>
    </span>
    <input
      v-model="active"
      type="checkbox"
      role="switch"
      class="chat-tools-row__switch"
      :aria-label="tool.name"
    />
  </li>
</template>

<style scoped>
.chat-tools-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.75rem;
}

.chat-tools-row:hover {
  background: var(--background-alt-grey);
}

.chat-tools-row__icon {
  display: inline-flex;
  color: var(--text-mention-grey);
}

.chat-tools-row__text {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.chat-tools-row__name {
  font-size: 0.875rem;
  font-weight: 500;
}

.chat-tools-row__edit {
  color: var(--text-default-warning);
}

.chat-tools-row__description {
  overflow: hidden;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Interrupteur discret, comme dans le menu de ChatGPT. */
.chat-tools-row__switch {
  appearance: none;
  flex-shrink: 0;
  position: relative;
  width: 2.25rem;
  height: 1.25rem;
  border-radius: 999px;
  background: var(--border-default-grey);
  cursor: pointer;
  transition: background 0.15s ease;
}

.chat-tools-row__switch::after {
  content: "";
  position: absolute;
  top: 0.125rem;
  left: 0.125rem;
  width: 1rem;
  height: 1rem;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.15s ease;
}

.chat-tools-row__switch:checked {
  background: #4b3fd9;
}

.chat-tools-row__switch:checked::after {
  transform: translateX(1rem);
}

.chat-tools-row__switch:focus-visible {
  outline: 2px solid #6a5cff;
  outline-offset: 2px;
}
</style>
