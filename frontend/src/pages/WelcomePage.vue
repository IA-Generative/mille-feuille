<script setup lang="ts">
import { onMounted, onUnmounted, ref, type ComponentPublicInstance } from "vue";
import { useRouter } from "vue-router";
import ThemeSettings from "@/components/ThemeSettings.vue";

import { useAuth } from "@/composables/useAuth";

const { isAuthenticated, loading, login } = useAuth();
const router = useRouter();

// Redirige automatiquement vers l'application si l'utilisateur est déjà
// connecté (évite d'afficher la landing page inutilement).
const { push } = router;
onMounted(() => {
  if (isAuthenticated.value) push("/analyses");
});

// Animations au scroll : on observe les sections et on ajoute une classe
// `--visible` quand elles entrent dans le viewport.
const animatedSections = ref<HTMLElement[]>([]);
let observer: IntersectionObserver | undefined;

onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("welcome--visible");
          observer?.unobserve(entry.target);
        }
      }
    },
    { threshold: 0.15 },
  );
  for (const el of animatedSections.value) observer.observe(el);
});

onUnmounted(() => observer?.disconnect());

function registerSection(el: Element | ComponentPublicInstance | null) {
  if (el instanceof HTMLElement) {
    animatedSections.value.push(el);
    observer?.observe(el);
  }
}

const features = [
  {
    icon: "ri-file-search-line",
    title: "Classification documentaire",
    description:
      "Identification automatique de la nature de chaque pièce téléversée (CNI, passeport, justificatif de domicile, avis d'imposition…) avec un score de confiance.",
  },
  {
    icon: "ri-text-snippet",
    title: "Extraction d'entités",
    description:
      "Extraction des informations clés (nom, prénom, date de naissance, adresse, numéros) structurées en JSON, sans saisie manuelle.",
  },
  {
    icon: "ri-shield-check-line",
    title: "Contrôles de cohérence",
    description:
      "Croisement des données entre pièces d'un même dossier pour détecter incohérences, fraudes ou informations manquantes.",
  },
  {
    icon: "ri-chat-3-line",
    title: "Assistant conversationnel",
    description:
      "Posez des questions sur vos dossiers et obtenez des réponses contextualisées, avec citation des sources consultées.",
  },
  {
    icon: "ri-folder-shield-2-line",
    title: "Souveraineté des données",
    description:
      "Authentification Keycloak, stockage souverain et chiffrement. Vos données restent en France, rien n'est réutilisé pour le réentraînement.",
  },
  {
    icon: "ri-flow-chart",
    title: "Pipelines d'agents",
    description:
      "Configurez des agents IA spécialisés par analyse, avec des outils et des prompts personnalisés pour chaque cas d'usage.",
  },
];

const steps = [
  {
    num: 1,
    icon: "ri-upload-2-line",
    title: "Importez vos documents",
    description: "Déposez vos fichiers (PDF, images, tableurs) dans un dossier usager.",
  },
  {
    num: 2,
    icon: "ri-cpu-line",
    title: "L'IA analyse le contenu",
    description: "Classification, extraction d'entités et contrôles de cohérence automatiques.",
  },
  {
    num: 3,
    icon: "ri-chat-check-line",
    title: "Discutez avec l'assistant",
    description: "Posez des questions, enrichissez les synthèses et validez les résultats.",
  },
  {
    num: 4,
    icon: "ri-check-double-line",
    title: "Vérifiez et exportez",
    description: "Consultez les résultats, corrigez si besoin et finalisez votre dossier.",
  },
];

const useCases = [
  {
    icon: "ri-government-line",
    title: "Administration publique",
    description:
      "Instruction de demandes (titres de séjour, aides sociales, permis) avec vérification automatique des pièces justificatives.",
  },
  {
    icon: "ri-bank-line",
    title: "Conformité bancaire",
    description:
      "Traitement KYC : extraction d'identité depuis CNI/passeport, vérification d'adresse et cohérence entre documents.",
  },
  {
    icon: "ri-health-book-line",
    title: "Santé et assurance",
    description:
      "Analyse de dossiers de remboursement : lecture de ordonnances, factures et courriers médicaux avec extraction structurée.",
  },
];

