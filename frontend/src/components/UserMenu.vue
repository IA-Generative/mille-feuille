<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import HelperAgentModal from "@/components/HelperAgentModal.vue";
import { useHelperAgent } from "@/composables/useHelperAgent";
import InfoModal from "@/components/InfoModal.vue";
import ReportFormModal from "@/components/ReportFormModal.vue";
import TaskDrawer from "@/components/TaskDrawer.vue";
import TutorialModal from "@/components/TutorialModal.vue";
import { useAuth } from "@/composables/useAuth";
import { useCgu } from "@/composables/useCgu";
import { useUserTasks } from "@/composables/useUserTasks";
import { renderMarkdown } from "@/utils/markdown";

// Version lue à la compilation depuis package.json (injectée par Vite via define).
const APP_VERSION = __APP_VERSION__;

const router = useRouter();
const { isAuthenticated, userName, isAdmin, profile, loading, login, logout } = useAuth();
const { fetchActive } = useCgu();
const { isOpen: showHelperAgent, openHelper, closeHelper } = useHelperAgent();

const showUserMenu = ref(false);
const userWrapper = ref<HTMLElement>();

// Modales
const showChangelog = ref(false);
const showCgu = ref(false);
const showReport = ref(false);
const showTutorials = ref(false);
const showTaskDrawer = ref(false);

// Tâches utilisateur (issue #62)
const { hasActiveTasks, activeCount } = useUserTasks();

const changelogHtml = ref("");
const cguHtml = ref("");
const changelogError = ref("");
const cguError = ref("");

const props = defineProps<{
  collapsed?: boolean;
}>();

const isCollapsed = computed(() => props.collapsed ?? false);

function toggleMenu() {
  showUserMenu.value = !showUserMenu.value;
}

function closeMenu() {
  showUserMenu.value = false;
}

function goProfile() {
  closeMenu();
  router.push("/profile");
}

function goUsage() {
  closeMenu();
  router.push("/consommation");
}

function goAdmin() {
  closeMenu();
  router.push("/administration");
}

function doLogout() {
  closeMenu();
  logout();
}

async function openChangelog() {
  closeMenu();
  showChangelog.value = true;
  if (!changelogHtml.value && !changelogError.value) {
    try {
      const res = await fetch("/CHANGELOG.md");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      changelogHtml.value = renderMarkdown(await res.text());
    } catch {
      changelogError.value =
        "Impossible de charger le journal des versions. Réessayez plus tard.";
    }
  }
}

async function openCgu() {
  closeMenu();
  showCgu.value = true;
  if (!cguHtml.value && !cguError.value) {
    try {
      const cgu = await fetchActive();
      if (cgu === null) {
        cguError.value = "Aucune version des conditions d'utilisation n'est disponible pour le moment.";
        return;
      }
      cguHtml.value = renderMarkdown(cgu.content);
    } catch {
      cguError.value =
        "Impossible de charger les conditions d'utilisation. Réessayez plus tard.";
    }
  }
}

function openReport() {
  closeMenu();
  showReport.value = true;
}

function openHelperAgent() {
  closeMenu();
  openHelper();
}

function openTutorials() {
  closeMenu();
  showTutorials.value = true;
}

function openTaskDrawer() {
  closeMenu();
  showTaskDrawer.value = true;
}

function handleOutsideClick(event: MouseEvent) {
  if (showUserMenu.value && !userWrapper.value?.contains(event.target as Node)) {
    showUserMenu.value = false;
  }
}

// Raccourci clavier Ctrl+K / Cmd+K pour ouvrir l'assistant.
function handleKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    showUserMenu.value = false;
    openHelper();
  }
  if (event.key === "Escape" && showHelperAgent.value) {
    closeHelper();
  }
}

