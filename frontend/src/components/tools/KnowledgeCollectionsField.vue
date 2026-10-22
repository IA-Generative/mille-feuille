<script setup lang="ts">
import { ref } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import CollectionPickerModal from "@/components/tools/CollectionPickerModal.vue";
import { useKnowledgeCollections } from "@/composables/useKnowledgeCollections";

const { selected, versions, restore, nameOf } = useKnowledgeCollections();
const isPickerOpened = ref(false);
</script>

<template>
  <section class="knowledge-field">
    <header class="knowledge-field__header">
      <span class="knowledge-field__icon"><VIcon name="ri-book-2-line" /></span>
      <div class="knowledge-field__text">
        <h3 class="fr-h6 knowledge-field__title">Base de connaissances</h3>
        <p class="knowledge-field__intro">
          Les collections que les agents et le chat de cette analyse peuvent interroger avec l'outil « Base de connaissances ».
        </p>
      </div>
      <DsfrButton label="Choisir les collections" icon="ri-folder-add-line" secondary size="sm" @click="isPickerOpened = true" />
    </header>

    <p v-if="selected.length === 0" class="knowledge-field__empty">
      Aucune collection : l'outil « Base de connaissances » n'a rien à interroger pour cette analyse.
    </p>
    <ul v-else class="knowledge-field__chips">
      <li v-for="item in selected" :key="item.id" class="knowledge-field__chip">
        {{ item.name }} <span class="knowledge-field__count">{{ item.documentCount.toLocaleString("fr-FR") }}</span>
      </li>
    </ul>

    <VersionHistory :versions="versions" :format-content="nameOf" @restore="restore" />
    <CollectionPickerModal v-model:opened="isPickerOpened" />
  </section>
</template>

<style scoped>
.knowledge-field {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.5rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 1rem;
  background: var(--background-default-grey);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.knowledge-field__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.knowledge-field__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.75rem;
  background: linear-gradient(135deg, #6a5cff1a 0%, #ff6ca01a 100%);
  color: #4b3fd9;
  flex-shrink: 0;
}

.knowledge-field__text {
  flex: 1;
}

.knowledge-field__title,
.knowledge-field__intro {
  margin: 0;
}

.knowledge-field__intro {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.knowledge-field__empty {
  margin: 0;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}

.knowledge-field__chips {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.knowledge-field__chip {
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  background: #6a5cff14;
  color: #4b3fd9;
  font-size: 0.8125rem;
  font-weight: 500;
}

.knowledge-field__count {
  margin-left: 0.25rem;
  color: var(--text-mention-grey);
  font-weight: 400;
}
</style>