// Les liens du pied de page. `aria-label` indique l'ouverture dans un nouvel onglet (le composant
// n'applique pas `title`). Le CGU est un fichier statique : une URL absolue est nécessaire.
const footerLinks = [
  {
    label: "Conditions d'utilisation",
    href: new URL("/cgu.md", window.location.origin).href,
    target: "_blank",
    rel: "noopener noreferrer",
    "aria-label": "Conditions d'utilisation - nouvelle fenêtre",
  },
  {
    label: "Code source",
    href: "https://github.com/IA-Generative/mille-feuille",
    target: "_blank",
    rel: "noopener noreferrer",
    "aria-label": "Code source - nouvelle fenêtre",
  },
];
</script>

<template>
  <div class="welcome">
    <div class="welcome__toolbar">
      <div class="fr-container welcome__toolbar-inner">
        <ThemeSettings />
      </div>
    </div>
    <!-- Hero -->
    <section class="welcome__hero">
      <div class="fr-container welcome__hero-inner">
        <p class="welcome__badge">Plateforme d'instruction assistée par IA</p>
        <h1 class="welcome__title">
          Accélérez l'instruction<br />de vos dossiers usagers
        </h1>
        <p class="welcome__subtitle">
          Importez vos documents, laissez l'IA extraire et structurer les
          informations clés, vérifiez la cohérence entre pièces et échangez
          avec un assistant conversationnel — le tout sur une infrastructure
          souveraine.
        </p>
        <div class="welcome__actions">
          <button
            v-if="!isAuthenticated && !loading"
            type="button"
            class="fr-btn fr-btn--lg"
            @click="login()"
          >
            Se connecter
          </button>
          <RouterLink
            v-if="isAuthenticated"
            to="/analyses"
            class="fr-btn fr-btn--lg"
          >
            Accéder à l'application
          </RouterLink>
          <a href="#features" class="fr-btn fr-btn--secondary fr-btn--lg">
            Découvrir les fonctionnalités
          </a>
        </div>
      </div>
    </section>

    <!-- Fonctionnalités -->
    <section id="features" :ref="registerSection" class="welcome__section welcome__animate">
      <div class="fr-container">
        <h2 class="welcome__section-title">Ce que MilleFeuille vous apporte</h2>
        <p class="welcome__section-subtitle">
          Une suite d'outils d'IA pour fiabiliser et accélérer le traitement
          documentaire, de l'import à la validation.
        </p>
        <div class="welcome__feature-grid">
          <div
            v-for="feature in features"
            :key="feature.title"
            class="welcome__feature-card"
          >
            <span class="welcome__feature-icon-wrapper">
              <VIcon :name="feature.icon" class="welcome__feature-icon" />
            </span>
            <h3 class="welcome__feature-title">{{ feature.title }}</h3>
            <p class="welcome__feature-desc">{{ feature.description }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Étapes -->
    <section :ref="registerSection" class="welcome__section welcome__section--alt welcome__animate">
      <div class="fr-container">
        <h2 class="welcome__section-title">Comment ça marche ?</h2>
        <p class="welcome__section-subtitle">
          Quatre étapes, de l'import du document à l'export du dossier validé.
        </p>
        <ol class="fr-raw-list welcome__steps" role="list">
          <li v-for="step in steps" :key="step.num" class="welcome__step">
            <div class="welcome__step-visual" aria-hidden="true">
              <span class="welcome__step-tile">
                <VIcon :name="step.icon" class="welcome__step-icon" />
              </span>
              <span class="welcome__step-num">{{ step.num }}</span>
            </div>
            <h3 class="welcome__step-title">{{ step.title }}</h3>
            <p class="welcome__step-desc">{{ step.description }}</p>
          </li>
        </ol>
      </div>
    </section>

    <!-- Cas d'usage -->
    <section :ref="registerSection" class="welcome__section welcome__animate">
      <div class="fr-container">
        <h2 class="welcome__section-title">Cas d'usage</h2>
        <p class="welcome__section-subtitle">
          MilleFeuille s'adapte à tout flux d'instruction documentaire nécessitant
          fiabilité et traçabilité.
        </p>
        <div class="welcome__usecase-grid">
          <div
            v-for="useCase in useCases"
            :key="useCase.title"
            class="welcome__usecase-card"
          >
            <span class="welcome__usecase-icon-wrapper">
              <VIcon :name="useCase.icon" class="welcome__usecase-icon" />
            </span>
            <h3 class="welcome__usecase-title">{{ useCase.title }}</h3>
            <p class="welcome__usecase-desc">{{ useCase.description }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA -->
    <section :ref="registerSection" class="welcome__cta welcome__animate">
      <div class="fr-container welcome__cta-inner">
        <h2 class="welcome__cta-title">Prêt à commencer ?</h2>
        <p class="welcome__cta-text">
          Connectez-vous pour accéder à votre espace de travail et créer vos
          premières analyses.
        </p>
        <div class="welcome__actions">
          <button
            v-if="!isAuthenticated && !loading"
            type="button"
            class="fr-btn fr-btn--lg"
            @click="login()"
          >
            Se connecter
          </button>
          <RouterLink
            v-if="isAuthenticated"
            to="/analyses"
            class="fr-btn fr-btn--lg"
          >
            Accéder à l'application
          </RouterLink>
        </div>
      </div>
    </section>

    <DsfrFooter
      logo-text="MilleFeuille"
      desc-text="© 2026 MilleFeuille — Instruction assistée des dossiers usagers"
      :mandatory-links="[]"
      :after-mandatory-links="footerLinks"
      licence-text=""
    />
  </div>
</template>

<style scoped>
.welcome {
  min-height: 100vh;
  background: var(--background-default-grey);
}

/* ── Barre d'outils ───────────────────────────────────── */
.welcome__toolbar{
  background: var(--background-default-grey);
  border-bottom: 1px solid var(--border-default-grey);
}

.welcome__toolbar-inner {
  display: flex;
  justify-content: flex-end;
  padding-block: 0.25rem;
}

/* ── Hero ─────────────────────────────────────────────── */
.welcome__hero {
  background: linear-gradient(
    135deg,
    var(--background-alt-blue-france) 0%,
    var(--background-alt-grey) 100%
  );
  padding: 4rem 0 5rem;
}

.welcome__hero-inner {
  max-width: 50rem;
  text-align: center;
}

.welcome__badge {
  display: inline-block;
  padding: 0.375rem 1rem;
  border-radius: 1rem;
  background: var(--background-action-low-blue-france);
  color: var(--text-action-high-blue-france);
  font-size: 0.875rem;
  font-weight: 500;
  margin-bottom: 1.5rem;
}

.welcome__title {
  font-size: clamp(2rem, 5vw, 3.25rem);
  font-weight: 700;
  color: var(--text-action-high-blue-france);
  margin: 0 0 1.25rem;
  line-height: 1.15;
}

.welcome__subtitle {
  font-size: 1.125rem;
  color: var(--text-default-grey);
  line-height: 1.6;
  margin: 0 auto 2.5rem;
  max-width: 38rem;
}

.welcome__actions {
  display: flex;
  gap: 1rem;
  justify-content: center;
  flex-wrap: wrap;
}

/* ── Sections génériques ──────────────────────────────── */
.welcome__section {
  padding: 4rem 0;
}

.welcome__section--alt {
  background: var(--background-alt-grey);
}

.welcome__section-title {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-title-grey);
  text-align: center;
  margin: 0 0 0.75rem;
}

.welcome__section-subtitle {
  font-size: 1.0625rem;
  color: var(--text-mention-grey);
  text-align: center;
  margin: 0 auto 3rem;
  max-width: 36rem;
  line-height: 1.5;
}

/* ── Cartes fonctionnalités ───────────────────────────── */
.welcome__feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
  gap: 1.5rem;
}

