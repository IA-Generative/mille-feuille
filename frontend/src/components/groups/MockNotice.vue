<script setup lang="ts">
/** Bandeau de maquette et choix du point de vue. */
import { useGroups } from "@/composables/useGroups";

const { personas, personaId } = useGroups();
</script>

<template>
  <div class="mock-notice" role="note">
    <p class="mock-notice__text">
      <strong>Maquette.</strong> Données fictives : rien n'est enregistré et les droits réels ne changent pas.
    </p>
    <label class="mock-notice__persona">
      Voir en tant que
      <select v-model="personaId" class="fr-select">
        <option v-for="p in personas" :key="p.id" :value="p.id">{{ p.label }}</option>
      </select>
    </label>
  </div>
</template>

<style scoped>
.mock-notice {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  padding: 0.75rem 1rem;
  border-radius: 0.875rem;
  background: var(--background-contrast-info);
}

.mock-notice__text {
  margin: 0;
  font-size: 0.875rem;
}

.mock-notice__persona {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.mock-notice__persona select {
  width: auto;
  margin: 0;
}
</style>
