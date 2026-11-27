<script setup lang="ts">
/** Les rôles. Création et modification réservées aux super admins ; les autres les consultent. */
import { onMounted, ref } from "vue";

import RoleModal from "@/components/groups/RoleModal.vue";
import { useAuth } from "@/composables/useAuth";
import { useGroups } from "@/composables/useGroups";
import { userMessage } from "@/utils/api";

const { isAdmin } = useAuth();
const { roles, fetchRoles } = useGroups();

const error = ref("");
onMounted(() => fetchRoles().catch((cause) => (error.value = userMessage(cause, "Les rôles n'ont pas pu être chargés."))));

const isModalOpened = ref(false);
const editedId = ref<string | null>(null);

function openModal(id: string | null) {
  editedId.value = id;
  isModalOpened.value = true;
}
</script>

<template>
  <div>
    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
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
    <button v-if="isAdmin" type="button" class="fr-btn fr-btn--secondary fr-btn--sm fr-mt-2w" @click="openModal(null)">
      Créer un rôle
    </button>
    <RoleModal :opened="isModalOpened" :role-id="editedId" @close="isModalOpened = false" />
  </div>
</template>

<style scoped src="./cards.css"></style>
