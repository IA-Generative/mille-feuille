<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";

import MarkdownText from "@/components/MarkdownText.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import AnalyseGuideBar from "@/components/analyses/AnalyseGuideBar.vue";
import AnalyseIdentityModal from "@/components/analyses/AnalyseIdentityModal.vue";
import DeleteAnalyseModal from "@/components/analyses/DeleteAnalyseModal.vue";
import BackLink from "@/components/BackLink.vue";
import { useAuth } from "@/composables/useAuth";
import { useCanManageAnalyse } from "@/composables/useCanManageAnalyse";
import { visibleGroups } from "@/pages/analyse/analyseGroups";

const route = useRoute();
const router = useRouter();
const { getById, fetchAnalyse, forget } = useAnalyses();
const { isAdmin } = useAuth();

const analyse = computed(() => getById(String(route.params.id)));

// Modifier / supprimer : le créateur et les administrateurs (le backend reste juge).
const canManageAnalyse = useCanManageAnalyse();
const canManage = computed(() => (analyse.value ? canManageAnalyse(analyse.value.createdBy) : false));
const isEditing = ref(false);
const isDeleting = ref(false);

async function onDeleted() {
  const id = String(route.params.id);
  await router.push("/analyses");
  forget(id);
}

function askDelete() {
  isEditing.value = false;
  isDeleting.value = true;
}

onMounted(() => {
  if (!analyse.value) fetchAnalyse(String(route.params.id));
});

// Quatre onglets de premier niveau (voir analyseGroups) ; chaque section d'un groupe reste une route enfant.
// Les champs tabId/panelId sont requis par DsfrTabs pour les attributs ARIA.
const groups = computed(() => visibleGroups(isAdmin.value));
const tabs = computed(() =>
  groups.value.map((group) => ({
    title: group.title,
    icon: group.icon,
    tabId: `tab-${group.id}`,
    panelId: `panel-${group.id}`,
  })),
);

const activeTabIndex = computed(() => {
  const index = groups.value.findIndex((group) => group.sections.some((section) => section.routeName === route.name));
  return index === -1 ? 0 : index;
});
const activeGroup = computed(() => groups.value[activeTabIndex.value]);

function goToSection(routeName: string, query = route.query) {
  router.push({ name: routeName, params: route.params, query });
}

function selectTab(index: number) {
  const group = groups.value[index];
  if (group) goToSection(group.sections[0].routeName, guideMode.value ? route.query : {});
}

// Assistant pas à pas : ?guide=all enchaîne toutes les sections (après la création), ?guide=group celles du groupe.
const guideMode = computed(() => (["all", "group"].includes(String(route.query.guide)) ? String(route.query.guide) : null));
const guideSteps = computed(() => {
  if (guideMode.value === "all") return groups.value.flatMap((group) => group.sections);
  return guideMode.value === "group" ? (activeGroup.value?.sections ?? []) : [];
});
const guideIndex = computed(() => Math.max(0, guideSteps.value.findIndex((step) => step.routeName === route.name)));

function startGuide() {
  const first = activeGroup.value?.sections[0];
  if (first) goToSection(first.routeName, { guide: "group" });
}

function quitGuide() {
  goToSection(String(route.name), {});
}
</script>

