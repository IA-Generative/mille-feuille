/** Un agent de l'analyse que la personne peut interroger dans le chat du dossier. */
export interface ChatAgent {
  /** Son nom, tel qu'il figure dans l'analyse. */
  name: string;
  /** Son rôle en une ligne (le début de son prompt). */
  role: string;
}
