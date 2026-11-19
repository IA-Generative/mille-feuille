<script setup lang="ts">
import { nextTick, ref, watch } from "vue";

import CollapsibleText from "@/components/analyses/CollapsibleText.vue";
import EntityLocation from "@/components/analyses/EntityLocation.vue";
import LlmAssistButton from "@/components/analyses/LlmAssistButton.vue";
import PaginationBar from "@/components/PaginationBar.vue";
import VersionHistory from "@/components/analyses/VersionHistory.vue";
import EditorIntro from "@/components/analyses/EditorIntro.vue";
import { useListView } from "@/composables/useListView";
import { suggestEntities, suggestEntityDefinition } from "@/composables/useLlmAssist";
import type { EntityDefinition, EntityNature, EntityType, LabelDefinition, Version } from "@/types/analyse";

const props = withDefaults(
  defineProps<{
    entities: EntityDefinition[];
    versions: Version<EntityDefinition[]>[];
    labels?: LabelDefinition[];
    /** Lecture seule : seuls le créateur de l'analyse et les administrateurs modifient les entités. */
    readonly?: boolean;
  }>(),
  { labels: () => [] },
);
const emit = defineEmits<{ save: [EntityDefinition[]]; restore: [string] }>();

const entityTypes: EntityType[] = ["texte", "date", "nombre", "booléen", "identifiant"];
const entityNatures: { value: EntityNature; text: string }[] = [
  { value: "entité", text: "Entité (GLiNER)" },
  { value: "sémantique", text: "Sémantique (LLM)" },
];

const draftEntities = ref<EntityDefinition[]>(cloneEntities(props.entities));
const isDirty = ref(false);
const editingId = ref<string | null>(null);
const { query, pageIndex, pageSize, hasSearch, filtered, paged, reveal } = useListView(draftEntities, (item) => `${item.name} ${item.definition}`);
const isSuggestingList = ref(false);
const suggestingDefinitionId = ref<string | null>(null);
const statusMessage = ref("");

// On vide puis on remplit au tick suivant : un message identique au précédent est ainsi annoncé de nouveau.
function announce(message: string) {
  statusMessage.value = "";
  nextTick(() => (statusMessage.value = message));
}

function labelNamesOf(entity: EntityDefinition): string[] {
  return entity.labelIds.map((id) => props.labels.find((label) => label.id === id)?.name).filter((name): name is string => !!name);
}

function cloneEntities(entities: EntityDefinition[]): EntityDefinition[] {
  return entities.map((entity) => ({ ...entity, labelIds: [...entity.labelIds], zones: entity.zones.map((zone) => ({ ...zone })) }));
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
  draftEntities.value.push({
    id: `entity-${Date.now()}`,
    name: "",
    definition: "",
    type: "texte",
    nature: "entité",
    labelIds: [],
    zones: [],
  });
  editingId.value = draftEntities.value[draftEntities.value.length - 1].id;
  reveal(editingId.value);
}

function removeEntity(id: string) {
  draftEntities.value = draftEntities.value.filter((entity) => entity.id !== id);
  if (editingId.value === id) editingId.value = null;
}

async function applySuggestions(model: string | null) {
  isSuggestingList.value = true;
  announce("Génération en cours…");
  try {
    const suggestions = await suggestEntities(model);
    draftEntities.value = suggestions.map((entity, index) => ({
      ...entity,
      id: `entity-suggestion-${index}`,
      labelIds: [],
      zones: [],
    }));
    editingId.value = null;
    announce("Liste proposée : vérifiez-la, puis enregistrez.");
  } catch (error) {
    statusMessage.value = "";
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
    if (suggestion.nature) entity.nature = suggestion.nature;
  } catch (error) {
    alert(error instanceof Error ? error.message : "Échec de l'aide LLM.");
  } finally {
    suggestingDefinitionId.value = null;
  }
}

function save() {
  emit("save", draftEntities.value);
  announce("Entités enregistrées.");
}

