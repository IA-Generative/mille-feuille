<script setup lang="ts">
/** Choisir le thème de ressemblance affiché. Ils peuvent être nombreux : recherche, portée et liste à défilement. */
import { computed, ref } from "vue";

import type { ResemblanceTheme } from "@/components/crossSearch/resemblanceThemes";
import { SCOPES, type Scope } from "@/types/crossSearch";

export type PickableRule = ResemblanceTheme & { scope: Scope; active: boolean; count: number };

const props = defineProps<{ rules: PickableRule[]; modelValue: string }>();
const emit = defineEmits<{ "update:modelValue": [id: string] }>();

const query = ref("");
const scope = ref<Scope | "">("");
const shown = computed(() => {
  const needle = query.value.trim().toLowerCase();
  return props.rules.filter(
    (rule) => rule.label.toLowerCase().includes(needle) && (!scope.value || rule.scope === scope.value),
  );
});
</script>

<template>
  <div class="picker">
    <div class="picker__filters">
      <div>
        <label class="fr-label fr-sr-only" for="rule-search">Chercher un thème de ressemblance</label>
        <input id="rule-search" v-model="query" class="fr-input" type="search" placeholder="Chercher un thème de ressemblance" />
      </div>
      <div>
        <label class="fr-label fr-sr-only" for="rule-scope">Portée</label>
        <select id="rule-scope" v-model="scope" class="fr-select">
          <option value="">Toutes les portées</option>
          <option v-for="(entry, value) in SCOPES" :key="value" :value="value">{{ entry.label }}</option>
        </select>
      </div>
    </div>

    <p v-if="!shown.length" class="fr-text--sm fr-mb-0">Aucun thème ne correspond.</p>
    <ul v-else class="picker__list">
      <li v-for="rule in shown" :key="rule.value">
        <button type="button" class="picker__rule" :class="{ 'picker__rule--off': !rule.active }" :aria-pressed="modelValue === rule.value" @click="emit('update:modelValue', rule.value)">
          <span class="picker__icon" :style="{ background: rule.color }"><img :src="rule.icon" alt="" /></span>
          <span class="picker__text">
            <span class="picker__name">{{ rule.label }}</span>
            <span class="picker__meta">{{ SCOPES[rule.scope].short }} · {{ rule.active ? `${rule.count} groupe(s)` : "désactivé" }}</span>
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.picker__filters {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.picker__list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
  gap: 0.5rem;
  max-height: 11rem;
  margin: 0;
  padding: 0.125rem;
  overflow-y: auto;
  list-style: none;
}

.picker__rule {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  text-align: left;
}

.picker__rule[aria-pressed="true"] {
  border-color: var(--border-active-blue-france);
  box-shadow: inset 0 0 0 1px var(--border-active-blue-france);
}

.picker__rule--off {
  opacity: 0.55;
}

.picker__icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 0.5rem;
}

.picker__icon img {
  width: 1rem;
  height: 1rem;
  /* Pictogramme du DSFR passé en blanc. */
  filter: brightness(0) invert(1);
}

.picker__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.picker__name {
  overflow: hidden;
  font-size: 0.875rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picker__meta {
  color: var(--text-mention-grey);
  font-size: 0.75rem;
}
</style>
