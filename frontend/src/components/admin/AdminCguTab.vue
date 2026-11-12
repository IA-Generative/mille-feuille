<script setup lang="ts">
import { ref, watch } from "vue";

import { useCgu } from "@/composables/useCgu";
import { renderMarkdown } from "@/utils/markdown";

const { versions, fetchVersions, createVersion, updateVersion, activateVersion } = useCgu();

const cguDraft = ref("");
const cguPreviewHtml = ref("");
const cguShowPreview = ref(false);
const cguSaving = ref(false);
const cguError = ref("");
const cguSuccess = ref("");

async function reload() {
  try {
    await fetchVersions();
  } catch {
    cguError.value = "Impossible de charger les versions des CGU.";
  }
}

watch(cguDraft, (value) => {
  if (cguShowPreview.value) cguPreviewHtml.value = renderMarkdown(value);
});

function togglePreview() {
  cguShowPreview.value = !cguShowPreview.value;
  if (cguShowPreview.value) cguPreviewHtml.value = renderMarkdown(cguDraft.value);
}

async function handleCreateVersion() {
  const content = cguDraft.value.trim();
  if (!content) return;
  cguSaving.value = true;
  cguError.value = "";
  cguSuccess.value = "";
  try {
    await createVersion(content);
    cguDraft.value = "";
    cguPreviewHtml.value = "";
    cguSuccess.value = "Nouvelle version créée. Pensez à l'activer pour la publier.";
    await reload();
  } catch {
    cguError.value = "Erreur lors de la création de la version.";
  } finally {
    cguSaving.value = false;
  }
}

async function handleActivate(id: string) {
  if (!confirm("Activer cette version ? Tous les utilisateurs devront l'accepter à nouveau.")) return;
  cguError.value = "";
  cguSuccess.value = "";
  try {
    await activateVersion(id);
    cguSuccess.value = "Version activée. Les utilisateurs devront l'accepter à leur prochaine connexion.";
    await reload();
  } catch {
    cguError.value = "Erreur lors de l'activation de la version.";
  }
}

async function handleUpdate(id: string) {
  const content = cguDraft.value.trim();
  if (!content) return;
  cguSaving.value = true;
  cguError.value = "";
  cguSuccess.value = "";
  try {
    await updateVersion(id, content);
    cguDraft.value = "";
    cguPreviewHtml.value = "";
    cguSuccess.value = "Version mise à jour.";
    await reload();
  } catch {
    cguError.value = "Erreur lors de la mise à jour. Une version active ne peut pas être modifiée.";
  } finally {
    cguSaving.value = false;
  }
}

function loadVersionIntoEditor(version: (typeof versions.value)[number]) {
  cguDraft.value = version.content;
  if (cguShowPreview.value) cguPreviewHtml.value = renderMarkdown(version.content);
}

const dateFormatter = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" });
function formatDate(iso: string) {
  return dateFormatter.format(new Date(iso));
}

defineExpose({ reload });
</script>

<template>
  <section class="cgu-admin">
    <h2 class="fr-h4">Conditions d'utilisation (CGU)</h2>

    <DsfrAlert v-if="cguError" alert type="error" small :description="cguError" class="fr-mb-2w" />
    <div v-if="cguSuccess" class="fr-alert fr-alert--success fr-mb-2w">{{ cguSuccess }}</div>

    <div class="cgu-admin__editor">
      <div class="cgu-admin__editor-toolbar">
        <DsfrButton label="Aperçu" tertiary size="sm" @click="togglePreview" />
      </div>
      <div v-if="cguShowPreview" class="cgu-admin__preview markdown" v-html="cguPreviewHtml" />
      <DsfrInput
        v-else
        v-model="cguDraft"
        label="Nouveau contenu (Markdown)"
        label-visible
        is-textarea
        :rows="12"
      />
      <div class="cgu-admin__editor-actions">
        <DsfrButton
          label="Créer une version"
          :disabled="cguSaving || !cguDraft.trim()"
          size="sm"
          @click="handleCreateVersion"
        />
      </div>
    </div>

    <p v-if="versions.length === 0" class="fr-text--sm">Aucune version des CGU pour le moment.</p>
    <ul v-else class="cgu-admin__list">
      <li v-for="v in versions" :key="v.id" class="cgu-admin__item">
        <div class="cgu-admin__item-header">
          <span class="cgu-admin__item-version">Version {{ v.version }}</span>
          <DsfrBadge v-if="v.isActive" label="Active" type="success" />
          <span v-else class="cgu-admin__item-status">Inactive</span>
        </div>
        <p class="fr-text--sm cgu-admin__item-meta">
          Créée le {{ formatDate(v.createdAt) }}<span v-if="v.publishedAt"> · Publiée le {{ formatDate(v.publishedAt) }}</span>
        </p>
        <div class="cgu-admin__item-actions">
          <DsfrButton label="Éditer" tertiary size="sm" @click="loadVersionIntoEditor(v)" />
          <DsfrButton
            v-if="!v.isActive"
            label="Activer"
            size="sm"
            @click="handleActivate(v.id)"
          />
          <DsfrButton
            v-if="!v.isActive"
            label="Mettre à jour"
            tertiary
            size="sm"
            :disabled="cguSaving || !cguDraft.trim()"
            @click="handleUpdate(v.id)"
          />
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.cgu-admin {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.cgu-admin__editor {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.cgu-admin__editor-toolbar {
  display: flex;
  gap: 0.5rem;
}

.cgu-admin__preview {
  min-height: 12rem;
  max-height: 24rem;
  overflow-y: auto;
  padding: 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.375rem;
  background: var(--background-alt-grey);
}

.cgu-admin__editor-actions {
  display: flex;
  gap: 0.5rem;
}

.cgu-admin__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.cgu-admin__item {
  padding: 1rem;
  background: var(--background-default-grey);
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.cgu-admin__item-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.cgu-admin__item-version {
  font-weight: 600;
}

.cgu-admin__item-status {
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.cgu-admin__item-meta {
  margin: 0;
  color: var(--text-mention-grey);
}

.cgu-admin__item-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
</style>
