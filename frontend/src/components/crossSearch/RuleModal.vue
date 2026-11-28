<script setup lang="ts">
/** Définir un thème de ressemblance (administrateurs), avec son historique. `rule` null : création. */
import { computed, reactive, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import AppModal from "@/components/AppModal.vue";
import CriteriaEditor from "@/components/crossSearch/CriteriaEditor.vue";
import { draftOf, useResemblances } from "@/composables/useResemblances";
import {
  CERTAINTIES,
  SCOPES,
  type ResemblanceRule,
  type RuleCriterion,
  type RuleDraft,
} from "@/types/crossSearch";

const props = defineProps<{ opened: boolean; rule: ResemblanceRule | null }>();
const emit = defineEmits<{ close: []; saved: [id: string] }>();

const { rules, saveRule, restoreRule, removeRule } = useResemblances();

const empty = (): RuleDraft => ({ name: "", description: "", criteria: [], scope: "all", certainty: "to_check", active: true });
const draft = reactive<RuleDraft>(empty());
const error = ref("");
const current = computed(() => rules.value.find((r) => r.id === props.rule?.id) ?? null);

function fill(rule: RuleDraft | null) {
  Object.assign(draft, draftOf(rule ?? empty()));
  error.value = "";
}

watch(
  () => props.opened,
  (isOpened) => isOpened && fill(props.rule),
);

function submit() {
  if (!draft.name.trim() || !draft.criteria.length) {
    error.value = "Donnez un nom et au moins un critère.";
    return;
  }
  emit("saved", saveRule(draft, current.value?.id));
  emit("close");
}

function restore(versionId: string) {
  if (!current.value) return;
  restoreRule(current.value.id, versionId);
  fill(current.value);
}

function remove() {
  if (!current.value || !confirm(`Supprimer le thème « ${current.value.name} » ? Les dossiers sont conservés.`)) return;
  removeRule(current.value.id);
  emit("close");
}

// L'historique dit aussi combien d'entités sont tenues pour équivalentes.
const describeCriterion = (criterion: RuleCriterion) =>
  criterion.origin === "analysis" && criterion.entityIds.length > 1
    ? `${criterion.name} (${criterion.entityIds.length} entités)`
    : criterion.name;

const describe = (content: RuleDraft) =>
  `${content.name} · ${content.criteria.map(describeCriterion).join(" et ")} · ` +
  `${SCOPES[content.scope].label} · ${CERTAINTIES[content.certainty].label} · ${content.active ? "actif" : "désactivé"}`;
</script>

<template>
  <AppModal
    :opened="opened"
    :title="rule ? 'Modifier le thème de ressemblance' : 'Nouveau thème de ressemblance'"
    :actions="[
      { label: 'Annuler', secondary: true, onClick: () => emit('close') },
      { label: 'Enregistrer', onClick: submit },
    ]"
    @close="emit('close')"
  >
    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
    <DsfrInput v-model="draft.name" label="Nom" label-visible required />
    <div class="fr-mt-2w">
      <DsfrInput v-model="draft.description" label="Description" label-visible is-textarea hint="Affichée aux instructeurs avec les rapprochements." />
    </div>

    <CriteriaEditor v-model="draft.criteria" />

    <label class="fr-label" for="rule-draft-scope">Portée</label>
    <select id="rule-draft-scope" v-model="draft.scope" class="fr-select fr-mb-2w">
      <option v-for="(entry, value) in SCOPES" :key="value" :value="value">{{ entry.label }}</option>
    </select>

    <label class="fr-label" for="rule-draft-certainty">Certitude annoncée</label>
    <select id="rule-draft-certainty" v-model="draft.certainty" class="fr-select fr-mb-2w">
      <option v-for="(entry, value) in CERTAINTIES" :key="value" :value="value">{{ entry.label }}</option>
    </select>

    <div class="fr-checkbox-group">
      <input id="rule-draft-active" v-model="draft.active" type="checkbox" />
      <label class="fr-label" for="rule-draft-active">Thème actif</label>
    </div>

    <template v-if="current">
      <VersionHistory :versions="current.versions" :format-content="describe" @restore="restore" />
      <button type="button" class="fr-btn fr-btn--tertiary fr-btn--sm fr-mt-2w" @click="remove">Supprimer ce thème</button>
    </template>
  </AppModal>
</template>
