<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import GroupPicker from "@/components/access/GroupPicker.vue";
import { useDossierAccess } from "@/composables/useDossierAccess";
import {
  VISIBILITY_HINTS,
  VISIBILITY_LABELS,
  groupLabel,
  type AccessImpact,
  type DossierAccess,
  type DossierAccessState,
  type Visibility,
} from "@/types/access";
import { userMessage } from "@/utils/api";

// Accès d'un dossier : visibilité et groupes associés. Lecture pour tous ceux qui y ont accès ; modification
// réservée aux administrateurs. Le serveur applique la règle ; avant d'enregistrer, une simulation dit si la personne
// affectée perdrait l'accès (son affectation serait alors annulée).
const props = defineProps<{ dossierId: string; dossierName: string }>();
const emit = defineEmits<{ close: []; saved: [message: string] }>();

const { fetchAccess, previewAccess, saveAccess } = useDossierAccess();

const state = ref<DossierAccessState | null>(null);
const loadError = ref("");
const visibility = ref<Visibility>("restricted");
const groups = ref<string[]>([]);
const impact = ref<AccessImpact | null>(null);
const confirmed = ref(false);
const saving = ref(false);
const saveError = ref("");

const canEdit = computed(() => state.value?.canEdit ?? false);
const draft = computed<DossierAccess>(() => ({ visibility: visibility.value, groups: groups.value }));
const dirty = computed(
  () =>
    !!state.value &&
    (visibility.value !== state.value.visibility ||
      JSON.stringify([...groups.value].sort()) !== JSON.stringify([...state.value.groups].sort())),
);

const errors = computed(() => {
  const list: string[] = [];
  if (visibility.value === "restricted" && groups.value.length === 0) {
    list.push("Un dossier restreint doit avoir au moins un groupe, sinon personne (hors administrateurs) ne pourrait l'ouvrir.");
  }
  return list;
});

const needsConfirmation = computed(() => dirty.value && !!impact.value?.assigneeUnassigned);
const canSave = computed(
  () => canEdit.value && dirty.value && errors.value.length === 0 && !saving.value && (!needsConfirmation.value || confirmed.value),
);

onMounted(async () => {
  try {
    state.value = await fetchAccess(props.dossierId);
    visibility.value = state.value.visibility;
    groups.value = [...state.value.groups];
  } catch (e) {
    loadError.value = userMessage(e, "Impossible de charger l'accès du dossier.");
  }
});

// Chaque modification relance la simulation : « Cette personne perdra l'accès » reste exacte.
let previewSeq = 0;
async function refreshImpact() {
  confirmed.value = false;
  impact.value = null;
  if (!canEdit.value || !dirty.value || errors.value.length) return;
  const seq = ++previewSeq;
  try {
    const result = await previewAccess(props.dossierId, draft.value);
    if (seq === previewSeq) impact.value = result;
  } catch (e) {
    if (seq === previewSeq) saveError.value = userMessage(e, "La simulation a échoué.");
  }
}

watch([visibility, groups], refreshImpact, { deep: true });

async function save() {
  if (!canSave.value) return;
  saving.value = true;
  saveError.value = "";
  try {
    const result = await saveAccess(props.dossierId, draft.value);
    const lost = result.impact.unassignedPerson ? ` L'affectation de ${result.impact.unassignedPerson.name} est annulée.` : "";
    emit("saved", `Accès enregistré. Le changement est tracé dans l'historique du dossier.${lost}`);
    emit("close");
  } catch (e) {
    saveError.value = userMessage(e, "L'enregistrement a échoué.");
  } finally {
    saving.value = false;
  }
}

const actions = computed(() => [
  ...(canEdit.value ? [{ label: saving.value ? "Enregistrement…" : "Enregistrer", disabled: !canSave.value, onClick: save }] : []),
  { label: canEdit.value ? "Annuler" : "Fermer", secondary: canEdit.value, onClick: () => emit("close") },
]);

const dateLabel = (iso: string) => new Date(iso).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
const visibilityOptions: Visibility[] = ["restricted", "analyse"];
</script>

