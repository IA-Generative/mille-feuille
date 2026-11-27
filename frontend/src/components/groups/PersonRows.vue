<script setup lang="ts">
/** Des personnes avec leur rôle. En lecture seule, les commandes sont masquées. */
import { useGroups } from "@/composables/useGroups";
import type { Assignment } from "@/types/groups";

defineProps<{ people: Assignment[]; editable: boolean; emptyText: string }>();
const emit = defineEmits<{ role: [email: string, roleId: string]; remove: [email: string] }>();

const { roles, roleById } = useGroups();
</script>

<template>
  <p v-if="!people.length" class="fr-text--sm">{{ emptyText }}</p>
  <ul v-else class="group-card">
    <li v-for="person in people" :key="person.email" class="group-card__row">
      <span class="group-card__main">
        <span class="group-card__title">{{ person.name || person.email }}</span>
        <span v-if="person.name" class="group-card__detail">{{ person.email }}</span>
        <span v-else class="fr-badge fr-badge--sm fr-badge--info fr-badge--no-icon">En attente de première connexion</span>
      </span>
      <template v-if="editable">
        <select
          class="fr-select person-rows__role"
          :value="person.roleId"
          :aria-label="`Rôle de ${person.name || person.email}`"
          @change="emit('role', person.email, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="role in roles" :key="role.id" :value="role.id">{{ role.name }}</option>
        </select>
        <button
          type="button"
          class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm"
          :aria-label="`Retirer ${person.name || person.email}`"
          @click="emit('remove', person.email)"
        >
          Retirer
        </button>
      </template>
      <span v-else class="group-card__detail">{{ roleById(person.roleId)?.name }}</span>
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
