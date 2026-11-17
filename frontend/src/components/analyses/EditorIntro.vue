<script setup lang="ts">
defineProps<{ id?: string }>();
</script>

<template>
  <DsfrAlert type="info" small>
    <div :id="id"><slot /></div>
  </DsfrAlert>
</template>
