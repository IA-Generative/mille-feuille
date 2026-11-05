/** Ce qu'un modèle sait faire techniquement : le backend le lit sur le hub, personne ne le saisit. */
export type LlmType = "completion" | "embedding" | "audio" | "image" | "video";

export const TYPE_LABELS: Record<LlmType, string> = {
  completion: "Texte",
  embedding: "Embeddings",
  audio: "Audio",
  image: "Image",
  video: "Vidéo",
};

export const TYPE_ICONS: Record<LlmType, string> = {
  completion: "ri-chat-3-line",
  embedding: "ri-node-tree",
  audio: "ri-mic-line",
  image: "ri-image-line",
  video: "ri-movie-line",
};

/**
 * Une capacité que l'administrateur définit : un nom et une description, par exemple « Tâches lourdes » (capable de
 * raisonner sur plusieurs documents) ou « Outils » (capable de répondre en appelant des outils). Rien n'est déduit
 * du modèle : c'est l'administrateur qui dit ce que chaque modèle sait faire.
 */
export interface LlmCapability {
  id: string;
  name: string;
  description: string;
}

export interface LlmModel {
  id: string;
  /** Le nom du modèle, tel que le hub le renvoie. */
  name: string;
  /** Ce que le hub a révélé du modèle ; `null` : pas encore lu. */
  types: LlmType[] | null;
  /** Les capacités que l'administrateur lui a données. */
  capabilityIds: string[];
  /** Ordre de préférence : le premier modèle actif fait tout hors mode auto. */
  position: number;
  enabled: boolean;
}

/** Un modèle vu sur le hub : son nom et ses types ; l'administrateur dit le reste (ses capacités). */
export interface HubModel {
  name: string;
  types: LlmType[];
}

/** « first » : le premier modèle fait tout. « auto » : le modèle suit les capacités que la demande demande. */
export type RoutingMode = "first" | "auto";
