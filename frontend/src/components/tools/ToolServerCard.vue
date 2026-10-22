<script setup lang="ts">
import ToolAuthBadge from "@/components/tools/ToolAuthBadge.vue";
import ToolTestButton from "@/components/tools/ToolTestButton.vue";
import { TOOL_VISIBILITY_LABELS, type ToolServer } from "@/types/tool";

defineProps<{ server: ToolServer }>();
const emit = defineEmits<{ remove: [id: string]; refresh: [id: string] }>();

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", { dateStyle: "medium" });
}
</script>

<template>
  <article class="server-card">
    <header class="server-card__header">
      <div class="server-card__identity">
        <span class="server-card__icon"><VIcon name="ri-plug-line" /></span>
        <div>
          <h3 class="fr-h6 server-card__title">{{ server.name }}</h3>
          <p class="server-card__url">{{ server.url }}</p>
        </div>
      </div>
      <div class="server-card__badges">
        <ToolAuthBadge :mode="server.authMode" />
        <DsfrBadge :label="TOOL_VISIBILITY_LABELS[server.visibility]" type="new" small no-icon />
      </div>
    </header>

    <ul class="server-card__tools">
      <li v-for="tool in server.tools" :key="tool.id" class="server-card__tool" :class="{ 'server-card__tool--off': !tool.enabled }">
        <span class="server-card__tool-name">{{ tool.name }}</span>
        <span class="server-card__tool-description">{{ tool.description }}</span>
        <span class="server-card__tool-actions">
          <span v-if="tool.sideEffect" class="server-card__side-effect" title="Demande une confirmation dans le chat">
            <VIcon name="ri-edit-2-line" scale="0.8" /> Modifie des données
          </span>
          <DsfrBadge v-if="!tool.enabled" label="Non autorisé" type="info" small no-icon />
          <ToolTestButton v-else :tool="tool" />
        </span>
      </li>
    </ul>

    <footer class="server-card__footer">
      <span class="server-card__meta">
        {{ server.tools.length }} tools · ajouté par {{ server.ownedByMe ? "vous" : server.ownerName }} · synchronisé le
        {{ formatDate(server.syncedAt) }}
      </span>
      <div v-if="server.ownedByMe" class="server-card__actions">
        <DsfrButton label="Actualiser" icon="ri-refresh-line" tertiary no-outline size="sm" @click="emit('refresh', server.id)" />
        <DsfrButton
          label="Supprimer"
          icon="ri-delete-bin-line"
          tertiary
          no-outline
          size="sm"
          @click="emit('remove', server.id)"
        />
      </div>
    </footer>
  </article>
</template>

<style scoped>
.server-card {
  background: var(--background-default-grey);
  border: 1px solid var(--border-default-grey);
  border-radius: 1rem;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.server-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.server-card__identity {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.server-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.75rem;
  background: linear-gradient(135deg, #6a5cff1a 0%, #ff6ca01a 100%);
  color: #4b3fd9;
  flex-shrink: 0;
}

.server-card__title {
  margin: 0;
}

.server-card__url {
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
  overflow-wrap: anywhere;
}

.server-card__badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.5rem;
}

.server-card__tools {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.server-card__tool {
  display: grid;
  grid-template-columns: minmax(10rem, 14rem) 1fr auto;
  align-items: center;
  gap: 1rem;
  padding: 0.3rem 0;
  border-top: 1px solid var(--border-default-grey);
  font-size: 0.875rem;
}

.server-card__tool--off {
  opacity: 0.6;
}

.server-card__tool-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 600;
}

.server-card__tool-description {
  color: var(--text-mention-grey);
}

.server-card__tool-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
}

.server-card__side-effect {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  color: var(--text-default-warning);
  white-space: nowrap;
}

.server-card__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.server-card__meta {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.server-card__actions {
  display: flex;
  gap: 0.25rem;
}
</style>
