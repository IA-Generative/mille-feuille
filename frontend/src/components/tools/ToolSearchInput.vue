<script setup lang="ts">
withDefaults(defineProps<{ placeholder?: string }>(), { placeholder: "Rechercher un outil, un serveur…" });
const query = defineModel<string>({ required: true });
</script>

<template>
  <div class="tool-search-input">
    <span class="tool-search-input__icon" aria-hidden="true"><VIcon name="ri-search-line" /></span>
    <input
      v-model="query"
      type="search"
      class="tool-search-input__field"
      :placeholder="placeholder"
      :aria-label="placeholder"
    />
  </div>
</template>

<style scoped>
.tool-search-input {
  position: relative;
  flex: 1;
}

.tool-search-input__icon {
  position: absolute;
  top: 50%;
  left: 0.9rem;
  transform: translateY(-50%);
  display: inline-flex;
  color: var(--text-mention-grey);
}

.tool-search-input__field {
  width: 100%;
  padding: 0.7rem 1rem 0.7rem 2.6rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 999px;
  background: var(--background-alt-grey);
  font: inherit;
}

.tool-search-input__field:focus {
  outline: 2px solid #6a5cff;
  outline-offset: 1px;
}
</style>
