/** Données FICTIVES des rapprochements, encore en maquette : à remplacer par l'API (aucune personne ni entreprise réelle). */
import { originOf } from "@/composables/mockEntityCatalog";
import type { FoundDossier, HiddenLinks, SharedItem, SharedKind } from "@/types/crossSearch";

function dossier(
  id: string,
  number: number,
  name: string,
  analyseName: string,
  themeName: string,
  excerpts: [string, number, string][],
): FoundDossier {
  return {
    id,
    reference: `DOS-2026-${String(number).padStart(4, "0")}`,
    name,
    analyseName,
    themeName,
    excerpts: excerpts.map(([documentName, page, text]) => ({ documentName, page, text })),
  };
}

export const MOCK_DOSSIERS: FoundDossier[] = [
  dossier("d1", 12, "Titre de séjour — Camille Exemple", "Titre de séjour", "Séjour des étrangers", [
    ["justificatif_domicile.pdf", 1, "Camille Exemple réside au 12 rue des Lilas depuis le 3 mars."],
    ["contrat_travail.pdf", 2, "Employeur : Transports Fictifs, poste de chauffeur."],
  ]),
  dossier("d2", 31, "Regroupement familial — Sacha Exemple", "Regroupement familial", "Séjour des étrangers", [
    ["demande.pdf", 1, "Le demandeur, Sacha Exemple, déclare habiter au 12 rue des Lilas."],
  ]),
  dossier("d3", 48, "Échange de permis — Camille Exemple", "Permis de conduire", "Sécurité routière", [
    ["permis_origine.pdf", 1, "Permis délivré à Camille Exemple, numéro PERMIS-000123."],
  ]),
  dossier("d4", 57, "Contravention — véhicule AA-123-AA", "Infractions routières", "Sécurité routière", [
    ["avis.pdf", 1, "Véhicule AA-123-AA au nom de la société Transports Fictifs."],
    ["courrier.pdf", 1, "Le conducteur désigné est Camille Exemple, permis PERMIS-000123."],
  ]),
  dossier("d5", 63, "Carte professionnelle — Dominique Modèle", "Carte d'agent de sécurité", "Sécurité privée", [
    ["attestation.pdf", 1, "Dominique Modèle, hébergé au 12 rue des Lilas."],
  ]),
  dossier("d6", 70, "Autorisation d'exercer — Transports Fictifs", "Licence de transport", "Sécurité routière", [
    ["kbis.pdf", 1, "Transports Fictifs, gérant : Dominique Modèle."],
  ]),
  // Le même échange de permis déposé une seconde fois.
  dossier("d7", 84, "Échange de permis (second dépôt) — Camille Exemple", "Permis de conduire", "Sécurité routière", [
    ["permis_origine.pdf", 1, "Permis délivré à Camille Exemple, numéro PERMIS-000123."],
  ]),
];

function item(id: string, kind: SharedKind, label: string, found: [string, string, number, string][]): SharedItem {
  return {
    id,
    kind,
    label,
    dossierIds: found.map(([dossierId]) => dossierId),
    occurrences: found.map(([dossierId, documentName, page, text]) => ({
      dossierId,
      documentName,
      page,
      text,
      origin: originOf(MOCK_DOSSIERS.find((d) => d.id === dossierId)!.analyseName!, kind),
    })),
  };
}

export const MOCK_ITEMS: SharedItem[] = [
  item("p-camille", "person", "Camille Exemple", [
    ["d1", "justificatif_domicile.pdf", 1, "Camille Exemple réside au 12 rue des Lilas depuis le 3 mars."],
    ["d3", "permis_origine.pdf", 1, "Permis délivré à Camille Exemple, numéro PERMIS-000123."],
    ["d4", "courrier.pdf", 1, "Le conducteur désigné est Camille Exemple, permis PERMIS-000123."],
    ["d7", "permis_origine.pdf", 1, "Permis délivré à Camille Exemple, numéro PERMIS-000123."],
  ]),
  item("p-dominique", "person", "Dominique Modèle", [
    ["d5", "attestation.pdf", 1, "Dominique Modèle, hébergé au 12 rue des Lilas."],
    ["d6", "kbis.pdf", 1, "Transports Fictifs, gérant : Dominique Modèle."],
  ]),
  item("c-transports", "company", "Transports Fictifs", [
    ["d1", "contrat_travail.pdf", 2, "Employeur : Transports Fictifs, poste de chauffeur."],
    ["d4", "avis.pdf", 1, "Véhicule AA-123-AA au nom de la société Transports Fictifs."],
    ["d6", "kbis.pdf", 1, "Transports Fictifs, gérant : Dominique Modèle."],
  ]),
  item("a-lilas", "address", "12 rue des Lilas", [
    ["d1", "justificatif_domicile.pdf", 1, "Camille Exemple réside au 12 rue des Lilas depuis le 3 mars."],
    ["d2", "demande.pdf", 1, "Le demandeur, Sacha Exemple, déclare habiter au 12 rue des Lilas."],
    ["d5", "attestation.pdf", 1, "Dominique Modèle, hébergé au 12 rue des Lilas."],
  ]),
  item("i-permis", "identifier", "PERMIS-000123", [
    ["d3", "permis_origine.pdf", 1, "Permis délivré à Camille Exemple, numéro PERMIS-000123."],
    ["d4", "courrier.pdf", 1, "Le conducteur désigné est Camille Exemple, permis PERMIS-000123."],
    ["d7", "permis_origine.pdf", 1, "Permis délivré à Camille Exemple, numéro PERMIS-000123."],
  ]),
  item("f-attestation", "document", "attestation_hebergement.pdf", [
    ["d2", "attestation_hebergement.pdf", 1, "Je soussigné atteste héberger la personne désignée ci-après."],
    ["d5", "attestation_hebergement.pdf", 1, "Je soussigné atteste héberger la personne désignée ci-après."],
  ]),
  item("t-transport", "topic", "Transport routier", [
    ["d4", "avis.pdf", 1, "Véhicule AA-123-AA au nom de la société Transports Fictifs."],
    ["d6", "licence.pdf", 3, "Demande d'autorisation de transport routier de marchandises."],
  ]),
];

export const mockDossiersByIds = (ids: string[]) =>
  ids.flatMap((id) => MOCK_DOSSIERS.filter((dossier) => dossier.id === id));

export const MOCK_HIDDEN: HiddenLinks[] = [
  { themeName: "Séjour des étrangers", count: 2, dossierIds: ["d1", "d2"] },
  { themeName: "Sécurité routière", count: 3, dossierIds: ["d4", "d6"] },
];
