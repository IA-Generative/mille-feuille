<script setup lang="ts">
import { computed, ref } from "vue";

import GroupPicker from "@/components/access/GroupPicker.vue";
import { useDossierAccess } from "@/composables/useDossierAccess";
import { VISIBILITY_HINTS, VISIBILITY_LABELS, type DossierAccess, type Visibility } from "@/types/access";

// « Définir l'accès » sur une sélection de dossiers (administrateurs).
const props = defineProps<{ count: number }>();
const emit = defineEmits<{ apply: [access: DossierAccess]; close: [] }>();

const { myGroups } = useDossierAccess();

const visibility = ref<Visibility>("restricted");
const groups = ref<string[]>([]);

const error = computed(() =>
  visibility.value === "restricted" && groups.value.length === 0 ? "Choisissez au moins un groupe." : null,
);

const actions = computed(() => [
  { label: "Appliquer", disabled: !!error.value, onClick: () => emit("apply", { visibility: visibility.value, groups: groups.value }) },
  { label: "Annuler", secondary: true, onClick: () => emit("close") },
]);

const visibilityOptions: Visibility[] = ["restricted", "analyse"];
</script>

<template>
  <DsfrModal
    :opened="true"
    :title="`Définir l'accès de ${count} dossier${count > 1 ? 's' : ''}`"
    icon="ri-lock-line"
    :actions="actions"
    @close="emit('close')"
  >
    <fieldset class="ba__group">
      <legend class="ba__legend">Qui peut voir ces dossiers ?</legend>
      <label v-for="v in visibilityOptions" :key="v" class="ba__radio">
        <input v-model="visibility" type="radio" :value="v" />
        <span>
          <strong>{{ VISIBILITY_LABELS[v] }}</strong>
          <span class="ba__hint">{{ VISIBILITY_HINTS[v] }}</span>
        </span>
      </label>
    </fieldset>

    <GroupPicker v-if="visibility === 'restricted'" v-model="groups" :options="myGroups" legend="Groupes ayant accès" hint="Vos propres groupes uniquement. Ils remplacent les groupes actuels de chaque dossier." />
    <p v-if="error" class="fr-error-text fr-mt-1w">{{ error }}</p>

    <p class="ba__note">Les affectations des personnes qui perdraient l'accès seront annulées et tracées dans l'historique de chaque dossier.</p>
  </DsfrModal>
</template>

<style scoped>
.ba__group {
  margin: 0 0 1rem;
  padding: 0;
  border: none;
}

.ba__legend {
  margin-bottom: 0.5rem;
  font-weight: 600;
}

.ba__radio {
  display: flex;
  align-items: flex-start;
  gap: 0.625rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  margin-bottom: 0.5rem;
  cursor: pointer;
}

.ba__radio span {
  display: flex;
  flex-direction: column;
}

.ba__hint {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.ba__note {
  margin: 1rem 0 0;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}
</style>
