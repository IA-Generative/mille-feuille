<script setup lang="ts">
/** Pastille de la couleur d'un type de point commun (la même que dans le graphe). */
import { SHARED_KINDS, type SharedKind } from "@/types/crossSearch";

const props = defineProps<{ kind: SharedKind }>();
const color = () => SHARED_KINDS.find((k) => k.value === props.kind)!.color;
</script>

<template>
  <span class="kind-dot" :style="{ background: color() }" aria-hidden="true" />
</template>

<style scoped>
.kind-dot {
  display: inline-block;
  flex: none;
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 50%;
}
</style>
