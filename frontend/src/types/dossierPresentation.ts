import type { ChatWindowSource } from "@/components/ChatWindow.vue";

/**
 * Où en est la présentation d'un dossier : l'analyse n'est pas lancée (rien à montrer), elle tourne encore, elle est
 * prête, ou elle a échoué.
 */
export type PresentationStatus = "idle" | "pending" | "ready" | "failed";

export interface PresentationClassification {
  label: string;
  /** 0-100 ; absente quand la classification n'en donne pas. */
  confidence?: number;
}

export interface PresentationEntity {
  name: string;
  value: string;
  /** La page d'où vient la valeur, pour la citer. */
  page?: number;
}

export interface PresentationAgent {
  name: string;
  /** La synthèse de l'agent, en markdown. */
  output: string;
}

export interface PresentationDocument {
  id: string;
  name: string;
  /** Nature du document posée par la classification (« Carte d'identité »). */
  label?: string;
  pageCount: number;
}

/** Une question dont la réponse est déjà prête : elle s'affiche sans attendre le modèle, avec ses sources. */
export interface SuggestedQuestion {
  id: string;
  question: string;
  /** La réponse en markdown, avec ses citations ([1]). */
  answer: string;
  sources: ChatWindowSource[];
}

/** Ce que la conversation montre en tête : l'essentiel du dossier, le détail à un clic. */
export interface DossierPresentation {
  status: PresentationStatus;
  /** Le résumé ou les réponses prêtes se calculent encore : la présentation se recharge jusqu'à ce que tout y soit. */
  refreshing?: boolean;
  /** Le message d'erreur quand l'analyse a échoué. */
  error?: string;
  dossierName: string;
  /** Le résumé du dossier, en markdown. */
  summary?: string;
  classification?: PresentationClassification;
  entities: PresentationEntity[];
  agents: PresentationAgent[];
  documents: PresentationDocument[];
  suggestions: SuggestedQuestion[];
}
