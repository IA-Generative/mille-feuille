import type { CustomField } from "@/types/tracking";
export type EntityType = "texte" | "date" | "nombre" | "booléen" | "identifiant";

export type AgentTool =
  | "lecture_document"
  | "recherche_web"
  | "base_connaissances"
  | "appel_agent"
  | "calculatrice"
  | "verification_coherence";

export const AGENT_TOOL_LABELS: Record<AgentTool, string> = {
  lecture_document: "Lecture de document",
  recherche_web: "Recherche web",
  base_connaissances: "Base de connaissances",
  appel_agent: "Appel à un autre agent",
  calculatrice: "Calculatrice",
  verification_coherence: "Vérification de cohérence",
};

/** Un instantané d'une valeur passée, horodaté, pour permettre une restauration. */
export interface Version<T> {
  id: string;
  content: T;
  createdAt: string;
}

export type PromptVersion = Version<string>;

export interface LabelDefinition {
  id: string;
  name: string;
  definition: string;
}

export interface EntityDefinition {
  id: string;
  name: string;
  definition: string;
  type: EntityType;
}

/**
 * Classification documentaire : une analyse simple (un prompt appliqué
 * systématiquement à tous les documents du dossier, pas un agent) qui
 * retourne un label parmi ceux définis ici, avec un score de confiance.
 * Un seul jeu de labels par analyse.
 */
export interface Classification {
  prompt: string;
  promptVersions: PromptVersion[];
  labels: LabelDefinition[];
  labelsVersions: Version<LabelDefinition[]>[];
}

/**
 * Extraction d'entités nommées : même principe que la classification,
 * un seul jeu d'entités à extraire par analyse.
 */
export interface Extraction {
  prompt: string;
  promptVersions: PromptVersion[];
  entities: EntityDefinition[];
  entitiesVersions: Version<EntityDefinition[]>[];
}

/**
 * Un agent est créé librement par l'utilisateur pour un but métier propre
 * à l'analyse (contrôle de cohérence, rédaction, construction d'une
 * timeline...) : nom, prompt et outils, sans capacité prédéfinie.
 */
export interface Agent {
  id: string;
  name: string;
  prompt: string;
  promptVersions: PromptVersion[];
  tools: AgentTool[];
  toolsVersions: Version<AgentTool[]>[];
  /** Si vrai, le résultat de cet agent est présenté comme une sortie visible dans la page de résultat du dossier. */
  output: boolean;
  outputVersions: Version<boolean>[];
  /** Identifiant de modèle (voir GET /api/models) ; null = pas de préférence, le hub par défaut sera utilisé. */
  model: string | null;
  modelVersions: Version<string | null>[];
}

/**
 * Statut de dossier défini par une analyse (issue #168). Distinct du statut
 * d'exécution d'un dossier : c'est l'avancement du traitement (À instruire,
 * En instruction…). Un statut garde son identifiant quand on modifie la liste.
 */
export interface WorkflowStatus {
  id: string;
  name: string;
  /** Couleur d'affichage, au format #RRGGBB. */
  color: string;
  position: number;
  /** Statut reçu à la création du dossier (un seul par analyse). */
  isInitial: boolean;
  /** Le dossier est clos dans ce statut (il reçoit une date de clôture). */
  isFinal: boolean;
}

/** Statut en cours d'édition : `id` absent tant qu'il n'a pas été enregistré. */
export type StatusDraft = Omit<WorkflowStatus, "id" | "position"> & { id: string | null };

/** Échéance des dossiers d'une analyse (#172) : durée par défaut et couleurs selon le temps restant. */
export interface DueSettings {
  /** Durée par défaut en jours depuis la création ; null = pas d'échéance automatique. */
  defaultDueDays: number | null;
  thresholds: DueThresholds;
}

export interface DueThresholds {
  /** Couleur quand l'échéance est loin. */
  farColor: string;
  /** « N jours restants ou moins » prend la couleur du seuil ; du plus large au plus serré. */
  steps: { days: number; color: string }[];
  overdueColor: string;
}

export interface Analyse {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  /** Version courante (v1, v2...) ; un dossier garde celle de son dernier lancement. */
  version: string;
  classification: Classification;
  extraction: Extraction;
  statuses: WorkflowStatus[];
  statusesVersions: Version<WorkflowStatus[]>[];
  dueSettings: DueSettings;
  dueSettingsVersions: Version<DueSettings>[];
  /** Colonnes personnalisées du suivi (#173) et leur historique. */
  customFields: CustomField[];
  customFieldsVersions: Version<CustomField[]>[];
  agents: Agent[];
}

/** Version allégée renvoyée par la liste des analyses (GET /api/analyses). */
export interface AnalyseSummary {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  agentCount: number;
  /** Statuts de dossier de l'analyse : la liste des dossiers s'en sert pour son filtre (#170). */
  statuses: WorkflowStatus[];
}
