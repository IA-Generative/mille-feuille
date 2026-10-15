<script setup lang="ts">
import { useClipboard } from "@/composables/useClipboard";

const props = defineProps<{ text: string; label?: string }>();

const clipboard = useClipboard();
</script>

<template>
  <button
    type="button"
    class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm copy"
    :title="`Copier « ${props.text} »`"
    @click.stop="clipboard.copy('value', props.text)"
  >
    {{ clipboard.copied.value ? "Copié" : (label ?? "Copier") }}
    <span class="fr-sr-only" role="status" aria-live="polite">{{ clipboard.copied.value ? "Texte copié" : "" }}</span>
  </button>
</template>

<style scoped>
.copy {
  flex: 0 0 auto;
}
</style>