function initials(name: string): string {
  return name
    .split(" ")
    .map((part) => part.charAt(0))
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

onMounted(() => {
  document.addEventListener("click", handleOutsideClick);
  document.addEventListener("keydown", handleKeydown);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", handleOutsideClick);
  document.removeEventListener("keydown", handleKeydown);
});
</script>

<template>
  <!-- Utilisateur connecté : avatar + menu flottant au-dessus -->
  <div v-if="isAuthenticated" ref="userWrapper" class="user-menu-wrapper" :class="{ 'user-menu-wrapper--collapsed': collapsed }">
    <div v-if="showUserMenu" class="user-menu" role="menu">
      <div class="user-menu__header">
        <span class="user-menu__name">{{ userName }}</span>
        <span v-if="profile?.email" class="user-menu__email">{{ profile.email }}</span>
      </div>

      <button type="button" class="user-menu__item" role="menuitem" @click="goProfile">
        <VIcon name="ri-account-circle-line" />
        <span>Profil</span>
      </button>

      <button type="button" class="user-menu__item" role="menuitem" @click="goUsage">
        <VIcon name="ri-drop-line" />
        <span>Ma consommation</span>
      </button>

      <button v-if="isAdmin" type="button" class="user-menu__item" role="menuitem" @click="goAdmin">
        <VIcon name="ri-shield-user-line" />
        <span>Administration</span>
      </button>

      <button type="button" class="user-menu__item" role="menuitem" @click="openTaskDrawer">
        <VIcon name="ri-task-line" />
        <span>Tâches</span>
        <span v-if="hasActiveTasks" class="user-menu__badge">{{ activeCount }}</span>
      </button>

      <button type="button" class="user-menu__item" role="menuitem" @click="openHelperAgent">
        <VIcon name="ri-robot-2-line" />
        <span>Assistant</span>
        <kbd class="user-menu__shortcut">⌘K</kbd>
      </button>

      <button type="button" class="user-menu__item" role="menuitem" @click="openTutorials">
        <VIcon name="ri-book-open-line" />
        <span>Tutoriels</span>
      </button>

      <div class="user-menu__separator" />

      <button type="button" class="user-menu__item" role="menuitem" @click="openChangelog">
        <VIcon name="ri-git-commit-line" />
        <span>Notes de version</span>
      </button>

      <button type="button" class="user-menu__item" role="menuitem" @click="openCgu">
        <VIcon name="ri-file-text-line" />
        <span>Conditions d'utilisation</span>
      </button>

      <button type="button" class="user-menu__item" role="menuitem" @click="openReport">
        <VIcon name="ri-bug-line" />
        <span>Signaler un bug</span>
      </button>

      <div class="user-menu__separator" />

      <button type="button" class="user-menu__item user-menu__item--danger" role="menuitem" @click="doLogout">
        <VIcon name="ri-logout-box-r-line" />
        <span>Se déconnecter</span>
      </button>

      <div class="user-menu__version">Version {{ APP_VERSION }}</div>
    </div>

    <button
      type="button"
      class="user-menu__trigger"
      :title="userName"
      @click="toggleMenu"
    >
      <span class="user-menu__avatar" aria-hidden="true">{{ initials(userName) }}</span>
      <span v-if="!isCollapsed" class="user-menu__label">{{ userName }}</span>
      <VIcon v-if="!isCollapsed" :name="showUserMenu ? 'ri-arrow-up-s-line' : 'ri-arrow-down-s-line'" class="user-menu__chevron" />
    </button>
  </div>

  <!-- Non connecté : bouton "Se connecter" -->
  <button
    v-else
    type="button"
    class="user-menu__trigger user-menu__trigger--login"
    :disabled="loading"
    @click="login()"
  >
    <VIcon name="ri-login-box-line" />
    <span v-if="!isCollapsed" class="user-menu__label">{{ loading ? "…" : "Se connecter" }}</span>
  </button>

  <!-- Modales -->
  <InfoModal title="Journal des versions" :open="showChangelog" @close="showChangelog = false">
    <div v-if="changelogError" class="user-menu__error">{{ changelogError }}</div>
    <!-- eslint-disable-next-line vue/no-v-html -- contenu statique rendu par renderMarkdown (échappé) -->
    <div v-else-if="changelogHtml" class="markdown" v-html="changelogHtml" />
    <p v-else>Chargement…</p>
  </InfoModal>

  <InfoModal title="Conditions d'utilisation" :open="showCgu" @close="showCgu = false">
    <div v-if="cguError" class="user-menu__error">{{ cguError }}</div>
    <!-- eslint-disable-next-line vue/no-v-html -- contenu statique rendu par renderMarkdown (échappé) -->
    <div v-else-if="cguHtml" class="markdown" v-html="cguHtml" />
    <p v-else>Chargement…</p>
  </InfoModal>

  <ReportFormModal :open="showReport" @close="showReport = false" />

  <HelperAgentModal :open="showHelperAgent" @close="closeHelper" />

  <TutorialModal :open="showTutorials" @close="showTutorials = false" />

  <TaskDrawer :open="showTaskDrawer" @close="showTaskDrawer = false" />
</template>

<style scoped>
.user-menu-wrapper {
  position: relative;
  flex-shrink: 0;
}

/* Menu flottant qui s'ouvre au-dessus du bouton profil */
.user-menu {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  margin-bottom: 0.5rem;
  padding: 0.25rem;
  background: var(--background-default-grey);
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 100;
}

.user-menu__header {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  padding: 0.625rem 0.75rem 0.5rem;
  border-bottom: 1px solid var(--border-default-grey);
  margin-bottom: 0.25rem;
}

.user-menu__name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-default-grey);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-menu__email {
  font-size: 0.75rem;
  color: var(--text-mention-grey);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-menu__separator {
  height: 1px;
  margin: 0.25rem 0.5rem;
  background: var(--border-default-grey);
}

.user-menu__item {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  width: 100%;
  text-align: left;
  padding: 0.625rem 0.75rem;
  border: none;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--text-default-grey);
  cursor: pointer;
  font-size: 0.875rem;
  font-family: inherit;
  transition: background-color 0.15s ease;
}

