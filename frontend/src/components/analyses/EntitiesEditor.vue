<script setup lang="ts">
import { ref, watch } from "vue";

import LlmAssistButton from "@/components/analyses/LlmAssistButton.vue";
import VersionHistory from "@/components/analyses/VersionHistory.vue";
import { suggestEntities, suggestEntityDefinition } from "@/composables/useLlmAssist";
import type { EntityDefinition, EntityType, Version } from "@/types/analyse";

const props = defineProps<{ entities: EntityDefinition[]; versions: Version<EntityDefinition[]>[] }>();
const emit = defineEmits<{ save: [EntityDefinition[]]; restore: [string] }>();

const entityTypes: EntityType[] = ["texte", "date", "nombre", "booléen", "identifiant"];

const draftEntities = ref<EntityDefinition[]>(cloneEntities(props.entities));
const isDirty = ref(false);
const editingId = ref<string | null>(null);
const isSuggestingList = ref(false);
const suggestingDefinitionId = ref<string | null>(null);

function cloneEntities(entities: EntityDefinition[]): EntityDefinition[] {
  return entities.map((entity) => ({ ...entity }));
}

watch(
  () => props.entities,
  (entities) => {
    draftEntities.value = cloneEntities(entities);
    isDirty.value = false;
    editingId.value = null;
  },
);

watch(
  draftEntities,
  (entities) => {
    isDirty.value = JSON.stringify(entities) !== JSON.stringify(props.entities);
  },
  { deep: true },
);

function addEntity() {
  draftEntities.value.push({ id: `entity-${Date.now()}`, name: "", definition: "", type: "texte" });
  editingId.value = draftEntities.value[draftEntities.value.length - 1].id;
}

function removeEntity(id: string) {
  draftEntities.value = draftEntities.value.filter((entity) => entity.id !== id);
  if (editingId.value === id) editingId.value = null;
}

async function applySuggestions(model: string | null) {
  isSuggestingList.value = true;
  try {
    const suggestions = await suggestEntities(model);
    draftEntities.value = suggestions.map((entity, index) => ({ ...entity, id: `entity-suggestion-${index}` }));
    editingId.value = null;
  } catch (error) {
    alert(error instanceof Error ? error.message : "Échec de l'aide LLM.");
  } finally {
    isSuggestingList.value = false;
  }
}

async function applyDefinitionSuggestion(entity: EntityDefinition, model: string | null) {
  suggestingDefinitionId.value = entity.id;
  try {
    const suggestion = await suggestEntityDefinition(entity.name, model);
    entity.definition = suggestion.definition;
    entity.type = suggestion.type;
  } catch (error) {
    alert(error instanceof Error ? error.message : "Échec de l'aide LLM.");
  } finally {
    suggestingDefinitionId.value = null;
  }
}

function save() {
  emit("save", draftEntities.value);
}

function formatVersionContent(entities: EntityDefinition[]) {
  return entities.length > 0
    ? entities.map((entity) => `${entity.name || "(sans nom)"} (${entity.type})`).join(", ")
    : "(aucune entité)";
}
</script>

<template>
  <div class="entities-editor">
    <h4 class="fr-h6 entities-editor__title">Entités à extraire</h4>

    <p v-if="draftEntities.length === 0" class="fr-text--sm">Aucune entité définie.</p>

    <ul v-else class="entities-editor__list">
      <li
        v-for="item in draftEntities"
        :key="item.id"
        class="entities-editor__item"
        :class="{ 'entities-editor__item--editing': editingId === item.id }"
      >
        <div v-if="editingId !== item.id" class="entities-editor__summary">
          <div class="entities-editor__text">
            <p class="entities-editor__name">
              <span>{{ item.name || "(sans nom)" }}</span>
              <span class="fr-badge fr-badge--sm fr-badge--blue-ecume">{{ item.type }}</span>
            </p>
            <p v-if="item.definition" class="fr-text--sm entities-editor__definition">{{ item.definition }}</p>
          </div>
          <div class="entities-editor__buttons">
            <DsfrButton label="Modifier" icon-only tertiary no-outline icon="ri-edit-line" size="sm" @click="editingId = item.id" />
            <DsfrButton
              label="Supprimer l'entité"
              icon-only
              tertiary
              no-outline
              icon="ri-delete-bin-line"
              size="sm"
              @click="removeEntity(item.id)"
            />
          </div>
        </div>

        <div v-else class="entities-editor__form">
          <div class="entities-editor__fields">
            <DsfrInput v-model="item.name" label="Entité" label-visible />
            <DsfrSelect v-model="item.type" label="Type" :options="entityTypes" />
          </div>
          <DsfrInput v-model="item.definition" label="Définition" label-visible is-textarea rows="3" />
          <div class="entities-editor__form-actions">
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

    <div class="entities-editor__actions">
      <DsfrButton label="Ajouter une entité" tertiary icon="ri-add-line" size="sm" @click="addEntity" />
      <LlmAssistButton :loading="isSuggestingList" @click="applySuggestions" />
      <DsfrButton label="Enregistrer" :disabled="!isDirty" size="sm" @click="save" />
    </div>

    <VersionHistory :versions="versions" :format-content="formatVersionContent" @restore="emit('restore', $event)" />
  </div>
</template>

<style scoped>
.entities-editor {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.entities-editor__title {
  margin: 0;
}

.entities-editor__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.entities-editor__item {
  border: 1px solid var(--border-default-grey);
  border-left: 3px solid #9d6cff;
  border-radius: 0.5rem;
  background: var(--background-default-grey);
}

.entities-editor__item--editing {
  border-color: #9d6cff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.entities-editor__summary {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
}

.entities-editor__text {
  flex: 1;
  min-width: 0;
}

.entities-editor__name {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  font-weight: 600;
}

.entities-editor__definition {
  margin: 0.25rem 0 0;
  color: var(--text-mention-grey);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.entities-editor__buttons {
  display: flex;
  flex-shrink: 0;
}

.entities-editor__form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
}

.entities-editor__fields {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.entities-editor__fields > :first-child {
  flex: 1;
  min-width: 12rem;
}

.entities-editor__form-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.entities-editor__actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}
</style>
