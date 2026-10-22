<script setup lang="ts">
import type { KnowledgeCollection } from "@/types/knowledge";

defineProps<{ collection: KnowledgeCollection; checked: boolean }>();
const emit = defineEmits<{ toggle: [] }>();
</script>

<template>
  <li class="collection-row">
    <label class="collection-row__main">
      <input type="checkbox" class="collection-row__box" :checked="checked" @change="emit('toggle')" />
      <img
        v-if="collection.previewUrl"
        class="collection-row__preview"
        :src="collection.previewUrl"
        alt=""
        loading="lazy"
        referrerpolicy="no-referrer"
      />
      <span v-else class="collection-row__preview collection-row__preview--none"><VIcon name="ri-book-2-line" /></span>
      <span class="collection-row__text">
        <span class="collection-row__name">{{ collection.name }}</span>
        <span v-if="collection.description" class="collection-row__description">{{ collection.description }}</span>
      </span>
    </label>
    <span class="collection-row__side">
      <a
        v-if="collection.url"
        class="collection-row__link"
        :href="collection.url"
        target="_blank"
        rel="noopener noreferrer"
        :title="`Ouvrir « ${collection.name} » chez le fournisseur`"
      >
        Ouvrir
      </a>
      <span class="collection-row__count">{{ collection.documentCount.toLocaleString("fr-FR") }} documents</span>
    </span>
  </li>
</template>

<style scoped>
.collection-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
}

.collection-row__main {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.collection-row__box {
  flex-shrink: 0;
  width: 1rem;
  height: 1rem;
}

.collection-row__preview {
  width: 3rem;
  height: 3rem;
  flex-shrink: 0;
  border-radius: 0.5rem;
  object-fit: cover;
  background: var(--background-alt-grey);
}

.collection-row__preview--none {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-mention-grey);
}

.collection-row__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.collection-row__name {
  font-weight: 600;
}

.collection-row__description {
  color: var(--text-mention-grey);
  font-size: 0.8125rem;
}

.collection-row__side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.125rem;
  flex-shrink: 0;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
  white-space: nowrap;
}

.collection-row__link {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  color: var(--text-action-high-blue-france);
  background-image: none;
}
</style>
