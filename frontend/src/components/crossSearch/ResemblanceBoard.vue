<script setup lang="ts">
/** « Rapprochements » : ce que le calcul a trouvé, un thème de ressemblance à la fois. */
import { computed, onMounted, ref, watch } from "vue";

import ClusterGraph from "@/components/crossSearch/ClusterGraph.vue";
import ClusterSummary from "@/components/crossSearch/ClusterSummary.vue";
import { themeFor } from "@/components/crossSearch/resemblanceThemes";
import RuleModal from "@/components/crossSearch/RuleModal.vue";
import RulePicker from "@/components/crossSearch/RulePicker.vue";
import { useAuth } from "@/composables/useAuth";
import { useResemblances } from "@/composables/useResemblances";
import type { Resemblance, ResemblanceRule } from "@/types/crossSearch";
import { userMessage } from "@/utils/api";

const emit = defineEmits<{ explore: [ids: string[]] }>();

// Les thèmes sont définis par les administrateurs (le serveur reste juge).
const { isAdmin } = useAuth();
const store = useResemblances();
const { rules, enabled, status, error, groups, total, groupsError } = store;

const selectedId = ref("");
const groupId = ref<string | null>(null);
const showDismissed = ref(false);
const actionError = ref("");
const selected = computed(() => rules.value.find((r) => r.id === selectedId.value) ?? rules.value[0]);
const theme = computed(() => selected.value && themeFor(selected.value));
const pickable = computed(() =>
  rules.value.map((rule) => ({ ...themeFor(rule), scope: rule.scope, active: rule.active, count: rule.groupCount })),
);
const dossiers = computed(() => groups.value.flatMap((g) => g.dossiers));
const dossierNames = computed(() => Object.fromEntries(dossiers.value.map((d) => [d.id, d.name])));
const dossierThemes = computed(() => Object.fromEntries(dossiers.value.map((d) => [d.id, d.themeName])));
const computedAt = computed(() =>
  selected.value?.computedAt
    ? new Date(selected.value.computedAt).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" })
    : null,
);

function reload() {
  groupId.value = null;
  actionError.value = "";
  return store.loadGroups(selected.value?.id ?? "", showDismissed.value);
}
watch([() => selected.value?.id, showDismissed], reload);
onMounted(store.load);

async function toggleDismissed(group: Resemblance) {
  try {
    await store.setDismissed(group, !group.dismissed);
    await Promise.all([store.load(), reload()]);
  } catch (failure) {
    actionError.value = userMessage(failure, "L'action a échoué.");
  }
}

const isModalOpened = ref(false);
const editedRule = ref<ResemblanceRule | null>(null);
function openModal(rule: ResemblanceRule | null) {
  editedRule.value = rule;
  isModalOpened.value = true;
}
function onSaved(id: string) {
  selectedId.value = id;
  reload();
}
</script>

<template>
  <p v-if="status === 'loading'" class="fr-text--sm" role="status">Chargement des thèmes…</p>
  <div v-else-if="status === 'error'" class="fr-alert fr-alert--error fr-alert--sm" role="alert">
    <p>{{ error }}</p>
    <DsfrButton label="Réessayer" size="sm" secondary @click="store.load" />
  </div>
  <template v-else>
    <div v-if="!enabled" class="fr-alert fr-alert--info fr-alert--sm fr-mb-2w" role="note">
      <p>Le calcul des rapprochements n'est pas activé : les thèmes peuvent être définis, aucun groupe n'est produit.</p>
    </div>
    <div class="board__header">
      <p class="fr-text--sm fr-mb-0">
        Parmi les dossiers auxquels vous avez accès.
        <template v-if="computedAt">Dernier calcul : {{ computedAt }}.</template>
      </p>
      <div v-if="isAdmin" class="board__admin">
        <DsfrButton v-if="selected" label="Modifier ce thème" size="sm" tertiary icon="ri-edit-line" @click="openModal(selected)" />
        <DsfrButton label="Nouveau thème" size="sm" secondary icon="ri-add-line" @click="openModal(null)" />
      </div>
    </div>

    <p v-if="!selected" class="fr-text--sm">Aucun thème de ressemblance n'est défini.</p>
    <template v-else>
      <RulePicker :model-value="selected.id" :rules="pickable" class="fr-mb-2w" @update:model-value="selectedId = $event" />
      <p v-if="isAdmin && selected.missingEntityIds.length" class="fr-text--sm fr-error-text" role="alert">
        {{ selected.missingEntityIds.length }} entité(s) citée(s) par ce thème ne sont plus définies dans les analyses.
      </p>
      <div class="fr-checkbox-group fr-checkbox-group--sm fr-mb-2w">
        <input id="show-dismissed" v-model="showDismissed" type="checkbox" />
        <label class="fr-label" for="show-dismissed">Voir les rapprochements écartés</label>
      </div>
      <p v-if="actionError || groupsError" class="fr-error-text" role="alert">{{ actionError || groupsError }}</p>

      <div class="board__columns">
        <div class="board__card">
          <ClusterGraph :key="selected.id" :theme="theme!" :groups="groups" :dossier-names="dossierNames" :group-id="groupId" @group="groupId = $event" />
        </div>
        <div class="board__side">
          <ClusterSummary
            :theme="theme!"
            :groups="groups"
            :dossier-themes="dossierThemes"
            :group-id="groupId"
            @group="groupId = $event"
            @explore="emit('explore', $event)"
            @dismiss="toggleDismissed"
          />
          <DsfrButton v-if="groups.length < total" label="Voir plus de groupes" size="sm" tertiary class="fr-mt-1w" @click="store.loadGroups(selected.id, showDismissed, true)" />
        </div>
      </div>
    </template>

    <RuleModal v-if="isAdmin" :opened="isModalOpened" :rule="editedRule" :store="store" @close="isModalOpened = false" @saved="onSaved" />
  </template>
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
