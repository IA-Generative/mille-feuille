// Configuration lue au démarrage du conteneur, pas figée au build : `/config.js` est généré par nginx à partir des
// variables d'environnement (API_BASE_URL, MILLEFEUILLE_URL), ce qui permet une seule image pour tous les
// environnements. En développement (Vite), `public/config.js` est vide et les variables VITE_* servent de repli.
interface RuntimeConfig {
  /** Adresse du backend (vide = même hôte). Doit être celle de MilleFeuille si l'hôte de ce frontend est différent :
   *  c'est là que le cookie de session est posé. */
  apiBaseUrl?: string;
  /** Adresse du frontend MilleFeuille complet, pour le lien de renvoi (vide = pas de lien). */
  millefeuilleUrl?: string;
}

const runtime: RuntimeConfig = (window as unknown as { __CONFIG__?: RuntimeConfig }).__CONFIG__ ?? {};

export const API_BASE_URL: string = (runtime.apiBaseUrl || import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
export const MILLEFEUILLE_URL: string = runtime.millefeuilleUrl || import.meta.env.VITE_MILLEFEUILLE_URL || "";
