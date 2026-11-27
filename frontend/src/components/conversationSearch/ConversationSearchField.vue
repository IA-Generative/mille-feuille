<script setup lang="ts">
const query = defineModel<string>({ required: true });
</script>

<template>
  <div class="conversation-search" role="search">
    <VIcon name="ri-search-line" class="conversation-search__icon" aria-hidden="true" />
    <input
      id="conversation-search"
      v-model="query"
      type="search"
      class="conversation-search__input"
      placeholder="Rechercher"
      aria-label="Rechercher dans mes conversations"
      autocomplete="off"
      maxlength="200"
      @keydown.esc.prevent="query = ''"
    />
  </div>
</template>

<style scoped>
.conversation-search {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
  margin-bottom: 0.75rem;
  padding: 0 0.75rem;
  border-radius: 0.625rem;
  background: var(--background-contrast-grey);
}

.conversation-search:focus-within {
  outline: 2px solid #0a76f6;
  outline-offset: 1px;
}

.conversation-search__icon {
  flex-shrink: 0;
  color: var(--text-mention-grey);
}

.conversation-search__input {
  flex: 1;
  min-width: 0;
  padding: 0.5rem 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-default-grey);
  font-family: inherit;
  font-size: 0.875rem;
}
</style>
