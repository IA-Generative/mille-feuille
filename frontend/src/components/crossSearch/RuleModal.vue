<script setup lang="ts">
/** Définir un thème de ressemblance (administrateurs), avec son historique. `rule` null : création. */
import { computed, reactive, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import AppModal from "@/components/AppModal.vue";
import CriteriaEditor from "@/components/crossSearch/CriteriaEditor.vue";
import { draftOf, fetchEntities, type useResemblances } from "@/composables/useResemblances";
import {
  CERTAINTIES,
  SCOPES,
  type CatalogEntity,
  type ResemblanceRule,
  type RuleCriterion,
  type RuleDraft,
} from "@/types/crossSearch";
import { userMessage } from "@/utils/api";

const props = defineProps<{ opened: boolean; rule: ResemblanceRule | null; store: ReturnType<typeof useResemblances> }>();
const emit = defineEmits<{ close: []; saved: [id: string] }>();

const empty = (): RuleDraft => ({ name: "", description: "", criteria: [], scope: "all", certainty: "to_check", active: true });
const draft = reactive<RuleDraft>(empty());
const entities = ref<CatalogEntity[]>([]);
const error = ref("");
const busy = ref(false);
const current = computed(() => props.store.rules.value.find((r) => r.id === props.rule?.id) ?? null);

function fill(rule: RuleDraft | null) {
  Object.assign(draft, draftOf(rule ?? empty()));
  error.value = "";
}

watch(
  () => props.opened,
  async (isOpened) => {
    if (!isOpened) return;
    fill(props.rule);
    try {
      entities.value = await fetchEntities();
    } catch (failure) {
      error.value = userMessage(failure, "Les entités des analyses n'ont pas pu être chargées.");
    }
  },
  { immediate: true },
);

/** Un seul enregistrement à la fois ; l'erreur du serveur reste dans la fenêtre. */
async function attempt(action: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await action();
  } catch (failure) {
    error.value = userMessage(failure, "L'enregistrement a échoué.");
  } finally {
    busy.value = false;
  }
}

function submit() {
  if (!draft.name.trim() || !draft.criteria.length) {
    error.value = "Donnez un nom et au moins un critère.";
    return;
  }
  return attempt(async () => {
    emit("saved", await props.store.saveRule(draft, current.value?.id));
    emit("close");
  });
}

const restore = (versionId: string) =>
  attempt(async () => {
    if (!current.value) return;
    const id = current.value.id;
    await props.store.restoreRule(id, versionId);
    fill(current.value);
    emit("saved", id);
  });

function remove() {
  const rule = current.value;
  if (!rule || !confirm(`Supprimer le thème « ${rule.name} » et son historique ? Les dossiers sont conservés.`)) return;
  return attempt(async () => {
    await props.store.removeRule(rule.id);
    emit("close");
  });
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

    <CriteriaEditor v-model="draft.criteria" :entities="entities" />

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
