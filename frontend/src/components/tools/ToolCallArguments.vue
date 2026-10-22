<script setup lang="ts">
// Les arguments exacts que l'assistant veut passer à l'outil : ce sont ceux qui seront exécutés, rien d'autre.
defineProps<{ args: Record<string, unknown> }>();

const show = (value: unknown) => (typeof value === "string" ? value : JSON.stringify(value));
</script>

<template>
  <dl v-if="Object.keys(args).length > 0" class="tool-call-args">
    <template v-for="(value, key) in args" :key="key">
      <dt>{{ key }}</dt>
      <dd>{{ show(value) }}</dd>
    </template>
  </dl>
  <p v-else class="tool-call-args tool-call-args--empty">Aucun argument.</p>
</template>

<style scoped>
.tool-call-args {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.25rem 1rem;
  margin: 0;
  font-size: 0.8125rem;
}

.tool-call-args--empty {
  color: var(--text-mention-grey);
}

.tool-call-args dt {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--text-mention-grey);
}

.tool-call-args dd {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
