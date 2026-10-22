<script setup lang="ts">
// Prévu pour les exécutions sans personne connectée (créneaux de traitement).
// Pas encore activable : voir docs/tools-mcp-plan.md.
</script>

<template>
  <DsfrToggleSwitch
    :model-value="false"
    disabled
    label="Utiliser un compte de service quand personne n'est connecté (bientôt disponible)"
    hint="Nécessaire pour les traitements lancés par un créneau."
  />
</template>
