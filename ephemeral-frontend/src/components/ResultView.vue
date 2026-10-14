<script setup lang="ts">
import { computed } from "vue";

import type { ClassificationOut, ExtractionOut, RunOut } from "@/types";

const props = defineProps<{ result: RunOut; mode: "classification" | "extraction" }>();

const SOURCES: Record<string, string> = { textual: "Texte", visual: "Visuel", gliner: "GLiNER" };
const percent = (c: number | null) => (c == null ? "" : `${Math.round(c * 100)} %`);

const classification = computed(() => (props.mode === "classification" ? (props.result as ClassificationOut) : null));
const extraction = computed(() => (props.mode === "extraction" ? (props.result as ExtractionOut) : null));
</script>

<template>
  <div v-for="doc in result.documents" :key="doc.name" class="fr-mb-3w">
    <h3 class="fr-h6">{{ doc.name }}</h3>
    <ul class="pages">
      <li v-for="page in doc.pages" :key="page.page_number" class="page">
        <span class="num">Page {{ page.page_number }}</span>
        <div class="tags">
          <template v-if="classification">
            <p
              v-for="(label, i) in (page as ClassificationOut['documents'][0]['pages'][0]).labels"
              :key="i"
              class="fr-tag"
              :title="`Source : ${SOURCES[label.source]}`"
            >
              {{ label.name }} <small class="conf">{{ percent(label.confidence) }}</small>
              <small class="src">{{ SOURCES[label.source] }}</small>
            </p>
            <span v-if="!(page as ClassificationOut['documents'][0]['pages'][0]).labels.length" class="fr-text--sm muted">—</span>
          </template>
          <template v-else-if="extraction">
            <div
              v-for="(entity, i) in (page as ExtractionOut['documents'][0]['pages'][0]).entities"
              :key="i"
              class="entity"
            >
              <span class="fr-text--sm muted">{{ entity.name }}</span>
              <strong>{{ entity.value }}</strong>
              <small class="conf">{{ percent(entity.confidence) }} · {{ SOURCES[entity.source] }}</small>
            </div>
            <span v-if="!(page as ExtractionOut['documents'][0]['pages'][0]).entities.length" class="fr-text--sm muted">—</span>
          </template>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.pages {
  list-style: none;
  padding: 0;
  margin: 0;
}
.page {
  display: flex;
  gap: 1rem;
  padding: 0.75rem 0;
  border-top: 1px solid var(--border-default-grey);
}
.num {
  flex: 0 0 5rem;
  font-weight: 600;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: flex-start;
}
.entity {
  display: flex;
  flex-direction: column;
  padding: 0.25rem 0.75rem;
  border-radius: 0.5rem;
  background: var(--background-alt-grey);
}
.conf,
.src {
  margin-left: 0.5rem;
  opacity: 0.7;
}
.muted {
  color: var(--text-mention-grey);
}
</style>
