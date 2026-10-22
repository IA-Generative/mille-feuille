/**
 * Aperçu des écrans des tools qui ne sont pas encore reliés à l'API (docs/tools-mcp-plan.md) : sélecteur d'outils
 * d'un agent, bouton « Tester », collections de la base de connaissances.
 * Ils tournent sur des données simulées : masqués par défaut, `VITE_TOOLS_PREVIEW=true` les affiche (dev, captures).
 */
export const TOOLS_PREVIEW = import.meta.env.VITE_TOOLS_PREVIEW === "true";
