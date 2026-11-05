<script setup lang="ts">
import type { LlmCapability } from "@/types/llmModel";

defineProps<{ capabilities: LlmCapability[] }>();
const emit = defineEmits<{ add: []; edit: [capability: LlmCapability] }>();
</script>

<template>
  <section class="capabilities" aria-labelledby="capabilities-title">
    <div class="capabilities__header">
      <div>
        <h3 id="capabilities-title" class="capabilities__title">Capacités</h3>
        <p class="capabilities__note">
          Vous les définissez : un nom et ce que le modèle est capable de faire. En mode auto, elles servent à choisir
          le modèle.
        </p>
      </div>
      <DsfrButton label="Nouvelle capacité" icon="ri-add-line" secondary size="sm" @click="emit('add')" />
    </div>

    <p v-if="!capabilities.length" class="capabilities__note">Aucune capacité définie.</p>
    <ul v-else class="capabilities__card">
      <li v-for="capability in capabilities" :key="capability.id" class="capabilities__item">
        <div>
          <strong>{{ capability.name }}</strong>
          <p class="capabilities__description">{{ capability.description }}</p>
        </div>
        <button
          type="button"
          class="capabilities__edit"
          :aria-label="`Modifier ${capability.name}`"
          @click="emit('edit', capability)"
        >
          <VIcon name="ri-pencil-line" />
        </button>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.capabilities {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.capabilities__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.capabilities__title {
  margin: 0;
  font-size: 1rem;
}

.capabilities__note,
.capabilities__description {
  margin: 0.125rem 0 0;
  font-size: 0.8125rem;
  color: var(--text-mention-grey, #666);
}

.capabilities__card {
  margin: 0;
  padding: 0;
  list-style: none;
  border: 1px solid var(--border-default-grey, #ddd);
  border-radius: 0.875rem;
  background: var(--background-default-grey, #fff);
}

.capabilities__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 1rem;
}

.capabilities__item + .capabilities__item {
  border-top: 1px solid var(--border-default-grey, #eee);
}

.capabilities__edit {
  border: 0;
  background: none;
  cursor: pointer;
  color: var(--text-mention-grey, #666);
  padding: 0.125rem;
}
</style>