.user-menu__item:hover {
  background: var(--background-alt-grey-hover);
}

.user-menu__item--danger {
  color: var(--text-default-error);
}

.user-menu__item--danger:hover {
  background: var(--background-error-hover);
}

.user-menu__version {
  padding: 0.5rem 0.75rem 0.25rem;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
  text-align: center;
}

/* Bouton déclencheur (avatar + nom) */
.user-menu__trigger {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.75rem;
  border-radius: 0.25rem;
  border: none;
  background: none;
  color: var(--text-default-grey);
  cursor: pointer;
  text-align: left;
  white-space: nowrap;
  font-family: inherit;
  transition: background-color 0.15s ease;
}

.user-menu__trigger:hover {
  background-color: var(--background-alt-grey-hover);
}

.user-menu__trigger--login {
  justify-content: center;
}

.user-menu__avatar {
  flex-shrink: 0;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--text-inverted-blue-france);
  background: var(--background-action-high-blue-france);
}

.user-menu__label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.875rem;
  font-weight: 500;
}

.user-menu__chevron {
  flex-shrink: 0;
  opacity: 0.6;
}

/* En mode sidebar réduite : on centre l'avatar */
.user-menu-wrapper--collapsed .user-menu__trigger {
  justify-content: center;
}

.user-menu-wrapper--collapsed .user-menu {
  left: 0;
  right: auto;
  min-width: 12rem;
}

/* Contenu markdown dans les modales */
.user-menu__error {
  color: var(--text-default-error);
}

.markdown :deep(h1) {
  font-size: 1.25rem;
  margin: 1rem 0 0.5rem;
}

.markdown :deep(h2) {
  font-size: 1.1rem;
  margin: 1.25rem 0 0.5rem;
}

.markdown :deep(h3) {
  font-size: 1rem;
  margin: 1rem 0 0.25rem;
}

.markdown :deep(ul) {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

.markdown :deep(li) {
  margin: 0.25rem 0;
}

.markdown :deep(a) {
  color: var(--text-action-high-blue-france);
}

.markdown :deep(code) {
  padding: 0.125rem 0.375rem;
  background: var(--background-alt-grey);
  border-radius: 0.25rem;
  font-size: 0.85em;
}

.markdown :deep(pre) {
  padding: 0.75rem;
  background: var(--background-alt-grey);
  border-radius: 0.375rem;
  overflow-x: auto;
}

.markdown :deep(hr) {
  border: none;
  border-top: 1px solid var(--border-default-grey);
  margin: 1rem 0;
}

.user-menu__shortcut {
  margin-left: auto;
  padding: 0.0625rem 0.375rem;
  font-size: 0.6875rem;
  font-family: inherit;
  color: var(--text-mention-grey);
  background: var(--background-alt-grey);
  border: 1px solid var(--border-default-grey);
  border-radius: 0.25rem;
  line-height: 1.4;
}

.user-menu__badge {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.375rem;
  border-radius: 0.625rem;
  background: var(--background-action-high-red-marianne);
  color: var(--text-inverted-red-marianne);
  font-size: 0.75rem;
  font-weight: 700;
}
</style>
