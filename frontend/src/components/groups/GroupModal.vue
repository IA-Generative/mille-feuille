<script setup lang="ts">
/** Créer ou modifier un groupe (super admin), avec son historique. `groupId` null : création. */
import { computed, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import AppModal from "@/components/AppModal.vue";
import { useGroups } from "@/composables/useGroups";
import { describeVersion } from "@/types/groups";
import { userMessage } from "@/utils/api";

const props = defineProps<{ opened: boolean; groupId: string | null }>();
const emit = defineEmits<{ close: []; saved: [id: string] }>();

const { groups, saveGroup, restoreGroup, removeGroup } = useGroups();

const name = ref("");
const description = ref("");
const error = ref("");
const current = computed(() => groups.value.find((g) => g.id === props.groupId));

function fill() {
  name.value = current.value?.name ?? "";
  description.value = current.value?.description ?? "";
  error.value = "";
}

watch(
  () => props.opened,
  (isOpened) => isOpened && fill(),
);

async function attempt(action: () => Promise<void>, fallback: string) {
  error.value = "";
  try {
    await action();
  } catch (cause) {
    error.value = userMessage(cause, fallback);
  }
}

function submit() {
  if (!name.value.trim()) {
    error.value = "Donnez un nom au groupe.";
    return;
  }
  attempt(async () => {
    emit("saved", await saveGroup({ name: name.value.trim(), description: description.value.trim() }, current.value?.id));
    emit("close");
  }, "Le groupe n'a pas pu être enregistré.");
}

function restore(versionId: string) {
  attempt(async () => {
    await restoreGroup(current.value!.id, versionId);
    fill();
  }, "La version n'a pas pu être restaurée.");
}

function remove() {
  if (!confirm(`Supprimer le groupe « ${current.value!.name} » ?`)) return;
  attempt(async () => {
    await removeGroup(current.value!.id);
    emit("close");
  }, "Le groupe n'a pas pu être supprimé.");
}
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
      <VersionHistory :versions="current.versions" :format-content="describeVersion" @restore="restore" />
      <button type="button" class="fr-btn fr-btn--tertiary fr-btn--sm fr-mt-2w" :disabled="!current.deletable" @click="remove">
        Supprimer ce groupe
      </button>
      <p v-if="!current.deletable" class="fr-hint-text">Il a des membres, ou des dossiers ou outils s'y réfèrent.</p>
    </template>
  </AppModal>
</template>
