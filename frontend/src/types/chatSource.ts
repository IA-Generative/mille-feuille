import type { ChatWindowSource } from "@/components/ChatWindow.vue";
import type { ExternalBox } from "@/types/knowledge";

/**
 * Une source citée par une réponse du chat, sous **une seule forme** : une page d'un document du dossier, ou un passage
 * d'une base de connaissances externe (document ou site web). Elle s'affiche sur une même carte.
 */
export interface ChatSource {
  /** Identifiant stable dans la liste (clé d'affichage). */
  key: string;
  /** Le numéro cité dans le texte ([2]) : une suite commune au dossier et à la base externe. */
  number: number;
  origin: "dossier" | "external";
  kind: "document" | "web";
  title: string;
  /** « page 3 », « pages 3, 4 » ; vide pour un site web. */
  pageLabel: string;
  /** Le passage cité ; vide si le fournisseur ou le worker n'en a pas gardé. */
  passage: string;
  /** Où il a été trouvé : la collection de la base externe ; vide pour le dossier. */
  context: string;
  /** Lien d'ouverture d'une source externe ; vide pour le dossier (la modale de la page s'ouvre). */
  url: string | null;
  /** L'aperçu d'une source externe ; le dossier charge la capture de sa page. */
  previewUrl: string | null;
  /** Zones à surligner sur l'aperçu, normalisées 0..1. */
  boxes: ExternalBox[];
  /** Pour une page du dossier : de quoi charger sa capture et rouvrir la modale. */
  dossier: { source: ChatWindowSource; documentId: string; pageId: string } | null;
}
