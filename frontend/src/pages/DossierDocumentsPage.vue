<script setup lang="ts">
/**
 * Documents d'un dossier (backend issues #140, #143) : créer un brouillon à partir d'un modèle de l'analyse du
 * dossier, reprendre un brouillon, télécharger les documents générés (ODT et PDF). Interne : jamais montré aux usagers.
 */
import BackLink from "@/components/BackLink.vue";
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { draftErrorMessage, useDocumentDrafts } from "@/composables/useDocumentDrafts";
import { useDossiers } from "@/composables/useDossiers";
import type { DossierTemplate, DraftSummary, GeneratedDocument } from "@/types/documentDraft";

const route = useRoute();
const router = useRouter();
const dossierId = String(route.params.id);
const api = useDocumentDrafts(dossierId);
const { list: dossiers, fetchDossier } = useDossiers();
const dossier = computed(() => dossiers.value.find((d) => d.id === dossierId));

const templates = ref<DossierTemplate[]>([]);
const drafts = ref<DraftSummary[]>([]);
const documents = ref<GeneratedDocument[]>([]);
const selectedTemplate = ref("");
const loading = ref(true);
const creating = ref(false);
const error = ref("");

const templateOptions = computed(() => [
  { value: "", text: templates.value.length ? "Choisir un modèle…" : "Aucun modèle pour l'analyse de ce dossier" },
  ...templates.value.map((t) => ({ value: t.id, text: `${t.name} (version ${t.versionNumber})` })),
]);
const selectedDescription = computed(() => templates.value.find((t) => t.id === selectedTemplate.value)?.description ?? "");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    [templates.value, drafts.value, documents.value] = await Promise.all([api.fetchTemplates(), api.fetchDrafts(), api.fetchDocuments()]);
  } catch (e) {
    error.value = draftErrorMessage(e, "Impossible de charger les documents du dossier.");
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void fetchDossier(dossierId).catch(() => undefined);
  void load();
});

async function createDraft() {
  if (!selectedTemplate.value) return;
  creating.value = true;
  error.value = "";
  try {
    const draft = await api.createDraft(selectedTemplate.value);
    await router.push(`/dossiers/${dossierId}/documents/${draft.id}`);
  } catch (e) {
    error.value = draftErrorMessage(e, "Impossible de créer le brouillon.");
  } finally {
    creating.value = false;
  }
}

const dateFormatter = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" });
const formatDate = (iso: string) => dateFormatter.format(new Date(iso));
const formatSize = (bytes: number | null) => (bytes === null ? "" : bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} Ko` : `${(bytes / (1024 * 1024)).toFixed(1)} Mo`);
const draftOf = (id: string) => drafts.value.find((d) => d.id === id);
</script>

<template>
  <div class="documents">
    <BackLink :to="`/dossiers/${dossierId}`">
      Retour au dossier
    </BackLink>
    <h1 class="fr-h2">Documents{{ dossier ? ` — ${dossier.name}` : "" }}</h1>
    <p class="fr-text--sm">
      Documents de fin d'instruction du dossier, produits à partir d'un modèle de son analyse. Ils restent internes : rien n'est
      envoyé à l'usager.
    </p>

    <DsfrAlert v-if="error" type="error" :description="error" small />
    <p v-if="loading" class="fr-text--sm">Chargement…</p>

    <template v-else>
      <section class="documents__block">
        <h2 class="fr-h5">Nouveau document</h2>
        <div class="documents__new">
          <DsfrSelect v-model="selectedTemplate" label="Modèle de document" label-visible :options="templateOptions" />
          <DsfrButton label="Créer le brouillon" icon="ri-add-line" :disabled="!selectedTemplate || creating" @click="createDraft" />
        </div>
        <p v-if="selectedDescription" class="fr-text--sm">{{ selectedDescription }}</p>
        <p v-if="!templates.length" class="fr-text--sm">
          Les modèles se gèrent dans l'onglet « Documents » de l'analyse du dossier (réservé aux administrateurs).
        </p>
      </section>

      <section class="documents__block">
        <h2 class="fr-h5">Brouillons ({{ drafts.length }})</h2>
        <p v-if="!drafts.length" class="fr-text--sm">Aucun brouillon pour ce dossier.</p>
        <ul v-else class="documents__list">
          <li v-for="d in drafts" :key="d.id" class="documents__item">
            <div>
              <strong>{{ d.templateName }}</strong>
              <DsfrBadge :label="`Modèle v${d.templateVersionNumber}`" small class="documents__badge" />
              <DsfrBadge v-if="d.status !== 'brouillon'" :label="d.status" type="warning" small class="documents__badge" />
              <p class="fr-text--sm documents__meta">Créé le {{ formatDate(d.createdAt) }}</p>
            </div>
            <RouterLink :to="`/dossiers/${dossierId}/documents/${d.id}`" class="fr-btn fr-btn--secondary fr-btn--sm">
              {{ d.status === "brouillon" ? "Reprendre" : "Ouvrir" }}
            </RouterLink>
          </li>
        </ul>
      </section>

      <section class="documents__block">
        <h2 class="fr-h5">Documents générés ({{ documents.length }})</h2>
        <p v-if="!documents.length" class="fr-text--sm">Aucun document généré pour l'instant.</p>
        <ul v-else class="documents__list">
          <li v-for="doc in documents" :key="doc.id" class="documents__item">
            <div>
              <strong>{{ doc.templateName }}</strong>
              <DsfrBadge :label="`Version ${doc.versionNumber}`" small class="documents__badge" />
              <DsfrBadge :label="`Analyse : révision ${doc.revisionNumber}`" type="info" small class="documents__badge" />
              <DsfrBadge v-if="doc.incompleteFields.length" label="Incomplet" type="warning" small class="documents__badge" />
              <DsfrBadge :label="doc.visibility" type="new" small class="documents__badge" />
              <p class="fr-text--sm documents__meta">
                Généré le {{ formatDate(doc.createdAt) }} · modèle v{{ doc.templateVersionNumber }}
                <template v-if="draftOf(doc.draftId)">
                  · <RouterLink :to="`/dossiers/${dossierId}/documents/${doc.draftId}`" class="fr-link fr-link--sm">brouillon</RouterLink>
                </template>
              </p>
            </div>
            <div class="documents__downloads">
              <a :href="api.documentUrl(doc.id, 'odt')" class="fr-btn fr-btn--secondary fr-btn--sm" download>
                ODT {{ formatSize(doc.odtSize) }}
              </a>
              <a v-if="doc.hasPdf" :href="api.documentUrl(doc.id, 'pdf')" class="fr-btn fr-btn--tertiary fr-btn--sm" download>
                PDF {{ formatSize(doc.pdfSize) }}
              </a>
            </div>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.documents {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.documents__block {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.375rem;
}

.documents__block h2 {
  margin: 0;
}

.documents__new {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.documents__new > :first-child {
  flex: 1 1 18rem;
}

.documents__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.documents__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0.75rem 1rem;
  background: var(--background-alt-grey);
  border-radius: 0.375rem;
}

.documents__badge {
  margin-left: 0.5rem;
}

.documents__meta {
  margin: 0.25rem 0 0;
  color: var(--text-mention-grey);
}

.documents__downloads {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
</style>