function formatVersionContent(entities: EntityDefinition[]) {
  return entities.length > 0
    ? entities.map((entity) => `${entity.name || "(sans nom)"} (${entity.nature ?? "entité"}, ${entity.type})`).join(", ")
    : "(aucune entité)";
}
</script>

<template>
  <div class="entities-editor">
    <h4 class="fr-h6 entities-editor__title">Entités à extraire</h4>
    <p class="fr-sr-only" role="status">{{ statusMessage }}</p>
    <EditorIntro v-if="$slots.description"><slot name="description" /></EditorIntro>

    <DsfrInput
      v-if="hasSearch"
      v-model="query"
      label="Rechercher"
      label-visible
      hint="Par nom ou définition"
      class="entities-editor__search"
    />
        <p v-if="draftEntities.length === 0" class="fr-text--sm">Aucune entité définie.</p>
    <p v-else-if="filtered.length === 0" class="fr-text--sm">Aucun résultat pour « {{ query }} ».</p>

    <ul v-else class="entities-editor__list">
      <li
        v-for="item in paged"
        :key="item.id"
        class="entities-editor__item"
        :class="{ 'entities-editor__item--editing': editingId === item.id }"
      >
        <div v-if="editingId !== item.id" class="entities-editor__summary">
          <div class="entities-editor__text">
            <p class="entities-editor__name">
              <span>{{ item.name || "(sans nom)" }}</span>
              <span class="fr-badge fr-badge--sm fr-badge--blue-ecume">{{ item.type }}</span>
              <span class="fr-badge fr-badge--sm fr-badge--no-icon" :class="item.nature === 'sémantique' ? 'fr-badge--purple-glycine' : 'fr-badge--green-menthe'">
                {{ item.nature }}
              </span>
              <span v-for="name in labelNamesOf(item)" :key="name" class="fr-badge fr-badge--sm fr-badge--info fr-badge--no-icon">{{ name }}</span>
              <span v-if="item.zones.length > 0" class="fr-badge fr-badge--sm fr-badge--no-icon">
                {{ item.zones.length }} zone{{ item.zones.length > 1 ? "s" : "" }}
              </span>
            </p>
            <CollapsibleText v-if="item.definition" :text="item.definition" />
          </div>
          <div v-if="!readonly" class="entities-editor__buttons">
            <DsfrButton :label="`Modifier l'entité « ${item.name || 'sans nom'} »`" icon-only tertiary no-outline icon="ri-edit-line" size="sm" @click="editingId = item.id" />
            <DsfrButton
              :label="`Supprimer l'entité « ${item.name || 'sans nom'} »`"
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
            <DsfrSelect v-model="item.nature" label="Nature" :options="entityNatures" />
          </div>
          <DsfrInput v-model="item.definition" label="Définition" label-visible is-textarea rows="3" />
          <EntityLocation v-model:label-ids="item.labelIds" v-model:zones="item.zones" :labels="labels" />
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

    <PaginationBar v-model:page-index="pageIndex" v-model:page-size="pageSize" :total="filtered.length" label="Par page" />

    <div v-if="!readonly" class="entities-editor__actions">
      <DsfrButton label="Ajouter une entité" tertiary icon="ri-add-line" size="sm" @click="addEntity" />
      <LlmAssistButton label="Suggérer des entités" :loading="isSuggestingList" @click="applySuggestions" />
      <DsfrButton label="Enregistrer" :disabled="!isDirty" size="sm" @click="save" />
    </div>

        <p v-if="readonly" class="fr-hint-text fr-mb-0">
      Seuls le créateur de l'analyse et les administrateurs peuvent modifier les entités.
    </p>
    <p v-else-if="!isDirty" class="fr-hint-text fr-mb-0">Aucune modification à enregistrer.</p>

    <VersionHistory :versions="versions" :format-content="formatVersionContent" :readonly="readonly" @restore="emit('restore', $event)" />
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
  box-shadow: var(--raised-shadow);
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
