<script setup lang="ts">
/** Les groupes d'une analyse qu'on crée, parmi ceux où l'on peut en créer. */
import { computed, onMounted } from "vue";

import { useGroups } from "@/composables/useGroups";

const selected = defineModel<string[]>({ required: true });
const { groups, fetchGroups } = useGroups();

const offered = computed(() => groups.value.filter((g) => g.canCreateAnalyses));

onMounted(async () => {
  await fetchGroups().catch(() => {});
  // Un seul choix possible : il est fait.
  if (offered.value.length === 1 && !selected.value.length) selected.value = [offered.value[0].id];
});
</script>

<template>
  <fieldset v-if="offered.length" class="creation-groups">
    <legend>Groupes ayant accès</legend>
    <p class="fr-hint-text">Leurs membres verront l'analyse. Sans choix, ce sont tous vos groupes.</p>
    <label v-for="group in offered" :key="group.id" class="creation-groups__item">
      <input v-model="selected" type="checkbox" :value="group.id" />
      {{ group.name }}
    </label>
  </fieldset>
</template>

<style scoped>
.creation-groups {
  margin: 1rem 0 0;
  padding: 0;
  border: 0;
}

.creation-groups legend {
  padding: 0;
}

.creation-groups__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
}
</style>
