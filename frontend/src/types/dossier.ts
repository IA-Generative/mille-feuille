import type { WorkflowStatus } from "@/types/analyse";
import type { DocumentSource } from "@/types/documentSource";

export type DossierStatus = "en_attente" | "en_cours" | "terminé" | "arrêté" | "échec";

export const DOSSIER_STATUS_LABELS: Record<DossierStatus, string> = {
  en_attente: "En attente",
  en_cours: "En cours",
  terminé: "Terminé",
  arrêté: "Arrêté",
  échec: "Échec",
};

export type ExecutionStepStatus = "en_cours" | "terminé" | "échec";

export const EXECUTION_STEP_STATUS_LABELS: Record<ExecutionStepStatus, string> = {
  en_cours: "En cours",
  terminé: "Terminé",
  échec: "Échec",
};

export type ExecutionStepKind = "classification" | "extraction" | "agent";

export interface ExecutionStep {
  id: string;
  kind: ExecutionStepKind;
  label: string;
  status: ExecutionStepStatus;
  startedAt: string;
  endedAt?: string;
  /**
   * Résultat produit par l'étape, présenté dans la page de résultat.
   * Absent tant que l'étape n'est pas terminée, ou pour un agent dont la
   * sortie n'est pas activée (Agent.output === false).
   */
  output?: string;
}

export type TextExtractionStatus = "en_attente" | "en_cours" | "terminé" | "échec";

export const TEXT_EXTRACTION_STATUS_LABELS: Record<TextExtractionStatus, string> = {
  en_attente: "En attente",
  en_cours: "Extraction en cours",
  terminé: "Texte extrait",
  échec: "Échec de l'extraction",
};

export type SummaryStatus = "en_attente" | "en_cours" | "terminé" | "échec";

export const SUMMARY_STATUS_LABELS: Record<SummaryStatus, string> = {
  en_attente: "Résumé en attente",
  en_cours: "Résumé en cours",
  terminé: "Résumé généré",
  échec: "Échec du résumé",
};

export type SuggestionStatus = "en_attente" | "en_cours" | "terminé" | "échec";

export const SUGGESTION_STATUS_LABELS: Record<SuggestionStatus, string> = {
  en_attente: "Suggestion en attente",
  en_cours: "Suggestion en cours",
  terminé: "Suggestions prêtes",
  échec: "Échec de la suggestion",
};

/** Suggestion d'analyse pour un dossier « à ranger » (issue #54). */
export interface AnalyseSuggestion {
  analyseId: string;
  name: string;
  score: number;
  rationale: string;
}

/** Résumé d'un document ou d'un dossier (version append-only, la plus récente gagne). */
export interface Summary {
  id: string;
  content: string;
  model?: string;
  createdAt: string;
}

export interface DossierDocument {
  id: string;
  name: string;
  size: number;
  s3Key: string;
  mimetype: string;
  /** Nature du document (ex: "CNI") : posée par la classification ou corrigée manuellement. */
  label?: string;
  /** Suivi du run du worker document_process (extract_document_text). */
  textExtractionStatus: TextExtractionStatus;
  textExtractionError?: string;
  /** Hash SHA-256 du fichier (calculé par le worker document_process). */
  fileHash?: string;
  /** Date de dépôt : sert à repérer les fichiers ajoutés depuis le dernier lancement de l'analyse. */
  createdAt?: string;
  /** D'où vient le fichier ; absent s'il n'a pas de source (ou si sa source a été supprimée). */
  source?: DocumentSource;
  /** Suivi de la génération du résumé (issue #52). */
  summaryStatus: SummaryStatus;
  summaryError?: string;
  /** Dernier résumé généré avec succès, ou undefined si aucun. */
  summary?: Summary;
}

export type DueLevel = "ok" | "soon" | "overdue" | "closed";

export interface DueInfo {
  level: DueLevel;
  /** Jours restants, négatif si l'échéance est dépassée. */
  daysLeft: number;
  /** Couleur du niveau selon les seuils de l'analyse ; absente pour un dossier clos. */
  color?: string;
}

export interface Dossier {
  id: string;
  name: string;
  /** Statut de dossier défini par son analyse (#168) ; absent pour un dossier « à ranger ». */
  /** Qui voit le dossier (#177) : « restricted » (groupes associés) ou « analyse ». */
  visibility?: "restricted" | "analyse";
  workflowStatus?: WorkflowStatus;
  /** Date de clôture : posée quand le dossier entre dans un statut final. */
  closedAt?: string;
  /** Échéance (#172) : un jour du calendrier (AAAA-MM-JJ), absente si le dossier n'en a pas. */
  dueAt?: string;
  /** Situation par rapport à l'échéance, calculée par le serveur selon les seuils de l'analyse. */
  due?: DueInfo;
  /** Clos au plus tard le jour de l'échéance ; absent si la question ne se pose pas. */
  closedBeforeDue?: boolean;
  /**
   * Analyse rattachée au dossier. Optionnel : un dossier « à ranger » peut
   * être créé sans analyse, puis recevoir des suggestions via le LLM
   * (issue #54).
   */
  analyseId?: string;
  /** Version de l'analyse utilisée pour l'exécution (snapshot au lancement). */
  analyseVersion: string;
  createdAt: string;
  status: DossierStatus;
  startedAt?: string;
  endedAt?: string;
  executionSteps: ExecutionStep[];
  documents: DossierDocument[];
  /** Suivi de la génération du résumé global du dossier (issue #52). */
  summaryStatus: SummaryStatus;
  summaryError?: string;
  /** Dernier résumé global généré avec succès, ou undefined si aucun. */
  summary?: Summary;
  /** Suivi de la génération des suggestions d'analyse (issue #54). */
  suggestionStatus: SuggestionStatus;
  /** Suggestions d'analyse générées par le LLM, ou undefined si aucune. */
  suggestedAnalyses?: AnalyseSuggestion[];
}
