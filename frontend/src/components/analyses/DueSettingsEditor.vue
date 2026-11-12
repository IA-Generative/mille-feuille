<script setup lang="ts">
import { computed, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import type { DueSettings, Version } from "@/types/analyse";

// Échéance des dossiers d'une analyse (#172) : durée par défaut et couleur selon le temps restant. Versionné avec
// historique et restauration, comme les autres champs d'une analyse. Le composant ne fait aucun appel : il émet
// `save` / `restore` et le parent enregistre.
const props = defineProps<{ settings: DueSettings; versions: Version<DueSettings>[]; saving?: boolean }>();
const emit = defineEmits<{ save: [settings: DueSettings]; restore: [versionId: string] }>();

const MAX_STEPS = 5;

interface StepRow {
  key: string;
  days: number | string;
  color: string;
}

let keySeq = 0;
const toState = (s: DueSettings) => ({
  defaultDueDays: s.defaultDueDays === null ? "" : String(s.defaultDueDays),
  farColor: s.thresholds.farColor,
  overdueColor: s.thresholds.overdueColor,
  steps: s.thresholds.steps.map((step): StepRow => ({ key: `s-${keySeq++}`, days: step.days, color: step.color })),
});

const initial = toState(props.settings);
const defaultDueDays = ref<string>(initial.defaultDueDays);
const farColor = ref(initial.farColor);
const overdueColor = ref(initial.overdueColor);
const steps = ref<StepRow[]>(initial.steps);

watch(
  () => props.settings,
  (settings) => {
    const state = toState(settings);
    defaultDueDays.value = state.defaultDueDays;
    farColor.value = state.farColor;
    overdueColor.value = state.overdueColor;
    steps.value = state.steps;
  },
);

const parsedDays = computed(() => {
  const raw = String(defaultDueDays.value).trim();
  return raw === "" ? null : Number(raw);
});

/** Seuils triés du plus large au plus serré, comme le serveur les range. */
const sortedSteps = computed(() => [...steps.value].sort((a, b) => Number(b.days) - Number(a.days)));

const current = computed<DueSettings>(() => ({
  defaultDueDays: parsedDays.value,
  thresholds: {
    farColor: farColor.value,
    steps: sortedSteps.value.map((s) => ({ days: Number(s.days), color: s.color })),
    overdueColor: overdueColor.value,
  },
}));

const signature = (s: DueSettings) =>
  JSON.stringify([
    s.defaultDueDays,
    s.thresholds.farColor.toLowerCase(),
    s.thresholds.steps.map((x) => [x.days, x.color.toLowerCase()]),
    s.thresholds.overdueColor.toLowerCase(),
  ]);

const isDirty = computed(() => signature(current.value) !== signature(props.settings));

const errors = computed(() => {
  const list: string[] = [];
  const days = parsedDays.value;
  if (days !== null && (!Number.isInteger(days) || days < 1 || days > 3650)) {
    list.push("La durée par défaut est un nombre entier de jours, entre 1 et 3 650.");
  }
  const values = steps.value.map((s) => Number(s.days));
  if (values.some((d) => !Number.isInteger(d) || d < 1 || d > 3650)) {
    list.push("Chaque seuil est un nombre entier de jours, entre 1 et 3 650.");
  } else if (new Set(values).size !== values.length) {
    list.push("Deux seuils ne peuvent pas avoir le même nombre de jours.");
  }
  return list;
});

function addStep() {
  steps.value.push({ key: `s-${keySeq++}`, days: "", color: "#b34000" });
}

function removeStep(key: string) {
  steps.value = steps.value.filter((s) => s.key !== key);
}

function save() {
  if (errors.value.length || !isDirty.value) return;
  emit("save", current.value);
}

/** Lignes de l'aperçu : ce que verra l'instructeur, de loin à dépassée. */
const preview = computed(() => {
  const rows: { label: string; color: string }[] = [];
  const list = current.value.thresholds.steps;
  rows.push({
    label: list.length ? `Plus de ${list[0].days} jours restants` : "Échéance à venir",
    color: farColor.value,
  });
  list.forEach((s, i) => {
    const wider = i === 0 ? null : list[i - 1].days;
    rows.push({ label: wider === null ? `${s.days} jours restants ou moins` : `${s.days} jours restants ou moins (moins de ${wider})`, color: s.color });
  });
  rows.push({ label: "Échéance dépassée", color: overdueColor.value });
  return rows;
});

function formatVersion(s: DueSettings) {
  const duration = s.defaultDueDays === null ? "pas d'échéance automatique" : `échéance à ${s.defaultDueDays} j`;
  const steps = s.thresholds.steps.map((x) => `${x.days} j`).join(", ");
  return `${duration} · seuils : ${steps || "aucun"}`;
}
</script>

<template>
  <div class="dse">
    <h4 class="fr-h6 dse__title">Échéance des dossiers</h4>
    <p class="fr-text--sm dse__intro">
      Un dossier peut avoir une date d'échéance, affichée avec une couleur selon le temps restant. Le libellé
      (« échéance dans 5 j ») est toujours écrit : la couleur n'est jamais le seul signal.
    </p>

    <div class="dse__duration">
      <label class="fr-label" for="due-default-days">
        Durée par défaut
        <span class="fr-hint-text">En jours depuis la création du dossier. Vide : pas d'échéance automatique.</span>
      </label>
      <input id="due-default-days" v-model="defaultDueDays" type="number" min="1" max="3650" class="fr-input dse__days" />
    </div>

    <div class="dse__colors">
      <label class="dse__color-row">
        <input v-model="farColor" type="color" />
        <span>Échéance loin</span>
      </label>

      <ul class="dse__steps">
        <li v-for="step in steps" :key="step.key" class="dse__step">
          <input v-model="step.color" type="color" :aria-label="`Couleur du seuil de ${step.days || '…'} jours`" />
          <span>À</span>
          <input v-model="step.days" type="number" min="1" max="3650" class="fr-input dse__step-days" aria-label="Nombre de jours restants" />
          <span>jours restants ou moins</span>
          <button type="button" class="dse__icon-btn" :aria-label="`Supprimer le seuil de ${step.days || '…'} jours`" @click="removeStep(step.key)">
            <VIcon name="ri-delete-bin-line" />
          </button>
        </li>
      </ul>

      <label class="dse__color-row">
        <input v-model="overdueColor" type="color" />
        <span>Échéance dépassée</span>
      </label>
    </div>

    <ul class="dse__preview" aria-label="Aperçu des niveaux d'échéance">
      <li v-for="row in preview" :key="row.label">
        <span class="dse__dot" :style="{ background: row.color }" aria-hidden="true" />
        {{ row.label }}
      </li>
    </ul>

    <DsfrAlert v-if="errors.length" alert type="error" small class="fr-my-2w">
      <ul class="fr-my-0 fr-pl-2w">
        <li v-for="e in errors" :key="e">{{ e }}</li>
      </ul>
    </DsfrAlert>

    <div class="dse__actions">
      <DsfrButton label="Ajouter un seuil" tertiary icon="ri-add-line" size="sm" :disabled="steps.length >= MAX_STEPS" @click="addStep" />
      <DsfrButton label="Enregistrer" size="sm" :disabled="!isDirty || errors.length > 0 || saving" @click="save" />
    </div>

    <VersionHistory :versions="versions" :format-content="formatVersion" @restore="emit('restore', $event)" />
  </div>
</template>

<style scoped>
.dse {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.dse__title,
.dse__intro {
  margin: 0;
}

.dse__days {
  max-width: 10rem;
}

.dse__colors {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
}

.dse__color-row,
.dse__step {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.dse__colors input[type="color"] {
  width: 2.25rem;
  height: 2.25rem;
  padding: 0;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.375rem;
  background: none;
  cursor: pointer;
}

.dse__steps {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.dse__step-days {
  width: 6rem;
}

.dse__icon-btn {
  display: flex;
  padding: 0.125rem;
  border: none;
  background: none;
  color: var(--text-default-error);
  font-size: 1.125rem;
  cursor: pointer;
}

.dse__preview {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 0.875rem;
}

.dse__dot {
  display: inline-block;
  width: 0.625rem;
  height: 0.625rem;
  margin-right: 0.375rem;
  border-radius: 50%;
}

.dse__actions {
  display: flex;
  gap: 0.75rem;
}
</style>
