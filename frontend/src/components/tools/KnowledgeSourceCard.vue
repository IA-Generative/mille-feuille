<script setup lang="ts">
import ToolAuthBadge from "@/components/tools/ToolAuthBadge.vue";
import { TOOL_VISIBILITY_LABELS } from "@/types/tool";
import type { KnowledgeSource } from "@/types/knowledge";

defineProps<{ source: KnowledgeSource }>();
const emit = defineEmits<{ remove: [id: string]; check: [id: string] }>();

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", { dateStyle: "medium" });
}
</script>

<template>
  <article class="knowledge-source-card">
    <header class="knowledge-source-card__header">
      <div class="knowledge-source-card__identity">
        <span class="knowledge-source-card__icon"><VIcon name="ri-book-2-line" /></span>
        <div>
          <h3 class="fr-h6 knowledge-source-card__title">{{ source.name }}</h3>
          <p class="knowledge-source-card__url">{{ source.url }}</p>
        </div>
      </div>
      <div class="knowledge-source-card__badges">
        <ToolAuthBadge :mode="source.authMode" />
        <DsfrBadge :label="TOOL_VISIBILITY_LABELS[source.visibility]" type="new" small no-icon />
      </div>
    </header>
    <footer class="knowledge-source-card__footer">
      <span class="knowledge-source-card__meta">
        ajoutée par {{ source.ownedByMe ? "vous" : source.ownerName }} le {{ formatDate(source.createdAt) }}
      </span>
      <div class="knowledge-source-card__actions">
        <DsfrButton
          label="Vérifier la connexion"
          icon="ri-refresh-line"
          tertiary
          no-outline
          size="sm"
          @click="emit('check', source.id)"
        />
        <DsfrButton
          v-if="source.ownedByMe"
          label="Supprimer"
          icon="ri-delete-bin-line"
          tertiary
          no-outline
          size="sm"
          @click="emit('remove', source.id)"
        />
      </div>
    </footer>
  </article>
</template>

<style scoped>
.knowledge-source-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1.25rem 1.5rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 1rem;
  background: var(--background-default-grey);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.knowledge-source-card__header,
.knowledge-source-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.knowledge-source-card__identity {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.knowledge-source-card__icon {
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

.knowledge-source-card__title,
.knowledge-source-card__url {
  margin: 0;
}

.knowledge-source-card__url {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
  overflow-wrap: anywhere;
}

.knowledge-source-card__badges,
.knowledge-source-card__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.knowledge-source-card__meta {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}
</style>
