<script setup lang="ts">
/** Créer ou modifier un rôle (super admin) : permissions cochées et historique. `roleId` null : création. */
import { computed, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import AppModal from "@/components/AppModal.vue";
import { useGroups } from "@/composables/useGroups";
import { useAuth } from "@/composables/useAuth";
import { describeVersion, PERMISSION_FAMILIES } from "@/types/groups";
import { userMessage } from "@/utils/api";

const props = defineProps<{ opened: boolean; roleId: string | null }>();
const emit = defineEmits<{ close: [] }>();

const { isAdmin } = useAuth();
const { roles, saveRole, restoreRole, removeRole } = useGroups();

const name = ref("");
const description = ref("");
const permissions = ref<string[]>([]);
const error = ref("");
const current = computed(() => roles.value.find((r) => r.id === props.roleId));
const editable = computed(() => isAdmin.value && !current.value?.system);

function fill() {
  name.value = current.value?.name ?? "";
  description.value = current.value?.description ?? "";
  permissions.value = [...(current.value?.permissions ?? [])];
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
  if (!name.value.trim() || !permissions.value.length) {
    error.value = "Donnez un nom et au moins une permission.";
    return;
  }
  attempt(async () => {
    const content = { name: name.value.trim(), description: description.value.trim(), permissions: permissions.value };
    await saveRole(content, current.value?.id);
    emit("close");
  }, "Le rôle n'a pas pu être enregistré.");
}

function restore(versionId: string) {
  attempt(async () => {
    await restoreRole(current.value!.id, versionId);
    fill();
  }, "La version n'a pas pu être restaurée.");
}

function remove() {
  if (!confirm(`Supprimer le rôle « ${current.value!.name} » ?`)) return;
  attempt(async () => {
    await removeRole(current.value!.id);
    emit("close");
  }, "Le rôle n'a pas pu être supprimé.");
}

const actions = computed(() =>
  editable.value
    ? [
        { label: "Annuler", secondary: true, onClick: () => emit("close") },
        { label: "Enregistrer", onClick: submit },
      ]
    : [{ label: "Fermer", onClick: () => emit("close") }],
);
</script>

<template>
  <AppModal :opened="opened" :title="current ? current.name : 'Nouveau rôle'" :actions="actions" @close="emit('close')">
    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
    <p v-if="current?.system" class="fr-text--sm">Rôle fourni par l'application : il ne se modifie pas.</p>
    <template v-if="editable">
      <DsfrInput v-model="name" label="Nom du rôle" label-visible required />
      <div class="fr-mt-2w">
        <DsfrInput v-model="description" label="Description" label-visible />
      </div>
    </template>

    <fieldset v-for="family in PERMISSION_FAMILIES" :key="family.title" class="role-modal__family" :disabled="!editable">
      <legend>{{ family.title }}</legend>
      <label v-for="(label, key) in family.permissions" :key="key" class="role-modal__permission">
        <input v-model="permissions" type="checkbox" :value="key" />
        {{ label }}
      </label>
    </fieldset>

    <template v-if="current && editable">
      <VersionHistory :versions="current.versions" :format-content="describeVersion" @restore="restore" />
      <button type="button" class="fr-btn fr-btn--tertiary fr-btn--sm fr-mt-2w" :disabled="current.inUse" @click="remove">
        Supprimer ce rôle
      </button>
      <p v-if="current.inUse" class="fr-hint-text">Ce rôle est encore attribué à des personnes.</p>
    </template>
  </AppModal>
</template>

<style scoped>
.role-modal__family {
  margin: 1rem 0 0;
  padding: 0;
  border: 0;
}

.role-modal__family legend {
  padding: 0;
  font-weight: 700;
}

.role-modal__permission {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
}
</style>
