import { ref } from "vue";

import type { DossierPresentation } from "@/types/dossierPresentation";

// La présentation d'un dossier, en tête de sa conversation. Pour l'instant des données simulées, avec plusieurs
// scénarios pour voir tous les états ; la signature (`load()`, `presentation`, `error`) est celle qu'aura la lecture de
// l'API, pour que les composants n'aient pas à changer.

export type MockScenario = "ready" | "pending" | "failed" | "no-suggestions";

const READY: DossierPresentation = {
  status: "ready",
  dossierName: "Dossier Martin — demande de logement",
  summary:
    "Mme Camille Martin demande un logement social pour elle et ses deux enfants. Le dossier est **complet** : pièce " +
    "d'identité valide, avis d'imposition 2024 et justificatif de domicile récent. Les revenus déclarés sont de " +
    "**27 480 €** pour l'année, soit un niveau compatible avec le plafond PLUS pour une famille de trois personnes [1]. " +
    "Deux points demandent un regard : la date de naissance de l'un des enfants diffère entre le livret de famille et " +
    "l'avis d'imposition, et le justificatif de domicile date de plus de trois mois [2].",
  classification: { label: "Demande de logement social", confidence: 94 },
  entities: [
    { name: "Demandeur", value: "Camille Martin", page: 1 },
    { name: "Date de naissance", value: "12 mars 1987", page: 1 },
    { name: "Composition du foyer", value: "3 personnes", page: 2 },
    { name: "Revenu fiscal de référence", value: "27 480 €", page: 4 },
    { name: "Adresse actuelle", value: "14 rue des Lilas, 69003 Lyon", page: 6 },
    { name: "Date du justificatif de domicile", value: "2 juin 2025", page: 6 },
    { name: "Numéro fiscal", value: "13 05 123 456 789", page: 4 },
  ],
  agents: [
    {
      name: "Juriste",
      output:
        "Le dossier respecte les conditions d'éligibilité : **résidence régulière**, revenus sous le plafond PLUS, " +
        "composition du foyer établie. Aucune pièce obligatoire ne manque.",
    },
    {
      name: "Contrôle de cohérence",
      output:
        "Deux écarts à vérifier :\n\n- la date de naissance de l'enfant aîné est le **4 mai 2015** sur le livret de " +
        "famille et le **4 mai 2016** sur l'avis d'imposition ;\n- le justificatif de domicile date de **plus de trois " +
        "mois**.",
    },
  ],
  documents: [
    { id: "d1", name: "carte-identite.pdf", label: "Carte d'identité", pageCount: 2 },
    { id: "d2", name: "livret-de-famille.pdf", label: "Livret de famille", pageCount: 3 },
    { id: "d3", name: "avis-imposition-2024.pdf", label: "Avis d'imposition", pageCount: 2 },
    { id: "d4", name: "facture-electricite.pdf", label: "Justificatif de domicile", pageCount: 1 },
  ],
  suggestions: [
    {
      id: "q1",
      question: "Quel est le revenu fiscal de référence du foyer ?",
      answer:
        "Le revenu fiscal de référence du foyer est de **27 480 €** pour l'année 2024 [1]. Il est identique sur " +
        "l'avis d'imposition et sur la déclaration annexée [2].",
      sources: [
        { id: "s1", number: 1, excerpt: "Revenu fiscal de référence : 27 480 €", pages: [{ id: "p4", pageNumber: 4 }] },
        { id: "s2", number: 2, excerpt: "Revenus 2024 du foyer : 27 480 €", pages: [{ id: "p5", pageNumber: 5 }] },
      ],
    },
    {
      id: "q2",
      question: "Les pièces d'identité sont-elles valides ?",
      answer:
        "La carte d'identité de Mme Martin est **valide jusqu'au 18 septembre 2031** [1]. Le livret de famille " +
        "n'a pas de date de validité.",
      sources: [
        { id: "s3", number: 1, excerpt: "Carte nationale d'identité — valable jusqu'au 18.09.2031", pages: [{ id: "p1", pageNumber: 1 }] },
      ],
    },
    {
      id: "q3",
      question: "Y a-t-il des incohérences entre les pièces ?",
      answer:
        "Oui, une : la date de naissance de l'enfant aîné est le **4 mai 2015** sur le livret de famille [1] et le " +
        "**4 mai 2016** sur l'avis d'imposition [2].",
      sources: [
        { id: "s4", number: 1, excerpt: "Né le 4 mai 2015 à Lyon", pages: [{ id: "p2", pageNumber: 2 }] },
        { id: "s5", number: 2, excerpt: "Enfant à charge : né en 2016", pages: [{ id: "p4", pageNumber: 4 }] },
      ],
    },
    {
      id: "q4",
      question: "Le justificatif de domicile est-il récent ?",
      answer: "Non : il date du **2 juin 2025**, soit plus de trois mois avant le dépôt du dossier [1].",
      sources: [{ id: "s6", number: 1, excerpt: "Facture du 2 juin 2025", pages: [{ id: "p6", pageNumber: 6 }] }],
    },
  ],
};

const SCENARIOS: Record<MockScenario, DossierPresentation> = {
  ready: READY,
  "no-suggestions": { ...READY, suggestions: [] },
  pending: {
    status: "pending",
    dossierName: READY.dossierName,
    entities: [],
    agents: [],
    documents: READY.documents,
    suggestions: [],
  },
  failed: {
    status: "failed",
    error: "L'analyse n'a pas pu aller à son terme : le service de lecture des documents ne répond pas.",
    dossierName: READY.dossierName,
    entities: [],
    agents: [],
    documents: READY.documents,
    suggestions: [],
  },
};

export function useDossierPresentation(_dossierId: string) {
  const presentation = ref<DossierPresentation | null>(null);
  const error = ref("");

  /** `scenario` ne sert qu'aux données simulées : la lecture de l'API n'en aura pas. */
  async function load(scenario: MockScenario = "ready") {
    error.value = "";
    await new Promise((resolve) => setTimeout(resolve, 120));
    presentation.value = SCENARIOS[scenario];
  }

  return { presentation, error, load };
}
