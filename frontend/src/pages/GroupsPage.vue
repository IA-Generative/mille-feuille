<script setup lang="ts">
/** Groupes et rôles de l'application. */
import { ref } from "vue";

import GroupsTab from "@/components/groups/GroupsTab.vue";
import RolesTab from "@/components/groups/RolesTab.vue";

const TABS = { groups: "Groupes", roles: "Rôles" } as const;
const tab = ref<keyof typeof TABS>("groups");
</script>

<template>
  <div class="groups-page">
    <h1 class="fr-h2 fr-mb-0">Groupes et rôles</h1>
    <div class="groups-page__segments" role="group" aria-label="Section">
      <button v-for="(label, key) in TABS" :key="key" type="button" class="groups-page__segment" :aria-pressed="tab === key" @click="tab = key">
        {{ label }}
      </button>
    </div>
    <GroupsTab v-if="tab === 'groups'" />
    <RolesTab v-else />
  </div>
</template>

<style scoped>
.groups-page {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.groups-page__segments {
  display: inline-flex;
  align-self: flex-start;
  gap: 0.125rem;
  padding: 0.125rem;
  border-radius: 0.625rem;
  background: var(--background-contrast-grey);
}

.groups-page__segment {
  padding: 0.25rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
}

.groups-page__segment[aria-pressed="true"] {
  background: var(--background-default-grey);
  font-weight: 500;
}
</style>
