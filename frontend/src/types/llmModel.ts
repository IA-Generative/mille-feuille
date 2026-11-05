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
  /** Les capacités que l'administrateur lui a données. */
  capabilityIds: string[];
  /** Ordre de préférence : le premier modèle actif fait tout hors mode auto. */
  position: number;
  enabled: boolean;
}

/** Un modèle vu sur le hub : son nom seulement, l'administrateur dit le reste. */
export interface HubModel {
  name: string;
}

/** « first » : le premier modèle fait tout. « auto » : le modèle suit les capacités que la demande demande. */
export type RoutingMode = "first" | "auto";
