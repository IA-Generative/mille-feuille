<script setup lang="ts">
import { FIELD_ORIGIN_LABELS, FIELD_STATUS_LABELS, valueToText, type DraftField, type FieldVersion } from "@/types/documentDraft";

import AppModal from "@/components/AppModal.vue";
// Historique d'un champ : toutes ses versions, de la plus récente à la plus ancienne. Restaurer ajoute une version
// (validée d'office, c'est une décision de la personne), rien n'est supprimé ni écrasé.
defineProps<{
  field: DraftField | null;
  versions: FieldVersion[];
  loading: boolean;
  canRestore: boolean;
}>();
const emit = defineEmits<{ close: []; restore: [versionId: string] }>();

const dateFormatter = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" });
</script>

<template>
  <AppModal :opened="field !== null" :title="field ? `Historique : ${field.label}` : ''" icon="ri-history-line" size="lg" @close="emit('close')">
    <p v-if="loading" class="fr-text--sm">Chargement…</p>
    <ul v-else class="field-history">
      <li v-for="(version, index) in versions" :key="version.id" class="field-history__item">
        <div class="field-history__head">
          <strong>Version {{ version.versionNumber }}</strong>
          <DsfrBadge :label="FIELD_STATUS_LABELS[version.status]" :type="version.status === 'validé' ? 'success' : version.status === 'proposé' ? 'info' : 'new'" small />
          <DsfrBadge v-if="index === 0" label="Actuelle" small />
          <span class="fr-text--xs field-history__meta">
            {{ FIELD_ORIGIN_LABELS[version.origin] }}<span v-if="version.restoredFromVersionId"> · restaurée</span> ·
            {{ dateFormatter.format(new Date(version.createdAt)) }}
          </span>
        </div>
        <p v-if="field && valueToText(version.value, field.type)" class="field-history__value">
          {{ valueToText(version.value, field.type) }}
        </p>
        <p v-else class="field-history__value field-history__value--empty">Pas de valeur</p>
        <p v-if="version.reason" class="fr-text--xs field-history__meta">Motif : {{ version.reason }}</p>
        <DsfrButton
          v-if="canRestore && index !== 0 && version.value !== null"
          label="Restaurer cette valeur"
          tertiary
          size="sm"
          @click="emit('restore', version.id)"
        />
      </li>
    </ul>
  </AppModal>
</template>

<style scoped>
.field-history {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.field-history__item {
  border-top: 1px solid var(--border-default-grey);
  padding-top: 0.75rem;
}

.field-history__item:first-child {
  border-top: none;
  padding-top: 0;
}

.field-history__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.field-history__value {
  margin: 0.25rem 0;
  white-space: pre-wrap;
}

.field-history__value--empty {
  color: var(--text-mention-grey);
  font-style: italic;
}

.field-history__meta {
  color: var(--text-mention-grey);
  margin: 0;
}
</style>