<template>
  <div v-if="analyse">
    <BackLink to="/analyses" class="analyse-detail__back">
      Retour aux analyses
    </BackLink>

    <div class="analyse-detail__header">
      <div class="analyse-detail__intro">
        <h1 class="fr-h2">{{ analyse.name }}</h1>
        <div
          class="analyse-detail__description"
          role="region"
          aria-label="Description de l'analyse"
          tabindex="0"
        >
          <MarkdownText :content="analyse.description" class="fr-text--lead" />
        </div>
      </div>
      <DsfrButton v-if="canManage" label="Modifier l'analyse" icon="ri-edit-line" tertiary size="sm" @click="isEditing = true" />
    </div>

    <template v-if="canManage">
      <AnalyseIdentityModal v-model:opened="isEditing" :analyse="analyse" @delete="askDelete" />
      <DeleteAnalyseModal v-model:opened="isDeleting" :analyse="analyse" @deleted="onDeleted" />
    </template>

    <DsfrTabs
      :model-value="activeTabIndex"
      tab-list-name="Sections de l'analyse"
      :tab-titles="tabs"
      @update:model-value="selectTab"
    >
      <!-- Un panneau par onglet : DsfrTabs mesure le panneau de l'onglet actif (panels[index]) pour dimensionner la
           zone, avec un seul panneau les onglets autres que le premier étaient coupés. Seul le groupe actif est rendu. -->
      <DsfrTabContent v-for="(group, index) in groups" :key="group.id" :panel-id="tabs[index].panelId" :tab-id="tabs[index].tabId">
        <template v-if="group.id === activeGroup?.id">
          <AnalyseGuideBar
            v-if="guideMode"
            :steps="guideSteps"
            :current="guideIndex"
            @go="(i) => goToSection(guideSteps[i].routeName)"
            @quit="quitGuide"
          />
          <div v-else-if="group.sections.length > 1" class="analyse-detail__subnav">
            <nav class="analyse-detail__sections" :aria-label="`Sections : ${group.title}`">
              <RouterLink
                v-for="section in group.sections"
                :key="section.routeName"
                :to="{ name: section.routeName, params: route.params }"
                class="analyse-detail__section"
                :class="{ 'analyse-detail__section--active': section.routeName === route.name }"
              >
                {{ section.title }}
              </RouterLink>
            </nav>
            <DsfrButton label="Pas à pas" icon="ri-footprint-line" tertiary size="sm" @click="startGuide" />
          </div>
          <RouterView />
        </template>
      </DsfrTabContent>
    </DsfrTabs>
  </div>
  <div v-else>
    <p>Chargement…</p>
    <RouterLink to="/analyses" class="fr-link">Retour aux analyses</RouterLink>
  </div>
</template>

<style scoped>
.analyse-detail__back {
  display: inline-flex;
  margin-bottom: 1.5rem;
}

.analyse-detail__subnav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.analyse-detail__sections {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.analyse-detail__section {
  padding: 0.375rem 0.875rem;
  border-radius: 999px;
  background: var(--background-alt-grey);
  color: var(--text-default-grey);
  font-size: 0.875rem;
  text-decoration: none;
  background-image: none;
}

.analyse-detail__section--active {
  background: var(--background-action-high-blue-france);
  color: var(--text-inverted-blue-france);
}

.analyse-detail__section:hover {
  background-color: var(--background-alt-grey-hover);
}

.analyse-detail__section:active {
  background-color: var(--background-alt-grey-active);
}

.analyse-detail__section--active:hover {
  background-color: var(--background-action-high-blue-france-hover);
}

.analyse-detail__section--active:active {
  background-color: var(--background-action-high-blue-france-active);
}

.analyse-detail__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 2rem;
}

/* Colonne de gauche : prend la place restante sans pousser le bouton « Modifier l'analyse ». */
.analyse-detail__intro {
  flex: 1;
  min-width: 0;
}

/* Description plafonnée en hauteur : le texte défile dans le bloc, les onglets restent visibles. */
.analyse-detail__description {
  max-height: 18rem;
  overflow-y: auto;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  background:
    /* caches : suivent le contenu et masquent l'ombre quand on est tout en haut ou tout en bas */
    linear-gradient(var(--background-alt-grey) 30%, transparent) top / 100% 2rem no-repeat local,
    linear-gradient(transparent, var(--background-alt-grey) 70%) bottom / 100% 2rem no-repeat local,
    /* ombres : fixes sur les bords du bloc */
    radial-gradient(farthest-side at 50% 0, var(--border-plain-grey), transparent) top / 100% 0.5rem no-repeat scroll,
    radial-gradient(farthest-side at 50% 100%, var(--border-plain-grey), transparent) bottom / 100% 0.5rem no-repeat scroll,
    var(--background-alt-grey);
}

/* Barre de défilement toujours visible, y compris sur macOS (qui masque la barre native tant qu'on ne défile pas). */
.analyse-detail__description::-webkit-scrollbar {
  width: 0.75rem;
}

.analyse-detail__description::-webkit-scrollbar-track {
  background: transparent;
}

.analyse-detail__description::-webkit-scrollbar-thumb {
  border: 3px solid var(--background-alt-grey);
  border-radius: 999px;
  background: var(--border-plain-grey);
}

/* Firefox : pas de ::-webkit-scrollbar, on utilise les propriétés standard. */
@supports not selector(::-webkit-scrollbar) {
  .analyse-detail__description {
    scrollbar-width: thin;
    scrollbar-color: var(--border-plain-grey) transparent;
  }
}
</style>
