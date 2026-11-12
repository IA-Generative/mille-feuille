<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import DocumentTemplateEditor from "@/components/admin/documentTemplates/DocumentTemplateEditor.vue";
import { errorMessage, useDocumentTemplates } from "@/composables/useDocumentTemplates";
import { useAnalyses } from "@/composables/useAnalyses";
import type { DocumentTemplate } from "@/types/documentTemplate";

// Onglet « Documents » d'une analyse (backend issues #138 et #139) : les modèles de document **de cette analyse**.
// Un modèle appartient à l'analyse où on le crée ; ses champs puisent dans ce qu'elle définit (entités, labels,
// agents), et seuls les dossiers de cette analyse peuvent s'en servir.
const route = useRoute();
const analyseId = computed(() => String(route.params.id));
const { getById, fetchAnalyse } = useAnalyses();
const analyse = computed(() => getById(analyseId.value));

const api = useDocumentTemplates();
const templates = ref<DocumentTemplate[]>([]);
const includeArchived = ref(false);
const loading = ref(false);
const error = ref("");
const editing = ref<DocumentTemplate | null>(null);
const creating = ref(false);

/** Écrit un placeholder comme dans le fichier : {{ nom }} (hors gabarit, où « }} » fermerait l'interpolation). */
const braces = (name: string) => `{{ ${name} }}`;

async function reload() {
  loading.value = true;
  error.value = "";
  try {
    templates.value = await api.fetchTemplates(analyseId.value, includeArchived.value);
  } catch (e) {
    error.value = errorMessage(e, "Impossible de charger les modèles de document.");
  } finally {
    loading.value = false;
  }
}

function closeEditor() {
  editing.value = null;
  creating.value = false;
  void reload();
}

onMounted(() => {
  if (!analyse.value) void fetchAnalyse(analyseId.value);
  void reload();
});
// Changer d'analyse (même page, autre identifiant) recharge ses modèles.
watch(analyseId, () => {
  editing.value = null;
  creating.value = false;
  void reload();
});

const dateFormatter = new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" });
</script>

<template>
  <section class="analyse-documents-tab">
    <DocumentTemplateEditor
      v-if="creating || editing"
      :key="editing?.id ?? 'new'"
      :template="editing"
      :analyse-id="analyseId"
      :analyse-name="analyse?.name ?? ''"
      @cancel="closeEditor"
      @changed="reload"
      @saved="reload"
    />

    <template v-else>
      <div class="analyse-documents-tab__header">
        <p class="fr-text--sm">
          Modèles de document de fin d'instruction de <strong>cette analyse</strong> : un fichier ODT avec des champs
          <code>{{ braces("nom") }}</code> et la définition de ces champs, qui puisent dans les entités, labels et agents de
          l'analyse. Ils ne servent qu'aux dossiers de cette analyse.
        </p>
        <DsfrButton label="Nouveau modèle" icon="ri-add-line" @click="creating = true" />
      </div>

      <DsfrAlert v-if="error" alert type="error" :description="error" small />
      <DsfrCheckbox
        v-model="includeArchived"
        name="include-archived"
        label="Afficher les modèles archivés"
        @update:model-value="reload"
      />

      <p v-if="loading" class="fr-text--sm">Chargement…</p>
      <p v-else-if="templates.length === 0" class="fr-text--sm">Cette analyse n'a pas encore de modèle de document.</p>
      <ul v-else class="analyse-documents-tab__list">
        <li v-for="t in templates" :key="t.id" class="analyse-documents-tab__item">
          <div>
            <div class="analyse-documents-tab__item-title">
              <strong>{{ t.name }}</strong>
              <DsfrBadge :label="`Version ${t.versionNumber}`" small />
              <DsfrBadge v-if="t.archived" label="Archivé" type="warning" small />
            </div>
            <p v-if="t.description" class="fr-text--sm analyse-documents-tab__item-desc">{{ t.description }}</p>
            <p class="fr-text--sm analyse-documents-tab__item-meta">
              {{ t.fields.length }} champ(s) · {{ t.fileName }} · modifié le {{ dateFormatter.format(new Date(t.updatedAt)) }}
            </p>
          </div>
          <DsfrButton label="Modifier" secondary size="sm" @click="editing = t" />
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.analyse-documents-tab {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.analyse-documents-tab__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.analyse-documents-tab__header code {
  white-space: nowrap;
}

.analyse-documents-tab__header p {
  margin: 0;
  flex: 1 1 24rem;
}

.analyse-documents-tab__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.analyse-documents-tab__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.375rem;
}

.analyse-documents-tab__item-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.analyse-documents-tab__item-desc,
.analyse-documents-tab__item-meta {
  margin: 0.25rem 0 0;
}

.analyse-documents-tab__item-meta {
  color: var(--text-mention-grey);
}
</style>
