<script setup lang="ts">
const prompt = defineModel<string>({ required: true });
</script>

<template>
  <DsfrInput
    v-model="prompt"
    label="Demande au modèle"
    label-visible
    is-textarea
    hint="Le modèle n'a que cet outil : il choisit lui-même les paramètres à partir de votre demande."
  />
</template>
