<script setup lang="ts">
/** « Rapprochements » : ce que l'analyse préalable a trouvé, un thème de ressemblance à la fois. */
import { computed, ref, watch } from "vue";

import ClusterGraph from "@/components/crossSearch/ClusterGraph.vue";
import ClusterSummary from "@/components/crossSearch/ClusterSummary.vue";
import { themeFor } from "@/components/crossSearch/resemblanceThemes";
import RuleModal from "@/components/crossSearch/RuleModal.vue";
import RulePicker from "@/components/crossSearch/RulePicker.vue";
import { useAuth } from "@/composables/useAuth";
import { mockDossiersByIds } from "@/composables/useCrossSearch";
import { mockResemblances, useResemblances } from "@/composables/useResemblances";
import type { ResemblanceRule } from "@/types/crossSearch";

const emit = defineEmits<{ explore: [ids: string[]] }>();

// Les thèmes sont définis par les administrateurs (le backend restera juge).
const { isAdmin } = useAuth();
const { rules } = useResemblances();

/** Un thème désactivé n'est montré qu'à qui peut le réactiver. */
const found = computed(() =>
  rules.value
    .filter((rule) => rule.active || isAdmin.value)
    .map((rule) => ({ rule, theme: themeFor(rule), groups: rule.active ? mockResemblances(rule) : [] })),
);
const pickable = computed(() =>
  found.value.map(({ rule, theme, groups }) => ({ ...theme, scope: rule.scope, active: rule.active, count: groups.length })),
);

const selectedId = ref(rules.value[0]?.id ?? "");
const groupId = ref<string | null>(null);
watch(selectedId, () => (groupId.value = null));
const selected = computed(() => found.value.find((entry) => entry.rule.id === selectedId.value) ?? found.value[0]);

const dossiers = computed(() => mockDossiersByIds([...new Set(selected.value?.groups.flatMap((g) => g.dossierIds))]));
const dossierNames = computed(() => Object.fromEntries(dossiers.value.map((d) => [d.id, d.name])));
const dossierThemes = computed(() => Object.fromEntries(dossiers.value.map((d) => [d.id, d.themeName])));

const isModalOpened = ref(false);
const editedRule = ref<ResemblanceRule | null>(null);
function openModal(rule: ResemblanceRule | null) {
  editedRule.value = rule;
  isModalOpened.value = true;
}
</script>

<template>
  <div class="board__header">
    <p class="fr-text--sm fr-mb-0">Analyse préalable des dossiers auxquels vous avez accès. Dernier passage : ce matin (fictif).</p>
    <div v-if="isAdmin" class="board__admin">
      <DsfrButton v-if="selected" label="Modifier ce thème" size="sm" tertiary icon="ri-edit-line" @click="openModal(selected.rule)" />
      <DsfrButton label="Nouveau thème" size="sm" secondary icon="ri-add-line" @click="openModal(null)" />
    </div>
  </div>

  <RulePicker v-model="selectedId" :rules="pickable" class="fr-mb-2w" />

  <div v-if="selected" class="board__columns">
    <div class="board__card">
      <ClusterGraph :key="selected.rule.id" :theme="selected.theme" :groups="selected.groups" :dossier-names="dossierNames" :group-id="groupId" @group="groupId = $event" />
    </div>
    <div class="board__side">
      <ClusterSummary :theme="selected.theme" :groups="selected.groups" :dossier-themes="dossierThemes" :group-id="groupId" @group="groupId = $event" @explore="emit('explore', $event)" />
    </div>
  </div>

  <RuleModal v-if="isAdmin" :opened="isModalOpened" :rule="editedRule" @close="isModalOpened = false" @saved="selectedId = $event" />
</template>

<style scoped>
.board__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.board__admin {
  display: flex;
  gap: 0.5rem;
}

.board__columns {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(16rem, 1fr);
  gap: 1rem;
  align-items: start;
}

.board__card {
  overflow: hidden;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
}

.board__side {
  max-height: 38rem;
  overflow-y: auto;
}

@media (max-width: 62em) {
  .board__columns {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
