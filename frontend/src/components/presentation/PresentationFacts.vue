<script setup lang="ts">
import { computed } from "vue";

import type { PresentationClassification } from "@/types/dossierPresentation";

// Les chiffres à retenir, en une ligne : la nature du dossier et ce que l'analyse a produit.
const props = defineProps<{
  classification?: PresentationClassification;
  entityCount: number;
  agentCount: number;
  documentCount: number;
}>();

const plural = (count: number, one: string, many: string) => `${count} ${count > 1 ? many : one}`;

const facts = computed(() => [
  plural(props.documentCount, "document", "documents"),
  plural(props.entityCount, "information extraite", "informations extraites"),
  ...(props.agentCount > 0 ? [plural(props.agentCount, "synthèse", "synthèses")] : []),
]);
</script>

<template>
  <div class="presentation-facts">
    <p v-if="classification" class="presentation-facts__kind">
      <VIcon name="ri-price-tag-3-line" aria-hidden="true" />
      <span>{{ classification.label }}</span>
      <span v-if="classification.confidence !== undefined" class="presentation-facts__confidence">
        Confiance {{ classification.confidence }} %
      </span>
    </p>
    <p class="presentation-facts__counts">{{ facts.join(" · ") }}</p>
  </div>
</template>

<style scoped>
.presentation-facts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}

.presentation-facts p {
  margin: 0;
}

.presentation-facts__kind {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.125rem 0.375rem;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  background: var(--background-contrast-grey);
  font-size: 0.875rem;
  font-weight: 500;
}

.presentation-facts__confidence {
  white-space: nowrap;
  color: var(--text-mention-grey);
  font-weight: 400;
}

.presentation-facts__counts {
  color: var(--text-mention-grey);
  font-size: 0.875rem;
}
</style>
