/**
 * Regroupement des sections d'une analyse en quatre entrées de premier niveau. Chaque section reste une route
 * enfant de `analyse-detail` (liens directs conservés) ; le groupe actif se déduit du nom de la route.
 */
export interface AnalyseSection {
  title: string;
  /** Question à laquelle répond la section, affichée dans l'assistant pas à pas. */
  hint: string;
  routeName: string;
}

export interface AnalyseGroup {
  id: string;
  title: string;
  icon: string;
  sections: AnalyseSection[];
  adminOnly?: boolean;
}

export const ANALYSE_GROUPS: AnalyseGroup[] = [
  {
    id: "dossier",
    title: "Analyse du dossier",
    icon: "ri-price-tag-3-line",
    sections: [
      { title: "Classification documentaire", hint: "Comment reconnaître le type de chaque pièce jointe ?", routeName: "analyse-classification" },
      { title: "Extraction d'entités", hint: "Quelles informations extraire de chaque pièce ?", routeName: "analyse-extraction" },
      { title: "Agents", hint: "Quelles analyses l'IA doit-elle mener sur le dossier ?", routeName: "analyse-agents" },
    ],
  },
  {
    id: "lecture",
    title: "Lecture et recherche",
    icon: "ri-scan-2-line",
    sections: [
      { title: "Lecture", hint: "Comment lire les documents (OCR) ?", routeName: "analyse-ocr" },
      { title: "Recherche", hint: "Comment retrouver les passages utiles ?", routeName: "analyse-search" },
    ],
  },
  {
    id: "documents",
    title: "Documents",
    icon: "ri-file-word-2-line",
    adminOnly: true,
    sections: [{ title: "Documents", hint: "Quels modèles de document produire ?", routeName: "analyse-documents" }],
  },
  {
    id: "plus",
    title: "Plus",
    icon: "ri-more-2-line",
    sections: [
      { title: "Statuts et échéance", hint: "Quels statuts et quelle échéance pour un dossier ?", routeName: "analyse-statuses" },
      { title: "Sources", hint: "D'où viennent les fichiers du dossier ?", routeName: "analyse-sources" },
      { title: "Questions fréquentes", hint: "Quelles questions reviennent le plus souvent ?", routeName: "analyse-questions" },
      { title: "Suivi", hint: "Quelles colonnes suivre dans le tableau ?", routeName: "analyse-tracking" },
    ],
  },
];

export function visibleGroups(isAdmin: boolean): AnalyseGroup[] {
  return ANALYSE_GROUPS.filter((group) => !group.adminOnly || isAdmin);
}
