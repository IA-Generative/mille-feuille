/**
 * Composable pour la gestion des tutoriels (V1 statique).
 *
 * Les tutoriels sont des fichiers Markdown servis statiquement depuis
 * /tutorials/*.md. La progression (tutoriels vus) est persistée en
 * localStorage.
 */
import { computed, ref, watch } from "vue";

import { renderMarkdown } from "@/utils/markdown";

export interface Tutorial {
  slug: string;
  title: string;
  icon: string;
  category: string;
  url: string;
}

export interface TutorialStep {
  title: string; // texte du titre `##`, ex. « 1. Créer une analyse »
  html: string; // contenu de l'étape, déjà rendu en HTML
}

interface PersistedState {
  slug: string | null;
  step: number;
  minimized: boolean;
}

/** Catalogue statique des tutoriels disponibles. */
const TUTORIALS: Tutorial[] = [
  {
    slug: "01-demarrage",
    title: "Démarrage : créer une analyse et un dossier",
    icon: "ri-rocket-line",
    category: "Premiers pas",
    url: "/tutorials/01-demarrage.md",
  },
  {
    slug: "02-documents",
    title: "Ajouter des documents à un dossier",
    icon: "ri-file-upload-line",
    category: "Premiers pas",
    url: "/tutorials/02-documents.md",
  },
  {
    slug: "03-pipeline",
    title: "Lancer le pipeline d'instruction",
    icon: "ri-flow-chart",
    category: "Analyse",
    url: "/tutorials/03-pipeline.md",
  },
  {
    slug: "04-assistant",
    title: "Utiliser l'assistant conversationnel",
    icon: "ri-chat-3-line",
    category: "Analyse",
    url: "/tutorials/04-assistant.md",
  },
  {
    slug: "05-partage",
    title: "Consulter et partager les résultats",
    icon: "ri-share-line",
    category: "Collaboration",
    url: "/tutorials/05-partage.md",
  },
];

const STORAGE_KEY = "millefeuille-tutorials-seen";
const STATE_KEY = "millefeuille-tutorials-state";

// État partagé entre toutes les instances du composable.
const saved = loadState();
const tutorials = ref<Tutorial[]>(TUTORIALS);
const seenSlugs = ref<Set<string>>(loadSeen());
const currentSlug = ref<string | null>(saved.slug);
const steps = ref<TutorialStep[]>([]);
const stepIndex = ref(saved.step);
const panelOpen = ref(false);
const minimized = ref(saved.minimized);
const loading = ref(false);
const error = ref("");
let loadToken = 0;

watch([currentSlug, stepIndex, minimized], () => {
  try {
    localStorage.setItem(
      STATE_KEY,
      JSON.stringify({ slug: currentSlug.value, step: stepIndex.value, minimized: minimized.value }),
    );
  } catch {
    // Ignoré.
  }
});

function loadSeen(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return new Set(JSON.parse(raw) as string[]);
  } catch {
    // localStorage indisponible ou corrompu.
  }
  return new Set();
}

function persistSeen() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...seenSlugs.value]));
  } catch {
    // Ignoré.
  }
}

function loadState(): PersistedState {
  try {
    const raw = localStorage.getItem(STATE_KEY);
    if (raw) {
      const s = JSON.parse(raw) as Partial<PersistedState>;
      return {
        slug: typeof s.slug === "string" ? s.slug : null,
        step: Number.isInteger(s.step) ? (s.step as number) : 0,
        minimized: s.minimized === true,
      };
    }
  } catch {
    // localStorage indisponible ou corrompu.
  }
  return { slug: null, step: 0, minimized: false };
}

/**
 * Découpe un tutoriel Markdown en étapes : chaque `## …` ouvre une étape.
 * Le `# Titre` est retiré (le panneau l'affiche). Un éventuel texte d'introduction est replié dans
 * la première étape. Sans `##`, le tutoriel n'a qu'une seule étape (title vide).
 */
export function splitSteps(md: string): TutorialStep[] {
  const [head, ...sections] = md.split(/^## /m);
  const intro = head.replace(/^# .*\n?/m, "").trim();
  if (sections.length === 0) return [{ title: "", html: renderMarkdown(intro) }];
  return sections.map((section, i) => {
    const [title, ...body] = section.split("\n");
    const text = (i === 0 && intro ? `${intro}\n\n` : "") + body.join("\n");
    return { title: title.trim(), html: renderMarkdown(text) };
  });
}

export function useTutorials() {
  const progress = computed(() => ({
    seen: seenSlugs.value.size,
    total: tutorials.value.length,
  }));

  const progressPercent = computed(() =>
    tutorials.value.length === 0
      ? 0
      : Math.round((seenSlugs.value.size / tutorials.value.length) * 100),
  );

  function isSeen(slug: string): boolean {
    return seenSlugs.value.has(slug);
  }

  function markSeen(slug: string) {
    if (!seenSlugs.value.has(slug)) {
      seenSlugs.value = new Set([...seenSlugs.value, slug]);
      persistSeen();
    }
  }

  function resetProgress() {
    seenSlugs.value = new Set();
    persistSeen();
  }

  async function load(slug: string, step = 0) {
    const tutorial = tutorials.value.find((t) => t.slug === slug);
    if (!tutorial) return;

    const token = ++loadToken;
    currentSlug.value = slug;
    loading.value = true;
    error.value = "";
    steps.value = [];

    try {
      const res = await fetch(tutorial.url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const parsed = splitSteps(await res.text());
      if (token !== loadToken) return;
      steps.value = parsed;
      // L'étape sauvegardée peut dépasser si le Markdown a changé : on la borne.
      stepIndex.value = Math.min(Math.max(step, 0), parsed.length - 1);
      markSeen(slug);
    } catch {
      if (token === loadToken) {
        error.value = "Impossible de charger ce tutoriel. Réessayez plus tard.";
      }
    } finally {
      if (token === loadToken) loading.value = false;
    }
  }

  /** Ouvre le panneau. Sans argument : reprend le tutoriel et l'étape en cours, ou affiche la liste. */
  async function openPanel(slug?: string) {
    panelOpen.value = true;
    minimized.value = false;
    if (slug && slug !== currentSlug.value) return load(slug);
    // Rechargement de page : on a le slug et l'étape sauvegardés, mais pas encore le contenu.
    if (currentSlug.value && steps.value.length === 0) return load(currentSlug.value, stepIndex.value);
  }

  /** Ferme le panneau SANS perdre le tutoriel ni l'étape. */
  function closePanel() {
    panelOpen.value = false;
  }

  function toggleMinimize() {
    minimized.value = !minimized.value;
  }

  const currentStep = computed(() => steps.value[stepIndex.value]);
  const isLastStep = computed(() => stepIndex.value >= steps.value.length - 1);
  const next = () => { if (!isLastStep.value) stepIndex.value++; };
  const prev = () => { if (stepIndex.value > 0) stepIndex.value--; };

  /** Retour à la liste : le seul endroit qui « oublie » le tutoriel en cours. */
  function leaveTutorial() {
    loadToken++; // annule un chargement éventuellement en cours
    currentSlug.value = null;
    steps.value = [];
    stepIndex.value = 0;
    error.value = "";
    loading.value = false;
  }

  return {
    tutorials,
    currentSlug,
    steps,
    stepIndex,
    currentStep,
    isLastStep,
    loading,
    error,
    panelOpen,
    minimized,
    progress,
    progressPercent,
    isSeen,
    markSeen,
    resetProgress,
    load,
    openPanel,
    closePanel,
    toggleMinimize,
    leaveTutorial,
    next,
    prev,
  };
}
