export type RunStatus = "en_attente" | "en_cours" | "terminé" | "arrêté" | "échec";
export type Mode = "classification" | "extraction";
export type EntityType = "texte" | "date" | "nombre" | "booléen" | "identifiant";

export interface LabelDef {
  name: string;
  definition: string;
}
export interface EntityDef extends LabelDef {
  type: EntityType;
}

export interface LabelResult {
  name: string;
  confidence: number | null;
  source: "textual" | "visual";
}
/** Rectangle sur la page, coordonnées normalisées (0 à 1, origine en haut à gauche). */
export interface Box {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}
export interface EntityResult {
  prediction_id?: string;
  name: string;
  value: string;
  confidence: number | null;
  source: "textual" | "gliner";
  pages: number[];
  /** Où la valeur se trouve sur cette page ; vide si elle n'a pas pu être localisée. */
  boxes: Box[];
}
export interface ExtractedPage {
  page_number: number;
  page_id: string;
  has_screenshot: boolean;
  entities: EntityResult[];
}
export interface ClassificationOut {
  run_id: string;
  status: RunStatus;
  error: string | null;
  expires_at: string | null;
  documents: { name: string; pages: { page_number: number; labels: LabelResult[] }[] }[];
}
export interface ExtractionOut {
  run_id: string;
  status: RunStatus;
  error: string | null;
  expires_at: string | null;
  documents: { name: string; pages: ExtractedPage[] }[];
}
export type RunOut = ClassificationOut | ExtractionOut;

export const TERMINAL: RunStatus[] = ["terminé", "arrêté", "échec"];

export interface RunSummary {
  id: string;
  kind: Mode | "analyse";
  status: RunStatus;
  documents: string[];
  persist: boolean;
  created_at: string;
  ended_at: string | null;
  expires_at: string | null;
}