<template>
  <DsfrModal :opened="true" title="Accès au dossier" icon="ri-lock-line" size="lg" :actions="actions" @close="emit('close')">
    <p class="am__name">{{ dossierName }}</p>

    <DsfrAlert v-if="loadError" alert type="error" small :description="loadError" class="fr-mb-2w" />

    <template v-else-if="state">
    <p v-if="!canEdit" class="am__readonly" role="note">
      <VIcon name="ri-information-line" /> Seuls les administrateurs modifient l'accès à un dossier.
    </p>

    <fieldset class="am__group" :disabled="!canEdit">
      <legend class="am__legend">Qui peut voir ce dossier ?</legend>
      <label v-for="v in visibilityOptions" :key="v" class="am__radio">
        <input v-model="visibility" type="radio" :value="v" />
        <span>
          <strong>{{ VISIBILITY_LABELS[v] }}</strong>
          <span class="am__hint">{{ VISIBILITY_HINTS[v] }}</span>
        </span>
      </label>
    </fieldset>

    <div v-if="visibility === 'restricted'" class="am__group">
      <GroupPicker
        v-model="groups"
        :options="state.availableGroups"
        :disabled="!canEdit"
        legend="Groupes ayant accès"
        hint="Vous ne pouvez associer que vos propres groupes. Un groupe ne donne pas accès à ses sous-groupes."
      />
    </div>

    <div v-if="needsConfirmation && impact?.unassignedPerson" class="am__impact" role="alert">
      <p class="am__impact-title"><VIcon name="ri-alert-line" /> Cette personne perdra l'accès au dossier :</p>
      <ul>
        <li>{{ impact.unassignedPerson.name }}</li>
      </ul>
      <p class="am__impact-note">Son affectation à ce dossier sera annulée et tracée. L'historique du dossier et les documents générés restent en place.</p>
      <label class="am__confirm"><input v-model="confirmed" type="checkbox" /> J'ai compris</label>
    </div>

    <DsfrAlert v-if="errors.length" alert type="error" small :description="errors.join(' ')" class="fr-mb-2w" />
    <DsfrAlert v-if="saveError" alert type="error" small :description="saveError" class="fr-mb-2w" />

    <section v-if="state.details.length" class="am__history" aria-labelledby="am-groups">
      <h3 id="am-groups" class="am__legend">Groupes associés</h3>
      <ul>
        <li v-for="g in state.details" :key="g.path">
          <span :title="g.path">{{ groupLabel(g.path) }}</span>{{ " " }}
          <span class="am__hint">— ajouté le {{ dateLabel(g.grantedAt) }}</span>
        </li>
      </ul>
    </section>
    <p v-else-if="state.visibility === 'analyse'" class="am__hint">Aucun groupe : le dossier suit l'accès à son analyse.</p>
    </template>
    <p v-else class="am__hint" role="status">Chargement…</p>
  </DsfrModal>
</template>

<style scoped>
.am__name {
  margin: 0 0 0.75rem;
  font-weight: 700;
}

.am__readonly {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 1rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  background: var(--background-alt-grey);
  font-size: 0.875rem;
}

.am__group {
  margin: 0 0 1rem;
  padding: 0;
  border: none;
}

.am__legend {
  margin: 0 0 0.5rem;
  font-size: 1rem;
  font-weight: 600;
}

.am__radio {
  display: flex;
  align-items: flex-start;
  gap: 0.625rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  margin-bottom: 0.5rem;
  cursor: pointer;
}

.am__radio span {
  display: flex;
  flex-direction: column;
}

.am__hint {
  font-size: 0.8125rem;
  font-weight: 400;
  color: var(--text-mention-grey);
}

.am__impact {
  margin: 0 0 1rem;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  background: var(--background-contrast-warning);
}

.am__impact-title {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin: 0 0 0.25rem;
  font-weight: 700;
}

.am__impact ul {
  margin: 0 0 0.5rem;
}

.am__impact-note {
  margin: 0 0 0.5rem;
  font-size: 0.875rem;
}

.am__confirm {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
}

.am__history ul {
  margin: 0;
  padding-left: 1.25rem;
  font-size: 0.875rem;
}
</style>
