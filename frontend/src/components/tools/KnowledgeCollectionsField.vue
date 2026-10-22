<script setup lang="ts">
import { computed, onMounted, ref, toRef, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import CollectionPickerModal from "@/components/tools/CollectionPickerModal.vue";
import { useAnalyseKnowledge } from "@/composables/useAnalyseKnowledge";
import { COLLECTION_STATUS_LABELS } from "@/types/knowledge";
import type { CollectionRef } from "@/types/knowledge";

const props = defineProps<{ analyseId: string }>();

const { collections, versions, refs, error, load, save, restore } = useAnalyseKnowledge(toRef(props, "analyseId"));
const isPickerOpened = ref(false);
const pickerError = ref("");

onMounted(load);
watch(() => props.analyseId, load);

async function onSave(chosen: CollectionRef[]) {
  pickerError.value = "";
  if (await save(chosen)) isPickerOpened.value = false;
  else pickerError.value = error.value;
}

// Une collection devenue indisponible est signalée ; la personne la retire quand elle veut.
const remove = (ref: CollectionRef) =>
  save(refs.value.filter((r) => r.sourceId !== ref.sourceId || r.collectionId !== ref.collectionId));

const nameOf = (content: { name: string }[]) =>
  content.length > 0 ? content.map((item) => item.name).join(", ") : "(aucune collection)";

const hasUnavailable = computed(() => collections.value.some((c) => c.status !== "available"));
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
      <DsfrButton
        label="Choisir les collections"
        icon="ri-folder-add-line"
        secondary
        size="sm"
        @click="(pickerError = ''), (isPickerOpened = true)"
      />
    </header>

    <DsfrAlert v-if="error && !isPickerOpened" type="error" small :description="error" />
    <p v-if="collections.length === 0" class="knowledge-field__empty">
      Aucune collection : l'outil « Base de connaissances » n'a rien à interroger pour cette analyse.
    </p>
    <ul v-else class="knowledge-field__chips">
      <li
        v-for="item in collections"
        :key="`${item.sourceId}:${item.collectionId}`"
        class="knowledge-field__chip"
        :class="{ 'knowledge-field__chip--off': item.status !== 'available' }"
      >
        <span>{{ item.name }}</span>
        <span v-if="item.status !== 'available'" class="knowledge-field__status">
          {{ COLLECTION_STATUS_LABELS[item.status] }}
        </span>
        <button
          type="button"
          class="knowledge-field__remove"
          :aria-label="`Retirer « ${item.name} »`"
          @click="remove(item)"
        >
          <VIcon name="ri-close-line" scale="0.8" />
        </button>
      </li>
    </ul>
    <p v-if="hasUnavailable" class="knowledge-field__hint">
      Une collection signalée n'est plus consultable par vous : elle reste enregistrée tant que vous ne la retirez pas.
    </p>

    <VersionHistory :versions="versions" :format-content="nameOf" @restore="restore" />
    <CollectionPickerModal v-model:opened="isPickerOpened" :chosen="refs" :error="pickerError" @save="onSave" />
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
.knowledge-field__intro,
.knowledge-field__hint {
  margin: 0;
}

.knowledge-field__intro,
.knowledge-field__hint {
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
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.5rem 0.25rem 0.75rem;
  border-radius: 999px;
  background: #6a5cff14;
  color: #4b3fd9;
  font-size: 0.8125rem;
  font-weight: 500;
}

.knowledge-field__chip--off {
  background: #b340001a;
  color: #b34000;
}

.knowledge-field__status {
  font-weight: 400;
}

.knowledge-field__remove {
  display: inline-flex;
  padding: 0.125rem;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.knowledge-field__remove:focus-visible {
  outline: 2px solid #6a5cff;
  outline-offset: 2px;
}
</style>