.welcome__feature-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 2rem 1.75rem;
  background: var(--background-default-grey);
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  transition:
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.welcome__feature-card:hover {
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
  border-color: var(--border-action-high-blue-france);
}

.welcome__feature-icon-wrapper {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 3rem;
  height: 3rem;
  border-radius: 0.5rem;
  background: var(--background-action-low-blue-france);
  margin-bottom: 1.25rem;
}

.welcome__feature-icon {
  font-size: 1.5rem;
  color: var(--text-action-high-blue-france);
}

.welcome__feature-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-title-grey);
  margin: 0 0 0.5rem;
}

.welcome__feature-desc {
  font-size: 0.9375rem;
  color: var(--text-mention-grey);
  line-height: 1.55;
  margin: 0;
}

/* Alternance : les cartes paires ont un fond bleu pâle. La tuile devient blanche pour rester
   distincte du fond, et l'icône garde sa couleur de base (bleu foncé). */
.welcome__feature-card:nth-child(even) {
  background: var(--background-alt-blue-france);
  border-color: var(--border-action-low-blue-france);
}

.welcome__feature-card:nth-child(even):hover {
  border-color: var(--border-action-high-blue-france);
}

.welcome__feature-card:nth-child(even) .welcome__feature-icon-wrapper {
  background: var(--background-default-grey);
}

.welcome__feature-card:nth-child(even) .welcome__feature-desc {
  color: var(--text-default-grey);
}

