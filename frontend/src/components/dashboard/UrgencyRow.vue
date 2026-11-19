<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import SlotEditorModal from "@/components/dashboard/SlotEditorModal.vue";
import { DUE_LEVEL_LABELS, type DashboardUrgency } from "@/types/dashboard";
import type { SlotDraft } from "@/types/schedule";
import { slotOfUrgency, summarizeRecurrence } from "@/utils/recurrence";

const props = defineProps<{
  urgency: DashboardUrgency;
  /** Texte secondaire à droite (ex. « dans 2 j »). */
  meta?: string;
  /** Jour proposé pour un nouveau créneau (YYYY-MM-DD) ; par défaut aujourd'hui. */
  defaultDate?: string;
}>();

const emit = defineEmits<{
  /** `slot` à `null` : le créneau est supprimé. */
  schedule: [dossierId: string, slot: SlotDraft | null];
}>();

const pad = (n: number) => String(n).padStart(2, "0");
const toDateInput = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const timeOf = (iso: string) =>
  new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

const slot = computed(() => slotOfUrgency(props.urgency));

/** « 11 oct. · 14:00–16:00 » ou, si le créneau se répète, « Toutes les semaines le lundi · 14:00–16:00 ». */
const slotLabel = computed(() => {
  if (!slot.value) return null;
  const start = new Date(slot.value.start);
  const when = slot.value.recurrence
    ? summarizeRecurrence(slot.value.recurrence, start)
    : start.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
  return `${when} · ${timeOf(slot.value.start)}–${timeOf(slot.value.end)}`;
});

const editing = ref(false);

function onSave(next: SlotDraft) {
  emit("schedule", props.urgency.dossierId, next);
  editing.value = false;
}

function onRemove() {
  emit("schedule", props.urgency.dossierId, null);
  editing.value = false;
}
</script>

<template>
  <div class="urow">
    <RouterLink :to="`/dossiers/${urgency.dossierId}`" class="urow__link">
      <span class="urow__main">
        <span class="urow__title">{{ urgency.dossierName }}</span>
        <span class="urow__sub">{{ urgency.analyseName }} · {{ urgency.statusLabel }}</span>
      </span>
      <span
        v-if="urgency.level !== 'ok'"
        class="fr-badge fr-badge--sm fr-badge--no-icon"
        :class="urgency.level === 'overdue' ? 'fr-badge--error' : 'fr-badge--warning'"
      >
        {{ DUE_LEVEL_LABELS[urgency.level] }}
      </span>
      <span v-if="meta" class="urow__meta">{{ meta }}</span>
    </RouterLink>

    <button
      type="button"
      class="fr-btn fr-btn--sm urow__plan"
      :class="slot ? 'fr-btn--secondary' : 'fr-btn--tertiary'"
      @click="editing = true"
    >
      <VIcon :name="slot ? 'ri-calendar-check-line' : 'ri-calendar-event-line'" />
      <template v-if="slotLabel">
        <span class="fr-sr-only">Traitement planifié : </span>{{ slotLabel }}
        <VIcon v-if="slot?.recurrence" name="ri-repeat-line" aria-label="Se répète" />
        <VIcon v-if="slot?.reminders.length" name="ri-notification-3-line" aria-label="Avec rappel" />
      </template>
      <template v-else>Planifier</template>
    </button>

    <SlotEditorModal
      v-if="editing"
      :dossier-name="urgency.dossierName"
      :initial="slot"
      :default-date="defaultDate ?? toDateInput(new Date())"
      @save="onSave"
      @remove="onRemove"
      @close="editing = false"
    />
  </div>
</template>

<style scoped>
.urow {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.urow__link {
  display: flex;
  align-items: center;
  flex: 1;
  gap: 0.75rem;
  min-width: 0;
  padding: 0.5rem 0.625rem;
  border-radius: 0.375rem;
  background-image: none;
  color: var(--text-default-grey);
}

.urow__link:hover {
  background: var(--background-alt-grey-hover);
}

.urow__main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.urow__title {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.urow__sub,
.urow__meta {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.urow__meta {
  flex-shrink: 0;
  white-space: nowrap;
}

.urow__plan {
  gap: 0.375rem;
  flex-shrink: 0;
  max-width: 18rem;
  white-space: normal;
  text-align: left;
}

@media (max-width: 48em) {
  .urow {
    flex-wrap: wrap;
  }
}
</style>
