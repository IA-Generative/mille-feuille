<script setup lang="ts">
import { ref, watch } from "vue";

import LlmAssistButton from "@/components/analyses/LlmAssistButton.vue";
import VersionHistory from "@/components/analyses/VersionHistory.vue";
import { suggestLabelDefinition, suggestLabels } from "@/composables/useLlmAssist";
import type { LabelDefinition, Version } from "@/types/analyse";

const props = defineProps<{ labels: LabelDefinition[]; versions: Version<LabelDefinition[]>[] }>();
const emit = defineEmits<{ save: [LabelDefinition[]]; restore: [string] }>();

const draftLabels = ref<LabelDefinition[]>(cloneLabels(props.labels));
const isDirty = ref(false);
const editingId = ref<string | null>(null);
const isSuggestingList = ref(false);
const suggestingDefinitionId = ref<string | null>(null);

function cloneLabels(labels: LabelDefinition[]): LabelDefinition[] {
  return labels.map((label) => ({ ...label }));
}

watch(
  () => props.labels,
  (labels) => {
    draftLabels.value = cloneLabels(labels);
    isDirty.value = false;
    editingId.value = null;
  },
);

watch(
  draftLabels,
  (labels) => {
    isDirty.value = JSON.stringify(labels) !== JSON.stringify(props.labels);
  },
  { deep: true },
);

function addLabel() {
  draftLabels.value.push({ id: `label-${Date.now()}`, name: "", definition: "" });
  editingId.value = draftLabels.value[draftLabels.value.length - 1].id;
}

function removeLabel(id: string) {
  draftLabels.value = draftLabels.value.filter((label) => label.id !== id);
  if (editingId.value === id) editingId.value = null;
}

async function applySuggestions(model: string | null) {
  isSuggestingList.value = true;
  try {
    const suggestions = await suggestLabels(model);
    draftLabels.value = suggestions.map((label, index) => ({ ...label, id: `label-suggestion-${index}` }));
    editingId.value = null;
  } catch (error) {
    alert(error instanceof Error ? error.message : "Échec de l'aide LLM.");
  } finally {
    isSuggestingList.value = false;
  }
}

async function applyDefinitionSuggestion(label: LabelDefinition, model: string | null) {
  suggestingDefinitionId.value = label.id;
  try {
    label.definition = await suggestLabelDefinition(label.name, model);
  } catch (error) {
    alert(error instanceof Error ? error.message : "Échec de l'aide LLM.");
  } finally {
    suggestingDefinitionId.value = null;
  }
}

function save() {
  emit("save", draftLabels.value);
}

function formatVersionContent(labels: LabelDefinition[]) {
  return labels.length > 0 ? labels.map((label) => label.name || "(sans nom)").join(", ") : "(aucun label)";
}
</script>

<template>
  <div class="labels-editor">
    <h4 class="fr-h6 labels-editor__title">Labels de classification</h4>

    <p v-if="draftLabels.length === 0" class="fr-text--sm">Aucun label défini.</p>

    <ul v-else class="labels-editor__list">
      <li
        v-for="item in draftLabels"
        :key="item.id"
        class="labels-editor__item"
        :class="{ 'labels-editor__item--editing': editingId === item.id }"
      >
        <div v-if="editingId !== item.id" class="labels-editor__summary">
          <div class="labels-editor__text">
            <p class="labels-editor__name">
              <span>{{ item.name || "(sans nom)" }}</span>
              
            </p>
            <p v-if="item.definition" class="fr-text--sm labels-editor__definition">{{ item.definition }}</p>
          </div>
          <div class="labels-editor__buttons">
            <DsfrButton label="Modifier" icon-only tertiary no-outline icon="ri-edit-line" size="sm" @click="editingId = item.id" />
            <DsfrButton
              label="Supprimer le label"
              icon-only
              tertiary
              no-outline
              icon="ri-delete-bin-line"
              size="sm"
              @click="removeLabel(item.id)"
            />
          </div>
        </div>

        <div v-else class="labels-editor__form">
          <div class="labels-editor__fields">
            <DsfrInput v-model="item.name" label="Label" label-visible />
            
          </div>
          <DsfrInput v-model="item.definition" label="Définition" label-visible is-textarea rows="3" />
          <div class="labels-editor__form-actions">
            <LlmAssistButton
              compact
              label="Suggérer une définition"
              :loading="suggestingDefinitionId === item.id"
              @click="(model) => applyDefinitionSuggestion(item, model)"
            />
            <DsfrButton label="Terminer" secondary size="sm" class="fr-ml-auto" @click="editingId = null" />
          </div>
        </div>
      </li>
    </ul>

    <div class="labels-editor__actions">
      <DsfrButton label="Ajouter un label" tertiary icon="ri-add-line" size="sm" @click="addLabel" />
      <LlmAssistButton :loading="isSuggestingList" @click="applySuggestions" />
      <DsfrButton label="Enregistrer" :disabled="!isDirty" size="sm" @click="save" />
    </div>

    <VersionHistory :versions="versions" :format-content="formatVersionContent" @restore="emit('restore', $event)" />
  </div>
</template>

<style scoped>
.labels-editor {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.labels-editor__title {
  margin: 0;
}

.labels-editor__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.labels-editor__item {
  border: 1px solid var(--border-default-grey);
  border-left: 3px solid #6a5cff;
  border-radius: 0.5rem;
  background: var(--background-default-grey);
}

.labels-editor__item--editing {
  border-color: #6a5cff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.labels-editor__summary {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
}

.labels-editor__text {
  flex: 1;
  min-width: 0;
}

.labels-editor__name {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  font-weight: 600;
}

.labels-editor__definition {
  margin: 0.25rem 0 0;
  color: var(--text-mention-grey);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.labels-editor__buttons {
  display: flex;
  flex-shrink: 0;
}

.labels-editor__form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
}

.labels-editor__fields {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.labels-editor__fields > :first-child {
  flex: 1;
  min-width: 12rem;
}

.labels-editor__form-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.labels-editor__actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}
</style>
