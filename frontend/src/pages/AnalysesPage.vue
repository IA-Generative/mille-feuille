<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import CreateAnalyseModal from "@/components/analyses/CreateAnalyseModal.vue";
import ThemeModal from "@/components/analyses/ThemeModal.vue";
import ThemeSection from "@/components/analyses/ThemeSection.vue";
import TutorialHint from "@/components/TutorialHint.vue";
import { useAnalyseThemes } from "@/composables/useAnalyseThemes";
import { useAuth } from "@/composables/useAuth";
import { useGroups } from "@/composables/useGroups";
import { guideStartRoute } from "@/pages/analyse/analyseGroups";
import type { AnalyseTheme } from "@/types/theme";
import { userMessage } from "@/utils/api";

const SEARCH_DELAY_MS = 250;

// Les thèmes sont gérés par les administrateurs (le backend reste juge).
const { isAdmin } = useAuth();
// Créer une analyse : un super admin, ou l'admin d'un groupe.
const { groups: myGroups, fetchGroups } = useGroups();
const canCreate = computed(() => isAdmin.value || myGroups.value.some((g) => g.canCreateAnalyses));
onMounted(() => fetchGroups().catch(() => {}));

const router = useRouter();
const { themes, unthemedCount, fetchThemes, deleteTheme } = useAnalyseThemes();

const searchInput = ref("");
const searchQuery = ref("");
const isLoaded = ref(false);
const error = ref("");
const isCreateModalOpened = ref(false);
const isThemeModalOpened = ref(false);
const editedTheme = ref<AnalyseTheme | null>(null);

async function load() {
  try {
    await fetchThemes(searchQuery.value);
    error.value = "";
    isLoaded.value = true;
  } catch (cause) {
    error.value = userMessage(cause, "Les analyses n'ont pas pu être chargées.");
  }
}

let timer: ReturnType<typeof setTimeout> | undefined;
watch(searchInput, (value) => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    searchQuery.value = value.trim();
    load();
  }, SEARCH_DELAY_MS);
});
onBeforeUnmount(() => clearTimeout(timer));
onMounted(load);

/** Les thèmes vides ne sont montrés qu'à qui peut les gérer, et jamais pendant une recherche. */
const isShown = (theme: AnalyseTheme) => theme.analyseCount > 0 || (isAdmin.value && !searchQuery.value);

function openThemeModal(theme: AnalyseTheme | null) {
  editedTheme.value = theme;
  isThemeModalOpened.value = true;
}

async function onThemeRemove(theme: AnalyseTheme) {
  if (!confirm(`Supprimer le thème « ${theme.name} » ? Ses analyses sont conservées.`)) return;
  try {
    await deleteTheme(theme.id);
    await load();
  } catch (cause) {
    error.value = userMessage(cause, "Le thème n'a pas pu être supprimé.");
  }
}

function onAnalyseCreated(id: string) {
  // Une analyse fraîchement créée est vide : on enchaîne directement sur l'assistant pas à pas.
  router.push(guideStartRoute(id, isAdmin.value));
}
</script>

<template>
  <div>
    <div class="analyses-page__header">
      <div>
        <h1 class="fr-h2">Analyses</h1>
        <p class="fr-text--lead">Retrouvez vos analyses, rangées par thème, ou créez-en une nouvelle.</p>
      </div>
      <div class="analyses-page__actions">
        <DsfrButton v-if="isAdmin" label="Créer un thème" icon="ri-folder-add-line" secondary @click="openThemeModal(null)" />
        <DsfrButton v-if="canCreate" label="Créer une analyse" icon="ri-add-line" @click="isCreateModalOpened = true" />
      </div>
    </div>

    <TutorialHint
      class="fr-mt-3w"
      slug="01-demarrage"
      title="Première analyse ? Un tutoriel vous guide."
      content="Le tutoriel « Démarrage » s'ouvre à côté de l'application : vous pouvez le suivre étape par étape tout en créant votre analyse. Il reste disponible à tout moment dans le menu utilisateur, en bas de la barre latérale, rubrique « Tutoriels »."
    />

    <DsfrSearchBar
      label="Rechercher une analyse"
      placeholder="Nom ou description..."
      :model-value="searchInput"
      class="analyses-page__search"
      @update:model-value="searchInput = $event"
    />

    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
    <p v-else-if="!isLoaded" class="fr-text--sm">Chargement…</p>
    <p v-else-if="unthemedCount === 0 && !themes.some(isShown)" class="fr-text--sm">
      {{ searchQuery ? "Aucune analyse ne correspond à cette recherche." : "Aucune analyse pour le moment." }}
    </p>

    <template v-if="isLoaded">
      <ThemeSection
        v-for="theme in themes.filter(isShown)"
        :key="theme.id"
        :theme-id="theme.id"
        :title="theme.name"
        :description="theme.description"
        :count="theme.analyseCount"
        :query="searchQuery"
        :editable="isAdmin"
        @edit="openThemeModal(theme)"
        @remove="onThemeRemove(theme)"
      />
      <ThemeSection
        v-if="unthemedCount > 0"
        key="sans-theme"
        :theme-id="null"
        title="Sans thème"
        :count="unthemedCount"
        :query="searchQuery"
      />
    </template>

    <ThemeModal
      :opened="isThemeModalOpened"
      :theme="editedTheme"
      @close="isThemeModalOpened = false"
      @saved="load"
    />
    <CreateAnalyseModal v-model:opened="isCreateModalOpened" @created="onAnalyseCreated" />
  </div>
</template>

<style scoped>
.analyses-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.analyses-page__actions {
  display: flex;
  gap: 0.75rem;
}

.analyses-page__search {
  max-width: 32rem;
  margin: 1.5rem 0 2rem;
}
</style>
