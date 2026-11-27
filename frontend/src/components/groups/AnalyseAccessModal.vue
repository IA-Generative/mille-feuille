<script setup lang="ts">
/** Qui voit une analyse : ses groupes et les personnes ajoutées, avec historique (maquette). */
import { computed, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import AppModal from "@/components/AppModal.vue";
import AddPersonForm from "@/components/groups/AddPersonForm.vue";
import MockNotice from "@/components/groups/MockNotice.vue";
import PersonRows from "@/components/groups/PersonRows.vue";
import { useMockAccess } from "@/composables/useMockAccess";
import type { AccessContent, MockAssignment } from "@/types/mockAccess";

const props = defineProps<{ opened: boolean; analyseId: string }>();
const emit = defineEmits<{ close: [] }>();

const { persona, roles, groups, groupById, managesAccessIn, knownPerson, roleById, accessOf, canManageAccess, saveAccess, restoreAccess } =
  useMockAccess();

const groupIds = ref<string[]>([]);
const people = ref<MockAssignment[]>([]);
const error = ref("");

const access = computed(() => (props.opened ? accessOf(props.analyseId) : null));
const editable = computed(() => props.opened && canManageAccess(props.analyseId));

function fill() {
  const saved = accessOf(props.analyseId);
  groupIds.value = [...saved.groupIds];
  people.value = saved.people.map((p) => ({ ...p }));
  error.value = "";
}

watch(
  () => props.opened,
  (isOpened) => isOpened && fill(),
  { immediate: true },
);

/** On n'associe ou ne retire que les groupes où l'on gère les accès. */
const canToggle = (groupId: string) => editable.value && managesAccessIn(groupId);

const rows = computed(() => people.value.map((p) => ({ ...p, key: p.email, pending: !p.name, editable: editable.value })));

function add(who: { email: string } | { userId: string }, roleId: string) {
  if (!("email" in who)) return;
  const address = who.email.toLowerCase();
  if (people.value.some((p) => p.email === address)) {
    error.value = "Cette personne est déjà ajoutée.";
    return;
  }
  error.value = "";
  people.value.push({ email: address, name: knownPerson(address)?.name ?? "", roleId });
}

function setRole(email: string, roleId: string) {
  people.value = people.value.map((p) => (p.email === email ? { ...p, roleId } : p));
}

function submit() {
  if (!persona.value.superAdmin && !groupIds.value.length) {
    error.value = "Gardez au moins un groupe.";
    return;
  }
  saveAccess(props.analyseId, { groupIds: groupIds.value, people: people.value });
  emit("close");
}

function restore(versionId: string) {
  restoreAccess(props.analyseId, versionId);
  fill();
}

const describe = (content: AccessContent) =>
  [
    `Groupes : ${content.groupIds.map((id) => groupById(id)?.name ?? "supprimé").join(", ") || "aucun"}`,
    `Personnes : ${content.people.map((p) => `${p.name || p.email} (${roleById(p.roleId)?.name})`).join(", ") || "aucune"}`,
  ].join(" · ");

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
  <AppModal :opened="opened" title="Accès à l'analyse" size="lg" :actions="actions" @close="emit('close')">
    <MockNotice class="fr-mb-2w" />
    <p v-if="!editable" class="fr-text--sm">Seuls l'admin d'un groupe associé et les super admins modifient les accès.</p>

    <fieldset class="access-groups">
      <legend>Groupes</legend>
      <label v-for="group in groups" :key="group.id" class="access-groups__item">
        <input v-model="groupIds" type="checkbox" :value="group.id" :disabled="!canToggle(group.id)" />
        {{ group.name }}
      </label>
    </fieldset>
    <p v-if="!groupIds.length" class="fr-text--sm">Sans groupe, seuls les super admins et les personnes ajoutées voient l'analyse.</p>

    <h3 class="fr-text--md fr-mt-2w fr-mb-1w">Personnes ajoutées</h3>
    <PersonRows
      :people="rows"
      :roles="roles"
      empty-text="Aucune personne ajoutée en plus des groupes."
      @role="setRole"
      @remove="(email) => (people = people.filter((p) => p.email !== email))"
    />
    <AddPersonForm v-if="editable" class="fr-mt-2w" :roles="roles" @add="add" />
    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>

    <VersionHistory v-if="access" :versions="access.versions" :format-content="describe" :readonly="!editable" @restore="restore" />
  </AppModal>
</template>

<style scoped>
.access-groups {
  margin: 0;
  padding: 0;
  border: 0;
}

.access-groups legend {
  padding: 0;
  font-weight: 700;
}

.access-groups__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
}
</style>