/* ── Étapes ───────────────────────────────────────────── */
.welcome__steps {
  --step-gap: 2rem;
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--step-gap);
}

.welcome__step {
  position: relative;
  text-align: center;
}

.welcome__step-visual {
  position: relative;
  display: inline-block;
  margin-bottom: 1.25rem;
}

.welcome__step-tile {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 4.5rem;
  height: 4.5rem;
  border-radius: 1rem;
  background: var(--background-action-low-blue-france);
}

.welcome__step-icon {
  font-size: 2rem;
  color: var(--text-action-high-blue-france);
}

/* Pastille de numéro posée sur le coin de la tuile. La bordure reprend le fond de la section pour « découper » la pastille. */
.welcome__step-num {
  position: absolute;
  top: -0.5rem;
  right: -0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 50%;
  border: 2px solid var(--background-alt-grey);
  background: var(--background-action-high-blue-france);
  color: var(--text-inverted-blue-france);
  font-size: 0.875rem;
  font-weight: 700;
}

/* Trait pointillé entre deux tuiles, uniquement quand les 4 étapes tiennent sur une ligne. */
@media (min-width: 62em) {
  .welcome__steps {
    grid-template-columns: repeat(4, 1fr);
  }

  .welcome__step:not(:last-child)::after {
    content: "";
    position: absolute;
    top: 2.25rem;                                  /* milieu de la tuile */
    left: calc(50% + 3rem);                        /* bord droit de la tuile + marge */
    right: calc(-50% - var(--step-gap) + 3rem);    /* bord gauche de la tuile suivante - marge */
    border-top: 2px dashed var(--border-action-low-blue-france);
  }
}

@media (min-width: 36em) and (max-width: 61.99em) {
  .welcome__steps { grid-template-columns: repeat(2, 1fr); }
}

.welcome__step-title {
  font-size: 1.0625rem;
  font-weight: 600;
  color: var(--text-title-grey);
  margin: 0 0 0.5rem;
}

.welcome__step-desc {
  font-size: 0.9375rem;
  color: var(--text-mention-grey);
  line-height: 1.55;
  margin: 0;
}

/* ── CTA ──────────────────────────────────────────────── */
.welcome__cta {
  padding: 4rem 0;
  text-align: center;
  background: linear-gradient(
    135deg,
    var(--background-alt-blue-france) 0%,
    var(--background-alt-grey) 100%
  );
}

.welcome__cta-inner {
  max-width: 40rem;
}

.welcome__cta-title {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-action-high-blue-france);
  margin: 0 0 0.75rem;
}

.welcome__cta-text {
  font-size: 1.125rem;
  color: var(--text-default-grey);
  margin: 0 0 2rem;
}

/* ── Cas d'usage ──────────────────────────────────────── */
.welcome__usecase-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr));
  gap: 1.5rem;
}

.welcome__usecase-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 1.75rem;
  background: var(--background-default-grey);
  border: 1px solid var(--border-default-grey);
  border-top: 4px solid var(--border-plain-blue-france);
  border-radius: 0.5rem;
}

.welcome__usecase-icon-wrapper {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 3.5rem;
  height: 3.5rem;
  border-radius: 0.75rem;
  background: var(--background-action-low-blue-france);
  margin-bottom: 1.25rem;
}

.welcome__usecase-icon {
  font-size: 1.75rem;
  color: var(--text-action-high-blue-france);
}

.welcome__usecase-title {
  font-size: 1.0625rem;
  font-weight: 600;
  color: var(--text-title-grey);
  margin: 0 0 0.5rem;
}

.welcome__usecase-desc {
  font-size: 0.9375rem;
  color: var(--text-default-grey);
  line-height: 1.55;
  margin: 0;
}

/* ── Animations au scroll ─────────────────────────────── */
.welcome__animate {
  opacity: 0;
  transform: translateY(1.5rem);
  transition:
    opacity 0.5s ease,
    transform 0.5s ease;
}

.welcome__animate.welcome--visible {
  opacity: 1;
  transform: translateY(0);
}

@media (prefers-reduced-motion: reduce) {
  .welcome__animate {
    opacity: 1;
    transform: none;
    transition: none;
  }
}

/* ── Responsive ───────────────────────────────────────── */
@media (max-width: 768px) {
  .welcome__hero {
    padding: 2.5rem 0 3.5rem;
  }

  .welcome__section {
    padding: 2.5rem 0;
  }

  .welcome__cta {
    padding: 2.5rem 0;
  }
}
</style>
