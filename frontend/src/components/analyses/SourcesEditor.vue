<script setup lang="ts">
/**
 * Catalogue des sources de fichiers d'une analyse : nom + description, ajout, modification, suppression. Pas de
 * versionnage (décision explicite). Supprimer une source utilisée est permis : ses documents restent, sans source.
 */
import { ref } from "vue";

import type { DocumentSource } from "@/types/documentSource";

defineProps<{ sources: DocumentSource[]; busy?: boolean }>();
const emit = defineEmits<{
  create: [input: { name: string; description: string }];
  update: [id: string, input: { name: string; description: string }];
  remove: [id: string];
}>();

const newName = ref("");
const newDescription = ref("");
const editingId = ref<string | undefined>(undefined);
const editName = ref("");
const editDescription = ref("");

function add() {
  if (!newName.value.trim()) return;
  emit("create", { name: newName.value.trim(), description: newDescription.value.trim() });
  newName.value = "";
  newDescription.value = "";
}

function startEdit(source: DocumentSource) {
  editingId.value = source.id;
  editName.value = source.name;
  editDescription.value = source.description;
}

function saveEdit() {
  if (!editingId.value || !editName.value.trim()) return;
  emit("update", editingId.value, { name: editName.value.trim(), description: editDescription.value.trim() });
  editingId.value = undefined;
}

function confirmRemove(source: DocumentSource) {
  if (confirm(`Supprimer la source « ${source.name} » ? Les documents qui l'utilisent restent, sans source.`)) {
    emit("remove", source.id);
  }
}
</script>

<template>
  <div class="sources-editor">
    <p v-if="sources.length === 0" class="fr-text--sm sources-editor__empty">
      Aucune source pour l'instant. Elles se créent ici, ou au moment du dépôt d'un fichier.
    </p>

    <ul v-else class="sources-editor__list">
      <li v-for="source in sources" :key="source.id" class="sources-editor__item">
        <template v-if="editingId === source.id">
          <div class="sources-editor__form">
            <DsfrInput v-model="editName" label="Nom" label-visible />
            <DsfrInput v-model="editDescription" label="Description" label-visible is-textarea />
            <div class="sources-editor__actions">
              <DsfrButton label="Enregistrer" size="sm" :disabled="!editName.trim() || busy" @click="saveEdit" />
              <DsfrButton label="Annuler" size="sm" secondary @click="editingId = undefined" />
            </div>
          </div>
        </template>
        <template v-else>
          <div class="sources-editor__text">
            <strong>{{ source.name }}</strong>
            <span v-if="source.description" class="fr-text--sm sources-editor__description">{{ source.description }}</span>
          </div>
          <div class="sources-editor__actions">
            <DsfrButton label="Modifier" icon="ri-edit-line" size="sm" tertiary @click="startEdit(source)" />
            <DsfrButton label="Supprimer" icon="ri-delete-bin-line" size="sm" tertiary :disabled="busy" @click="confirmRemove(source)" />
          </div>
        </template>
      </li>
    </ul>

    <div class="sources-editor__new">
      <h3 class="fr-h6">Nouvelle source</h3>
      <DsfrInput v-model="newName" label="Nom" label-visible placeholder="Ex. : Guichet, Courrier, Autre administration" />
      <DsfrInput v-model="newDescription" label="Description" hint="L'IA la reçoit en contexte pour comprendre la pièce." label-visible is-textarea />
      <DsfrButton label="Ajouter la source" icon="ri-add-line" :disabled="!newName.trim() || busy" @click="add" />
    </div>
  </div>
</template>

<style scoped>
.sources-editor__empty {
  color: var(--text-mention-grey);
}

.sources-editor__list {
  list-style: none;
  margin: 0 0 2rem;
  padding: 0;
}

.sources-editor__item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.85rem 0;
  border-top: 1px solid var(--border-default-grey);
}

.sources-editor__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.sources-editor__description {
  color: var(--text-mention-grey);
}

.sources-editor__form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
}

.sources-editor__actions {
  display: flex;
  gap: 0.5rem;
  flex: 0 0 auto;
}

.sources-editor__new {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1rem;
  max-width: 40rem;
}
</style>
