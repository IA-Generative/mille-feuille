/** Rectangle sur la page, coordonnées normalisées (0 à 1, origine en haut à gauche). */
export interface ExtractionBox {
  xMin: number;
  yMin: number;
  xMax: number;
  yMax: number;
}

/** Le texte brut de la page sur lequel repose une valeur, et son intervalle de caractères dans la page. */
export interface ExtractionPassage {
  text: string;
  charStart: number;
  charEnd: number;
}

export interface ExtractedEntity {
  id: string;
  name: string;
  value: string;
  confidence?: number;
  /** `textual` (LLM) ou `gliner`. */
  source: string;
  /** Numéros de toutes les pages de l'entité. */
  pages: number[];
  /** Où la valeur se trouve sur cette page ; vide si elle n'a pas pu être localisée. */
  boxes: ExtractionBox[];
  /** Texte brut de cette page sur lequel repose la valeur (sémantique : la valeur peut être reformulée). */
  passages: ExtractionPassage[];
}

export interface ExtractedPage {
  id: string;
  pageNumber: number;
  hasScreenshot: boolean;
  entities: ExtractedEntity[];
}

export interface ExtractedDocument {
  id: string;
  name: string;
  pages: ExtractedPage[];
}
