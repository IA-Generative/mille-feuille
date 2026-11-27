<script setup lang="ts">
/** Maquette : les groupes d'une analyse qu'on crée, parmi ceux où l'on peut en créer. Non envoyé au serveur. */
import { useGroups } from "@/composables/useGroups";

const selected = defineModel<string[]>({ required: true });
const { creationGroups } = useGroups();
</script>

<template>
  <fieldset class="creation-groups">
    <legend>Groupes ayant accès <span class="fr-badge fr-badge--sm fr-badge--info fr-badge--no-icon">Maquette</span></legend>
    <p class="fr-hint-text">Au moins un, parmi les vôtres. Ce choix n'est pas encore enregistré.</p>
    <label v-for="group in creationGroups" :key="group.id" class="creation-groups__item">
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
