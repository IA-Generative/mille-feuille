import type { EntityType, Version } from "@/types/analyse";

/** Recherche à travers les dossiers : résultats, liens entre eux et signalement des dossiers non accessibles. */

/** Ce que des dossiers ont en commun. */
/** Le serveur fournit `identifier`, `value` et `document` ; les autres ne servent qu'aux rapprochements en maquette. */
export type SharedKind = "person" | "company" | "address" | "identifier" | "value" | "document" | "topic";

export interface Excerpt {
  documentName: string | null;
  page: number | null;
  text: string;
  /** Les morceaux surlignés de `text`, quand le serveur les donne. */
  segments?: { text: string; highlighted: boolean }[];
  /** Nom de l'entité ou du champ, pour une valeur extraite. */
  field?: string | null;
}

export interface FoundDossier {
  id: string;
  reference: string;
  name: string;
  analyseName: string | null;
  themeName: string | null;
  excerpts: Excerpt[];
}

/** La preuve d'un lien : où le point commun apparaît dans un dossier. */
export interface Occurrence extends Excerpt {
  dossierId: string;
  /** D'où vient l'entité trouvée : « Analyse X · nom de l'entité ». Absent pour un fichier ou un sujet. */
  origin?: string;
}

/** Ce qui est sélectionné : un nœud, un trait du graphe, ou deux dossiers à comparer. */
export type Selection =
  | { type: "node"; id: string }
  | { type: "link"; dossierId: string; targetId: string }
  | { type: "pair"; dossierIds: [string, string] };

export interface SharedItem {
  id: string;
  kind: SharedKind;
  label: string;
  /** Écritures différentes rapprochées : à vérifier, jamais une identité. */
  uncertain?: boolean;
  /** Dossiers accessibles, parmi les résultats, qui le partagent (au moins deux). */
  dossierIds: string[];
  occurrences: Occurrence[];
}

/** Dossiers non accessibles liés aux résultats : un nombre par thème, jamais un nom ni un motif. */
export interface HiddenLinks {
  themeName: string | null;
  count: number;
  /** Les résultats accessibles auxquels ils sont liés. */
  dossierIds: string[];
}

export interface CrossSearchResult {
  query: string;
  /** Dossiers choisis comme point de départ ; vide pour une recherche par mots-clés. */
  anchorIds: string[];
  dossiers: FoundDossier[];
  items: SharedItem[];
  hidden: HiddenLinks[];
}

export const SHARED_KINDS: { value: SharedKind; label: string; color: string }[] = [
  { value: "person", label: "Personnes", color: "#e4794a" },
  { value: "company", label: "Entreprises", color: "#a558a0" },
  { value: "address", label: "Adresses", color: "#00a95f" },
  { value: "identifier", label: "Identifiants", color: "#c3992a" },
  { value: "value", label: "Valeurs communes", color: "#e4794a" },
  { value: "document", label: "Documents identiques", color: "#009099" },
  { value: "topic", label: "Sujets communs", color: "#8585a0" },
];

/** Portée d'un thème de ressemblance par rapport aux thèmes d'analyse. */
export type Scope = "all" | "within" | "across";

export const SCOPES: Record<Scope, { label: string; short: string }> = {
  all: { label: "Tous les dossiers", short: "Tous dossiers" },
  within: { label: "Au sein d'un même thème d'analyse", short: "Même thème" },
  across: { label: "Entre thèmes d'analyse différents", short: "Entre thèmes" },
};

/**
 * Une chose que les dossiers doivent avoir en commun :
 * - `analysis` : des entités définies dans les analyses, tenues pour équivalentes (« Nom du demandeur » ici,
 *   « Titulaire du permis » là) ;
 * - `file`, `topic` : le même fichier, ou un sujet proche (ce ne sont pas des entités).
 */
export type RuleCriterion =
  | { id: string; origin: "analysis"; name: string; entityIds: string[]; refusedIds?: string[] }
  | { id: string; origin: "file" | "topic"; name: string };

export const CRITERION_ORIGINS: Record<Exclude<RuleCriterion["origin"], "analysis">, string> = {
  file: "Fichier",
  topic: "Sujet",
};

/** Une entité telle qu'une analyse la définit. */
export interface CatalogEntity {
  id: string;
  analyseName: string;
  name: string;
  type: EntityType;
}

/** Ce qu'un administrateur définit pour un thème de ressemblance. */
export interface RuleDraft {
  name: string;
  description: string;
  /** Ce que les dossiers doivent avoir en commun : tous les critères à la fois. */
  criteria: RuleCriterion[];
  scope: Scope;
  certainty: Certainty;
  active: boolean;
}

export interface ResemblanceRule extends RuleDraft {
  id: string;
  versions: Version<RuleDraft>[];
}

export type Certainty = "identical" | "probable" | "to_check";

/** Un groupe trouvé par l'analyse préalable. */
export interface Resemblance {
  id: string;
  ruleId: string;
  label: string;
  certainty: Certainty;
  reason: string;
  caution?: string;
  dossierIds: string[];
  occurrences: Occurrence[];
}

export const CERTAINTIES: Record<Certainty, { label: string; badge: string }> = {
  identical: { label: "Identique", badge: "fr-badge--success" },
  probable: { label: "Probable", badge: "fr-badge--info" },
  to_check: { label: "À vérifier", badge: "fr-badge--warning" },
};

/** Pourquoi un point commun relie des dossiers, et ce qu'il faut vérifier. */
export const LINK_REASONS: Record<SharedKind, { reason: string; caution?: string }> = {
  person: { reason: "La même personne est citée.", caution: "Même nom : à vérifier, il peut s'agir d'homonymes." },
  company: { reason: "La même entreprise est citée." },
  address: { reason: "La même adresse apparaît.", caution: "Une même adresse peut loger des personnes sans rapport." },
  identifier: { reason: "Le même identifiant apparaît." },
  value: {
    reason: "La même valeur apparaît.",
    caution: "À vérifier : une même valeur peut désigner des personnes ou des choses différentes.",
  },
  document: { reason: "Le même fichier a été déposé." },
  topic: { reason: "Les documents traitent d'un sujet commun.", caution: "Rapprochement par le sens, moins sûr." },
};

/** Bleu France ; les autres couleurs sont les teintes illustratives du DSFR. */
export const DOSSIER_COLOR = "#6a6af4";
/** Un dossier trouvé parce qu'il est lié à la sélection, sans en faire partie. */
export const RELATED_COLOR = "#9c9cc4";
export const HIDDEN_COLOR = "#929292";

/** L'explication d'un point commun, qui dit quand il n'est pas certain. */
export const reasonOf = (item: Pick<SharedItem, "kind" | "uncertain">): { reason: string; caution?: string } =>
  item.uncertain
    ? {
        reason: "Des écritures proches apparaissent.",
        caution:
          "Rapprochement incertain : ordre des mots, séparateurs, abréviations ou caractères confondus (O et 0, I, L et 1). Comparez les écritures.",
      }
    : LINK_REASONS[item.kind];
