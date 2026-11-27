<script setup lang="ts">
/** Des personnes avec leur rôle. Sans le droit d'agir sur une ligne, ses commandes sont masquées. */
export interface PersonRow {
  key: string;
  name: string;
  email: string;
  roleId: string;
  pending: boolean;
  editable: boolean;
}

const props = defineProps<{
  people: PersonRow[];
  /** Tous les rôles ; `assignable` à faux : proposé nulle part, mais affichable. */
  roles: { id: string; name: string; assignable?: boolean }[];
  emptyText: string;
}>();
const emit = defineEmits<{ role: [key: string, roleId: string]; remove: [key: string] }>();

const roleName = (id: string) => props.roles.find((r) => r.id === id)?.name ?? "";
</script>

<template>
  <p v-if="!people.length" class="fr-text--sm">{{ emptyText }}</p>
  <ul v-else class="group-card">
    <li v-for="person in people" :key="person.key" class="group-card__row">
      <span class="group-card__main">
        <span class="group-card__title">{{ person.name || person.email }}</span>
        <span v-if="person.name && person.email" class="group-card__detail">{{ person.email }}</span>
        <span v-if="person.pending" class="fr-badge fr-badge--sm fr-badge--info fr-badge--no-icon">En attente de connexion</span>
      </span>
      <template v-if="person.editable">
        <select
          class="fr-select person-rows__role"
          :value="person.roleId"
          :aria-label="`Rôle de ${person.name || person.email}`"
          @change="emit('role', person.key, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="role in roles.filter((r) => r.assignable !== false)" :key="role.id" :value="role.id">{{ role.name }}</option>
        </select>
        <button
          type="button"
          class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
          :aria-label="`Retirer ${person.name || person.email}`"
          @click="emit('remove', person.key)"
        >
          Retirer
        </button>
      </template>
      <span v-else class="group-card__detail">{{ roleName(person.roleId) }}</span>
    </li>
  </ul>
</template>

<style scoped src="./cards.css"></style>
<style scoped>
.person-rows__role {
  width: auto;
  margin: 0;
}
</style>
