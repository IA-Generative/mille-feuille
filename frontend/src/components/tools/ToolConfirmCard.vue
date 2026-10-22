<script setup lang="ts">
import type { PendingToolCall } from "@/composables/useToolConfirmation";

defineProps<{ call: PendingToolCall }>();
const emit = defineEmits<{ allow: []; deny: [] }>();
</script>

<template>
  <div class="tool-confirm-card" role="alertdialog" aria-label="Confirmer l'utilisation d'un outil">
    <div class="tool-confirm-card__header">
      <span class="tool-confirm-card__icon"><VIcon name="ri-edit-2-line" /></span>
      <div>
        <p class="tool-confirm-card__title">
          L'assistant souhaite utiliser <strong>{{ call.toolName }}</strong>
        </p>
        <p class="tool-confirm-card__subtitle">
          <template v-if="call.serverName">Serveur « {{ call.serverName }} » · </template>cet outil modifie des données.
        </p>
      </div>
    </div>
    <dl class="tool-confirm-card__args">
      <template v-for="(value, key) in call.args" :key="key">
        <dt>{{ key }}</dt>
        <dd>{{ value }}</dd>
      </template>
    </dl>
    <div class="tool-confirm-card__actions">
      <DsfrButton label="Refuser" secondary size="sm" @click="emit('deny')" />
      <DsfrButton label="Autoriser" size="sm" @click="emit('allow')" />
    </div>
  </div>
</template>

<style scoped>
.tool-confirm-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  padding: 1rem 1.25rem;
  border: 1px solid var(--border-default-warning, #b34000);
  border-radius: 1rem;
  background: var(--background-default-grey);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.tool-confirm-card__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.tool-confirm-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.75rem;
  background: #b340001a;
  color: #b34000;
  flex-shrink: 0;
}

.tool-confirm-card__title,
.tool-confirm-card__subtitle {
  margin: 0;
}

.tool-confirm-card__subtitle {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.tool-confirm-card__args {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.25rem 1rem;
  margin: 0;
  font-size: 0.8125rem;
}

.tool-confirm-card__args dt {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--text-mention-grey);
}

.tool-confirm-card__args dd {
  margin: 0;
}

.tool-confirm-card__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
