<script setup lang="ts">
const audience = defineModel<string>({ required: true });
</script>

<template>
  <DsfrInput
    v-model="audience"
    label="Audience Keycloak du serveur"
    label-visible
    placeholder="mcp-legifrance"
    hint="Identifiant du client Keycloak du serveur : le jeton de la personne est échangé pour lui, jamais transmis tel quel."
    required
  />
</template>
