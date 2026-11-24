import type { RouteLocationRaw } from "vue-router";

/**
 * Regroupement des sections d'une analyse en quatre entrées de premier niveau. Chaque section reste une route
 * enfant de `analyse-detail` (liens directs conservés) ; le groupe actif se déduit du nom de la route.
 */
export interface AnalyseSection {
  title: string;
  /** Question à laquelle répond la section, affichée dans l'assistant pas à pas. */
  hint: string;
  /** Questions qui renvoient à une action visible sur la page (remplacent `hint` si présentes). */
  checks?: { label: string; optional?: boolean }[];
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
      { title: "Classification documentaire",
        hint: "Comment reconnaître le type de chaque pièce jointe ?",
        checks: [
          { label: "La méthode de classification a-t-elle été insérée dans le prompt ci-dessous ?" },
          { label: "Cette analyse a-t-elle ses labels de classification ?", optional: true }
        ],
        routeName: "analyse-classification" },
      { title: "Extraction d'entités",
        hint: "Quelles informations extraire de chaque pièce ?",
        checks: [
          { label: "La méthode d'extraction a-t-elle été insérée dans le prompt ci-dessous ?" },
          { label: "Les entités à extraire sont-elles définies dans la liste en dessous ?" },
        ],
        routeName: "analyse-extraction" },
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

/** Paramètre d'adresse qui active l'assistant pas à pas. Un seul mode : le parcours complet. */
export const GUIDE_QUERY = { guide: "all" } as const;

/** Les étapes du pas à pas : toutes les sections des onglets visibles, dans l'ordre des onglets (9, ou 10 pour un administrateur). */
export function guideSteps(isAdmin: boolean): AnalyseSection[] {
  return visibleGroups(isAdmin).flatMap((group) => group.sections);
}

/** Où envoyer la personne pour démarrer le pas à pas : la même route pour la création et pour le bouton. */
export function guideStartRoute(analyseId: string, isAdmin: boolean): RouteLocationRaw {
  return { name: guideSteps(isAdmin)[0].routeName, params: { id: analyseId }, query: GUIDE_QUERY };
}
