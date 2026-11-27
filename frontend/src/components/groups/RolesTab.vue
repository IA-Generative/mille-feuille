<script setup lang="ts">
/** Les rôles. Création et modification réservées aux super admins ; les autres les consultent. */
import { ref } from "vue";

import RoleModal from "@/components/groups/RoleModal.vue";
import { useGroups } from "@/composables/useGroups";

const { persona, roles } = useGroups();

const isModalOpened = ref(false);
const editedId = ref<string | null>(null);

function openModal(id: string | null) {
  editedId.value = id;
  isModalOpened.value = true;
}
</script>

<template>
  <div>
    <ul class="group-card">
      <li v-for="role in roles" :key="role.id">
        <button type="button" class="group-card__row" @click="openModal(role.id)">
          <span class="group-card__main">
            <span class="group-card__title">{{ role.name }}</span>
            <span class="group-card__detail">{{ role.description }}</span>
          </span>
          <span class="group-card__detail">{{ role.permissions.length }} permission(s)</span>
        </button>
      </li>
    </ul>
    <button v-if="persona.superAdmin" type="button" class="fr-btn fr-btn--secondary fr-btn--sm fr-mt-2w" @click="openModal(null)">
      Créer un rôle
    </button>
    <RoleModal :opened="isModalOpened" :role-id="editedId" @close="isModalOpened = false" />
  </div>
</template>

<style scoped src="./cards.css"></style>
