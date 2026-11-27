/** Maquette : les entités définies dans les analyses (l'API les lira dans les analyses réelles). */
import type { CatalogEntity, RuleCriterion, SharedKind } from "@/types/crossSearch";
import type { EntityType } from "@/types/analyse";

/** `kind` ne sert qu'à la maquette : il dit quelles données fictives correspondent à l'entité. */
export type MockEntity = CatalogEntity & { kind: SharedKind };

const entity = (analyseName: string, name: string, kind: SharedKind, type: EntityType = "texte"): MockEntity => ({
  id: `${analyseName} › ${name}`,
  analyseName,
  name,
  type,
  kind,
});

export const ENTITY_CATALOG: MockEntity[] = [
  entity("Titre de séjour", "Nom du demandeur", "person"),
  entity("Titre de séjour", "Adresse", "address"),
  entity("Titre de séjour", "Employeur", "company"),
  entity("Regroupement familial", "Nom du demandeur", "person"),
  entity("Regroupement familial", "Adresse du foyer", "address"),
  entity("Permis de conduire", "Titulaire du permis", "person"),
  entity("Permis de conduire", "Numéro de permis", "identifier", "identifiant"),
  entity("Infractions routières", "Conducteur désigné", "person"),
  entity("Infractions routières", "Numéro de permis", "identifier", "identifiant"),
  entity("Infractions routières", "Société titulaire", "company"),
  entity("Carte d'agent de sécurité", "Nom de l'agent", "person"),
  entity("Carte d'agent de sécurité", "Adresse", "address"),
  entity("Licence de transport", "Gérant", "person"),
  entity("Licence de transport", "Société", "company"),
];

/** Un critère prêt à l'emploi réunissant toutes les entités d'une même nature. */
export const allOfKind = (kind: SharedKind, name: string): RuleCriterion => ({
  id: `all-${kind}`,
  origin: "analysis",
  name,
  entityIds: ENTITY_CATALOG.filter((e) => e.kind === kind).map((e) => e.id),
});

/** D'où vient l'entité d'une nature donnée dans un dossier d'une analyse, telle qu'affichée avec la preuve. */
export function originOf(analyseName: string, kind: SharedKind): string | undefined {
  const found = ENTITY_CATALOG.find((e) => e.analyseName === analyseName && e.kind === kind);
  return found && `Analyse ${found.analyseName} · ${found.name}`;
}

/** Les analyses d'où viennent les entités d'un critère. */
export const analysesOf = (entityIds: string[]) => [
  ...new Set(ENTITY_CATALOG.filter((e) => entityIds.includes(e.id)).map((e) => e.analyseName)),
];
