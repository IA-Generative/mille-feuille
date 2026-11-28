<script setup lang="ts">
/** Étiquettes sélectionnables du DSFR, qui servent à la fois de légende et de filtre des types de liens. */
import KindDot from "@/components/crossSearch/KindDot.vue";
import { SHARED_KINDS, type SharedKind } from "@/types/crossSearch";

const props = defineProps<{ modelValue: SharedKind[]; present: SharedKind[] }>();
const emit = defineEmits<{ "update:modelValue": [kinds: SharedKind[]] }>();

function toggle(kind: SharedKind) {
  const next = props.modelValue.includes(kind)
    ? props.modelValue.filter((k) => k !== kind)
    : [...props.modelValue, kind];
  emit("update:modelValue", next);
}
</script>

<template>
  <ul class="fr-tags-group link-filters" aria-label="Types de liens affichés">
    <li v-for="kind in SHARED_KINDS.filter((k) => present.includes(k.value))" :key="kind.value">
      <button type="button" class="fr-tag" :aria-pressed="modelValue.includes(kind.value)" @click="toggle(kind.value)">
        <KindDot :kind="kind.value" class="fr-mr-1v" />
        {{ kind.label }}
      </button>
    </li>
  </ul>
</template>

<style scoped>
.link-filters {
  margin: 0;
}
</style>
