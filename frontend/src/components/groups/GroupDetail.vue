<script setup lang="ts">
/** Les membres d'un groupe et son journal. */
import { computed, onMounted, ref } from "vue";

import AddPersonForm from "@/components/groups/AddPersonForm.vue";
import PersonRows from "@/components/groups/PersonRows.vue";
import { useAuth } from "@/composables/useAuth";
import { useGroups } from "@/composables/useGroups";
import { describeEvent, type GroupEvent, type Member, type Role } from "@/types/groups";
import { userMessage } from "@/utils/api";

const props = defineProps<{ groupId: string }>();
const emit = defineEmits<{ edit: [] }>();

const { isAdmin } = useAuth();
const { groups, fetchGroups, fetchRoles, fetchMembers, fetchEvents, addMember, setMemberRole, removeMember, searchPeople } =
  useGroups();

const group = computed(() => groups.value.find((g) => g.id === props.groupId)!);
const manages = computed(() => group.value.canManageMembers);
const members = ref<Member[]>([]);
const roles = ref<Role[]>([]);
const events = ref<GroupEvent[]>([]);
const isLoaded = ref(false);
const error = ref("");

const rows = computed(() => members.value.map((m) => ({ ...m, key: m.id })));

async function load() {
  [members.value, roles.value] = await Promise.all([fetchMembers(props.groupId), fetchRoles(props.groupId)]);
  events.value = manages.value ? await fetchEvents(props.groupId) : [];
  isLoaded.value = true;
}

/** Une action sur les membres, puis relecture : la liste montre ce que le serveur a retenu. */
async function change(action: () => Promise<unknown>, fallback: string) {
  error.value = "";
  try {
    await action();
  } catch (cause) {
    error.value = userMessage(cause, fallback);
  }
  await load().catch((cause) => (error.value = userMessage(cause, "Les membres n'ont pas pu être chargés.")));
  await fetchGroups().catch(() => {});
}

onMounted(() => load().catch((cause) => (error.value = userMessage(cause, "Les membres n'ont pas pu être chargés."))));

const formatDate = (iso: string) => new Date(iso).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
</script>

<template>
  <section v-if="group" :aria-label="`Groupe ${group.name}`">
    <div class="group-detail__header">
      <div>
        <h2 class="fr-h4 fr-mb-0">{{ group.name }}</h2>
        <p class="fr-text--sm fr-mb-0">{{ group.description }}</p>
      </div>
      <button v-if="isAdmin" type="button" class="fr-btn fr-btn--tertiary fr-btn--sm" @click="emit('edit')">Modifier le groupe</button>
    </div>

    <h3 class="fr-text--md fr-mt-3w fr-mb-1w">Membres ({{ group.memberCount }})</h3>
    <p v-if="!isLoaded && !error" class="fr-text--sm">Chargement…</p>
    <PersonRows
      v-else
      :people="rows"
      :roles="roles"
      empty-text="Aucun membre."
      @role="(id, roleId) => change(() => setMemberRole(groupId, id, roleId), 'Le rôle n\'a pas pu être changé.')"
      @remove="(id) => change(() => removeMember(groupId, id), 'La personne n\'a pas pu être retirée.')"
    />
    <AddPersonForm
      v-if="manages"
      class="fr-mt-2w"
      :roles="roles"
      :search="searchPeople"
      @add="(who, roleId) => change(() => addMember(groupId, who, roleId), 'La personne n\'a pas pu être ajoutée.')"
    />
    <p v-else class="fr-hint-text fr-mt-1w">Seuls l'admin du groupe et les super admins gèrent les membres.</p>
    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>

    <DsfrAccordion v-if="events.length" class="fr-mt-3w" :title="`Journal des changements (${events.length})`">
      <ul class="fr-text--sm">
        <li v-for="event in events" :key="event.id">{{ formatDate(event.createdAt) }} · {{ describeEvent(event) }}</li>
      </ul>
    </DsfrAccordion>
  </section>
</template>

<style scoped>
.group-detail__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
}
</style>
