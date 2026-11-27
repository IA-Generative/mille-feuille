<script setup lang="ts">
/** Les membres d'un groupe et son journal. */
import { computed, ref, watch } from "vue";

import AddPersonForm from "@/components/groups/AddPersonForm.vue";
import PersonRows from "@/components/groups/PersonRows.vue";
import { useGroups } from "@/composables/useGroups";

const props = defineProps<{ groupId: string }>();
const emit = defineEmits<{ edit: [] }>();

const { persona, groupById, can, addMember, setMemberRole, removeMember, hasAdmin } = useGroups();

const group = computed(() => groupById(props.groupId)!);
const manages = computed(() => can("group.members", props.groupId));
const error = ref("");
watch(
  () => props.groupId,
  () => (error.value = ""),
);

const add = (email: string, roleId: string) => (error.value = addMember(props.groupId, email, roleId) ?? "");
const formatDate = (iso: string) => new Date(iso).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
</script>

<template>
  <section :aria-label="`Groupe ${group.name}`">
    <div class="group-detail__header">
      <div>
        <h2 class="fr-h4 fr-mb-0">{{ group.name }}</h2>
        <p class="fr-text--sm fr-mb-0">{{ group.description }}</p>
      </div>
      <button v-if="persona.superAdmin" type="button" class="fr-btn fr-btn--tertiary fr-btn--sm" @click="emit('edit')">
        Modifier le groupe
      </button>
    </div>

    <p v-if="!hasAdmin(group)" class="fr-text--sm group-detail__warning">Ce groupe n'a pas d'admin.</p>

    <h3 class="fr-text--md fr-mt-3w fr-mb-1w">Membres ({{ group.members.length }})</h3>
    <PersonRows
      :people="group.members"
      :editable="manages"
      empty-text="Aucun membre."
      @role="(email, roleId) => setMemberRole(groupId, email, roleId)"
      @remove="(email) => removeMember(groupId, email)"
    />
    <AddPersonForm v-if="manages" class="fr-mt-2w" :error="error" @add="add" />
    <p v-else class="fr-hint-text fr-mt-1w">Seuls l'admin du groupe et les super admins gèrent les membres.</p>

    <DsfrAccordion v-if="manages && group.journal.length" class="fr-mt-3w" :title="`Journal des changements (${group.journal.length})`">
      <ul class="fr-text--sm">
        <li v-for="entry in group.journal" :key="entry.id">{{ formatDate(entry.at) }} · {{ entry.author }} · {{ entry.text }}</li>
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

.group-detail__warning {
  margin: 0.75rem 0 0;
  color: var(--text-default-warning);
}
</style>
