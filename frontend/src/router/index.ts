import { watch } from "vue";
import { createRouter, createWebHistory } from "vue-router";

import { useAuth } from "@/composables/useAuth";
import AdministrationPage from "@/pages/AdministrationPage.vue";
import AnalyseAgentsTab from "@/pages/analyse/AnalyseAgentsTab.vue";
import AnalyseClassificationTab from "@/pages/analyse/AnalyseClassificationTab.vue";
import AnalyseDetailPage from "@/pages/AnalyseDetailPage.vue";
import AnalyseDocumentsTab from "@/pages/analyse/AnalyseDocumentsTab.vue";
import AnalyseExtractionTab from "@/pages/analyse/AnalyseExtractionTab.vue";
import AnalyseSearchTab from "@/pages/analyse/AnalyseSearchTab.vue";
import AnalyseSourcesTab from "@/pages/analyse/AnalyseSourcesTab.vue";
import AnalyseStatusesTab from "@/pages/analyse/AnalyseStatusesTab.vue";
import AnalyseTrackingTab from "@/pages/analyse/AnalyseTrackingTab.vue";
import AnalysesPage from "@/pages/AnalysesPage.vue";
import DashboardPage from "@/pages/DashboardPage.vue";
import DocumentReviewPage from "@/pages/DocumentReviewPage.vue";
import DossierAnalysisPage from "@/pages/DossierAnalysisPage.vue";
import DossierDocumentsPage from "@/pages/DossierDocumentsPage.vue";
import DossierHistoryPage from "@/pages/DossierHistoryPage.vue";
import DossierDetailPage from "@/pages/DossierDetailPage.vue";
import DossiersPage from "@/pages/DossiersPage.vue";
import ProfilePage from "@/pages/ProfilePage.vue";
import ToolsPage from "@/pages/ToolsPage.vue";
import TrackingPage from "@/pages/TrackingPage.vue";
import UsagePage from "@/pages/UsagePage.vue";
import WelcomePage from "@/pages/WelcomePage.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/dashboard" },
    { path: "/welcome", name: "welcome", component: WelcomePage, meta: { public: true } },
    { path: "/dashboard", name: "dashboard", component: DashboardPage },
    { path: "/analyses", name: "analyses", component: AnalysesPage },
    {
      path: "/analyses/:id",
      name: "analyse-detail",
      component: AnalyseDetailPage,
      redirect: (to) => ({ name: "analyse-classification", params: to.params }),
      children: [
        {
          path: "classification",
          name: "analyse-classification",
          component: AnalyseClassificationTab,
        },
        {
          path: "extraction",
          name: "analyse-extraction",
          component: AnalyseExtractionTab,
        },
        {
          path: "agents",
          name: "analyse-agents",
          component: AnalyseAgentsTab,
        },
        {
          path: "statuts",
          name: "analyse-statuses",
          component: AnalyseStatusesTab,
        },
        {
          path: "sources",
          name: "analyse-sources",
          component: AnalyseSourcesTab,
        },
        {
          path: "recherche",
          name: "analyse-search",
          component: AnalyseSearchTab,
        },
        {
          path: "suivi",
          name: "analyse-tracking",
          component: AnalyseTrackingTab,
        },
        {
          path: "documents",
          name: "analyse-documents",
          component: AnalyseDocumentsTab,
          // Modèles de document : réservés aux administrateurs (backend issue #138).
          meta: { requiresAdmin: true },
        },
      ],
    },
    { path: "/dossiers", name: "dossiers", component: DossiersPage },
    {
      path: "/dossiers/:id",
      name: "dossier-detail",
      component: DossierDetailPage,
      // La zone d'envoi du chat colle au bas de l'écran (sticky) : le contenu ne doit pas être son propre conteneur de
      // défilement, voir App.vue.
      meta: { pageScroll: true },
    },
    { path: "/dossiers/:id/analyse", name: "dossier-analysis", component: DossierAnalysisPage },
    { path: "/dossiers/:id/documents", name: "dossier-documents", component: DossierDocumentsPage },
    { path: "/dossiers/:id/historique", name: "dossier-history", component: DossierHistoryPage },
    { path: "/dossiers/:id/documents/:draftId", name: "document-review", component: DocumentReviewPage },
    { path: "/suivi", name: "tracking", component: TrackingPage },
    { path: "/profile", name: "profile", component: ProfilePage },
    { path: "/consommation", name: "usage", component: UsagePage },
    { path: "/outils", name: "tools", component: ToolsPage },
    {
      path: "/administration",
      name: "administration",
      component: AdministrationPage,
      meta: { requiresAdmin: true },
    },
  ],
});

// Garde globale : les routes publiques (meta.public) sont toujours
// accessibles. Pour les autres, on attend que /api/auth/me réponde ; si
// l'utilisateur n'est pas connecté, on le redirige vers la page d'accueil
// (/welcome) plutôt que de déclencher immédiatement le flow Keycloak —
// c'est depuis la page d'accueil que l'utilisateur clique "Se connecter".
router.beforeEach(async (to) => {
  if (to.meta.public) return true;

  const { isAuthenticated, isAdmin, loading } = useAuth();

  if (loading.value) {
    // fetchProfile est lancé au montage de App.vue : on attend qu'elle
    // termine avant de décider (évite un flash de redirection).
    await new Promise<void>((resolve) => {
      const stop = watch(loading, (isLoading) => {
        if (!isLoading) {
          stop();
          resolve();
        }
      });
    });
  }

  if (!isAuthenticated.value) {
    // On redirige vers la page d'accueil avec un paramètre pour revenir
    // ici après login.
    return { name: "welcome", query: { redirect: to.fullPath } };
  }

  if (to.meta.requiresAdmin && !isAdmin.value) {
    return { name: "dossiers" };
  }

  return true;
});
