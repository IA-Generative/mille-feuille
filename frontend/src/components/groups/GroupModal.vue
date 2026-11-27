<script setup lang="ts">
/** Créer ou modifier un groupe (super admin), avec son historique. `groupId` null : création. */
import { computed, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import AppModal from "@/components/AppModal.vue";
import { useGroups } from "@/composables/useGroups";
import type { GroupContent } from "@/types/groups";

const props = defineProps<{ opened: boolean; groupId: string | null }>();
const emit = defineEmits<{ close: []; saved: [id: string] }>();

const { groupById, saveGroup, restoreGroup, isGroupUsed, removeGroup } = useGroups();

const name = ref("");
const description = ref("");
const error = ref("");
const current = computed(() => (props.groupId ? groupById(props.groupId) : undefined));

function fill() {
  name.value = current.value?.name ?? "";
  description.value = current.value?.description ?? "";
  error.value = "";
}

watch(
  () => props.opened,
  (isOpened) => isOpened && fill(),
);

function submit() {
  if (!name.value.trim()) {
    error.value = "Donnez un nom au groupe.";
    return;
  }
  emit("saved", saveGroup({ name: name.value.trim(), description: description.value.trim() }, current.value?.id));
  emit("close");
}

function restore(versionId: string) {
  restoreGroup(current.value!.id, versionId);
  fill();
}

function remove() {
  if (!confirm(`Supprimer le groupe « ${current.value!.name} » ?`)) return;
  removeGroup(current.value!.id);
  emit("close");
}

const describe = (content: GroupContent) => [content.name, content.description].filter(Boolean).join(" · ");
</script>

<template>
  <AppModal
    :opened="opened"
    :title="groupId ? 'Modifier le groupe' : 'Nouveau groupe'"
    :actions="[
      { label: 'Annuler', secondary: true, onClick: () => emit('close') },
      { label: 'Enregistrer', onClick: submit },
    ]"
    @close="emit('close')"
  >
    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
    <DsfrInput v-model="name" label="Nom du groupe" label-visible required />
    <div class="fr-mt-2w">
      <DsfrInput v-model="description" label="Description" label-visible is-textarea />
    </div>
    <template v-if="current">
      <VersionHistory :versions="current.versions" :format-content="describe" @restore="restore" />
      <button type="button" class="fr-btn fr-btn--tertiary fr-btn--sm fr-mt-2w" :disabled="isGroupUsed(current.id)" @click="remove">
        Supprimer ce groupe
      </button>
      <p v-if="isGroupUsed(current.id)" class="fr-hint-text">Retirez d'abord ses membres et ses analyses.</p>
    </template>
  </AppModal>
</template>
