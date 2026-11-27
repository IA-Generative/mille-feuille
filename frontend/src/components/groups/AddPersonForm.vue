<script setup lang="ts">
/** Ajouter une personne connue, ou une adresse pas encore connectée. */
import { ref, useId } from "vue";

import { useGroups } from "@/composables/useGroups";

const emit = defineEmits<{ add: [email: string, roleId: string] }>();
defineProps<{ error?: string }>();

const { roles, people } = useGroups();
const id = useId();
const email = ref("");
const roleId = ref("instructor");
const invalid = ref(false);

function submit() {
  const address = email.value.trim();
  invalid.value = !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(address);
  if (invalid.value) return;
  emit("add", address, roleId.value);
  email.value = "";
}
</script>

<template>
  <div>
    <form class="add-person" novalidate @submit.prevent="submit">
      <label class="fr-sr-only" :for="`${id}-email`">Adresse e-mail à ajouter</label>
      <input :id="`${id}-email`" v-model="email" class="fr-input add-person__email" type="email" placeholder="Adresse e-mail" :list="`${id}-people`" />
      <datalist :id="`${id}-people`">
        <option v-for="p in people" :key="p.email" :value="p.email">{{ p.name }}</option>
      </datalist>
      <label class="fr-sr-only" :for="`${id}-role`">Rôle de la personne ajoutée</label>
      <select :id="`${id}-role`" v-model="roleId" class="fr-select add-person__role">
        <option v-for="role in roles" :key="role.id" :value="role.id">{{ role.name }}</option>
      </select>
      <button type="submit" class="fr-btn fr-btn--secondary">Ajouter</button>
    </form>
    <p v-if="invalid || error" class="fr-error-text" role="alert">{{ invalid ? "Saisissez une adresse e-mail valide." : error }}</p>
  </div>
</template>

<style scoped>
.add-person {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.add-person__email {
  flex: 1;
  min-width: 14rem;
}

.add-person__role {
  width: auto;
}
</style>
