<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import InfoModal from "@/components/InfoModal.vue";
import { useReports } from "@/composables/useReports";
import { REPORT_STATUS_LABELS, REPORT_TYPE_LABELS, type ReportType } from "@/types/report";
import { userMessage } from "@/utils/api";

defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();

const { reports, fetchMyReports, createReport } = useReports();

const typeOptions = (Object.keys(REPORT_TYPE_LABELS) as ReportType[]).map((value) => ({
  value,
  text: REPORT_TYPE_LABELS[value],
}));

const type = ref<ReportType>("bug");
const title = ref("");
const description = ref("");
const screenshot = ref<Blob | null>(null);
const screenshotPreviewUrl = ref<string | null>(null);
const isSubmitting = ref(false);
const submitted = ref(false);
const error = ref("");

onMounted(fetchMyReports);

function setScreenshot(blob: Blob | null) {
  if (screenshotPreviewUrl.value) URL.revokeObjectURL(screenshotPreviewUrl.value);
  screenshot.value = blob;
  screenshotPreviewUrl.value = blob ? URL.createObjectURL(blob) : null;
}

function onFileChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (file) setScreenshot(file);
}

// Une capture prise avec l'outil du système atterrit dans le
// presse-papiers : coller ici est le moyen le plus simple d'attacher une
// capture sans bibliothèque de rendu DOM (et ses cas limites).
function onPaste(event: ClipboardEvent) {
  const item = Array.from(event.clipboardData?.items ?? []).find((entry) => entry.type.startsWith("image/"));
  const file = item?.getAsFile();
  if (file) setScreenshot(file);
}

const canSubmit = computed(() => title.value.trim() !== "" && description.value.trim() !== "" && !isSubmitting.value);

async function submit() {
  if (!canSubmit.value) return;
  isSubmitting.value = true;
  error.value = "";
  try {
    await createReport(type.value, title.value.trim(), description.value.trim(), screenshot.value);
    title.value = "";
    description.value = "";
    setScreenshot(null);
    submitted.value = true;
  } catch (err) {
    error.value = userMessage(err, "Échec de l'envoi.");
  } finally {
    isSubmitting.value = false;
  }
}

const dateFormatter = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium" });
function formatDate(iso: string) {
  return dateFormatter.format(new Date(iso));
}
</script>

<template>
  <InfoModal title="Signaler un bug, une idée ou une question" :open="open" @close="emit('close')">
    <form class="report-form" @submit.prevent="submit">
      <DsfrSelect v-model="type" label="Type" label-visible :options="typeOptions" />
      <DsfrInput v-model="title" label="Titre" label-visible placeholder="En une phrase…" required />
      <DsfrInput
        v-model="description"
        label="Description"
        label-visible
        is-textarea
        placeholder="Décrivez ce que vous avez observé, ou votre idée…"
        required
        @paste="onPaste"
      />

      <div class="report-form__screenshot">
        <p class="fr-text--sm report-form__screenshot-label">Capture d'écran (optionnel)</p>
        <img v-if="screenshotPreviewUrl" :src="screenshotPreviewUrl" alt="Aperçu de la capture d'écran jointe" />
        <p v-else class="fr-text--sm report-form__screenshot-hint">
          Collez une capture (Ctrl+V) dans la description, ou choisissez un fichier.
        </p>
        <div class="report-form__screenshot-actions">
          <input type="file" accept="image/*" aria-label="Choisir une capture d'écran" @change="onFileChange" />
          <DsfrButton v-if="screenshot" label="Retirer" tertiary size="sm" @click="setScreenshot(null)" />
        </div>
      </div>

      <DsfrAlert v-if="error" alert type="error" small :description="error" />
      <p v-if="submitted" class="report-form__success">Signalement envoyé, merci !</p>

      <DsfrButton type="submit" label="Envoyer" :disabled="!canSubmit" />
    </form>

    <section class="report-form__history">
      <h3 class="fr-h6">Mes signalements</h3>
      <p v-if="reports.length === 0" class="fr-text--sm">Aucun signalement pour le moment.</p>
      <ul v-else class="report-form__history-list">
        <li v-for="report in reports" :key="report.id" class="report-form__history-item">
          <div class="report-form__history-row">
            <span class="report-form__history-title">{{ report.title }}</span>
            <DsfrBadge :label="REPORT_STATUS_LABELS[report.status]" small />
          </div>
          <p class="fr-text--sm report-form__history-meta">
            {{ REPORT_TYPE_LABELS[report.type] }} · {{ formatDate(report.createdAt) }}
          </p>
          <p v-if="report.adminResponse" class="fr-text--sm report-form__history-response">
            <strong>Réponse :</strong> {{ report.adminResponse }}
          </p>
        </li>
      </ul>
    </section>
  </InfoModal>
</template>

<style scoped>
.report-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.report-form__screenshot img {
  max-width: 100%;
  max-height: 10rem;
  border-radius: 0.375rem;
  border: 1px solid var(--border-default-grey);
  margin-bottom: 0.5rem;
}

.report-form__screenshot-label {
  margin: 0 0 0.375rem;
  font-weight: 600;
}

.report-form__screenshot-hint {
  color: var(--text-mention-grey);
  margin: 0 0 0.5rem;
}

.report-form__screenshot-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.report-form__success {
  color: var(--text-default-success);
}

.report-form__history {
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border-default-grey);
}

.report-form__history h3 {
  margin: 0 0 0.75rem;
}

.report-form__history-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.report-form__history-item {
  padding: 0.75rem;
  background: var(--background-alt-grey);
  border-radius: 0.5rem;
}

.report-form__history-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.report-form__history-title {
  font-weight: 600;
}

.report-form__history-meta {
  margin: 0.25rem 0 0;
  color: var(--text-mention-grey);
}

.report-form__history-response {
  margin: 0.5rem 0 0;
}
</style>
