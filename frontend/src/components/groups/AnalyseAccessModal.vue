<script setup lang="ts">
/** Qui voit une analyse : ses groupes et les personnes ajoutées, avec historique. */
import { computed, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import AppModal from "@/components/AppModal.vue";
import AddPersonForm from "@/components/groups/AddPersonForm.vue";
import PersonRows from "@/components/groups/PersonRows.vue";
import { useAnalyseAccess } from "@/composables/useAnalyseAccess";
import { useGroups } from "@/composables/useGroups";
import { describeAccess, type AccessPerson, type AnalyseAccess } from "@/types/analyseAccess";
import { userMessage } from "@/utils/api";

const props = defineProps<{ opened: boolean; analyseId: string }>();
const emit = defineEmits<{ close: [] }>();

const { fetchAccess, saveAccess, restoreAccess } = useAnalyseAccess(() => props.analyseId);
const { fetchRoles, searchPeople } = useGroups();

const access = ref<AnalyseAccess | null>(null);
const roles = ref<{ id: string; name: string }[]>([]);
const groupIds = ref<string[]>([]);
const people = ref<AccessPerson[]>([]);
const error = ref("");

const editable = computed(() => access.value?.canEdit ?? false);
const offeredRoles = computed(() =>
  roles.value.map((r) => ({ ...r, assignable: access.value?.assignableRoleIds.includes(r.id) ?? false })),
);
/** Les groupes associés, puis ceux qu'on peut ajouter. */
const groupChoices = computed(() => {
  const current = access.value?.groups ?? [];
  const others = (access.value?.availableGroups ?? [])
    .filter((g) => !current.some((c) => c.id === g.id))
    .map((g) => ({ ...g, editable: true }));
  return [...current, ...others];
});

const keyOf = (p: AccessPerson) => p.id ?? p.userId ?? p.email;
const rows = computed(() => people.value.map((p) => ({ ...p, key: keyOf(p) })));

function fill(loaded: AnalyseAccess) {
  access.value = loaded;
  groupIds.value = loaded.groups.map((g) => g.id);
  people.value = loaded.people.map((p) => ({ ...p }));
}

async function attempt(action: () => Promise<void>, fallback: string) {
  error.value = "";
  try {
    await action();
  } catch (cause) {
    error.value = userMessage(cause, fallback);
  }
}

watch(
  () => props.opened,
  (isOpened) => {
    if (!isOpened) return;
    access.value = null;
    attempt(async () => {
      const [loaded, allRoles] = await Promise.all([fetchAccess(), fetchRoles()]);
      roles.value = allRoles;
      fill(loaded);
    }, "Les accès n'ont pas pu être chargés.");
  },
  { immediate: true },
);

function add(who: { email: string } | { userId: string }, roleId: string, label: string) {
  const person: AccessPerson = {
    ...("userId" in who ? { userId: who.userId, name: label, email: "" } : { name: "", email: who.email.toLowerCase() }),
    roleId,
    pending: !("userId" in who),
    editable: true,
  };
  if (people.value.some((p) => keyOf(p) === keyOf(person) || (person.email && p.email === person.email))) {
    error.value = "Cette personne est déjà ajoutée.";
    return;
  }
  error.value = "";
  people.value.push(person);
}

const setRole = (key: string, roleId: string) =>
  (people.value = people.value.map((p) => (keyOf(p) === key ? { ...p, roleId } : p)));

const submit = () =>
  attempt(async () => {
    await saveAccess(groupIds.value, people.value);
    emit("close");
  }, "Les accès n'ont pas pu être enregistrés.");

const restore = (versionId: string) =>
  attempt(async () => fill(await restoreAccess(versionId)), "La version n'a pas pu être restaurée.");

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
    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
    <p v-if="!access && !error" class="fr-text--sm" role="status">Chargement…</p>
    <template v-if="access">
      <p v-if="!editable" class="fr-text--sm">Seuls l'admin d'un groupe associé et les super admins modifient les accès.</p>

      <fieldset class="access-groups">
        <legend>Groupes</legend>
        <label v-for="group in groupChoices" :key="group.id" class="access-groups__item">
          <input v-model="groupIds" type="checkbox" :value="group.id" :disabled="!group.editable" />
          {{ group.name }}
        </label>
      </fieldset>
      <p v-if="!groupIds.length" class="fr-text--sm">Sans groupe, seuls les super admins et les personnes ajoutées voient l'analyse.</p>

      <h3 class="fr-text--md fr-mt-2w fr-mb-1w">Personnes ajoutées</h3>
      <PersonRows
        :people="rows"
        :roles="offeredRoles"
        empty-text="Aucune personne ajoutée en plus des groupes."
        @role="setRole"
        @remove="(key) => (people = people.filter((p) => keyOf(p) !== key))"
      />
      <AddPersonForm v-if="editable" class="fr-mt-2w" :roles="offeredRoles" :search="searchPeople" @add="add" />

      <VersionHistory v-if="editable" :versions="access.versions" :format-content="describeAccess" @restore="restore" />
    </template>
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
