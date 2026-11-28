import { ref } from "vue";

import { MOCK_DOSSIERS, MOCK_ITEMS } from "@/composables/mockCrossSearch";
import { allOfKind, ENTITY_CATALOG } from "@/composables/mockEntityCatalog";
import {
  LINK_REASONS,
  type Occurrence,
  type Resemblance,
  type ResemblanceRule,
  type RuleCriterion,
  type RuleDraft,
  type SharedKind,
} from "@/types/crossSearch";

type Preset = [string, string, string, RuleCriterion[], RuleDraft["scope"], RuleDraft["certainty"]];

const person = allOfKind("person", "Personne");
const company = allOfKind("company", "Entreprise");
const identifier = allOfKind("identifier", "Numéro");

/** Maquette : des thèmes de ressemblance tels qu'un administrateur pourrait les définir. */
const PRESETS: Preset[] = [
  ["duplicate", "Dossiers possiblement en double", "La même demande a pu être déposée deux fois.", [person, identifier], "within", "probable"],
  ["person-across", "Personne dans plusieurs thèmes", "Une même personne suivie par des services différents.", [person], "across", "probable"],
  ["person-within", "Personne revenant dans un thème", "Plusieurs dossiers d'une même personne dans un même thème.", [person], "within", "probable"],
  ["driver-company", "Conducteur et employeur", "La même personne et la même entreprise.", [person, company], "all", "probable"],
  ["company", "Entreprise commune", "Des dossiers qui citent la même entreprise.", [company], "all", "probable"],
  ["address", "Adresse partagée", "La même adresse, sans que les personnes soient forcément liées.", [allOfKind("address", "Adresse")], "all", "to_check"],
  ["identifier", "Même numéro", "Permis, immatriculation ou pièce identique.", [identifier], "all", "identical"],
  ["file", "Fichier réutilisé", "Le même fichier déposé dans plusieurs dossiers.", [{ id: "file", origin: "file", name: "Même fichier" }], "all", "identical"],
];

/** Maquette : la nature des données fictives qui correspondent à un critère (aucune si elle est inconnue). */
export function mockKindOf(criterion: RuleCriterion): SharedKind | null {
  if (criterion.origin === "file") return "document";
  if (criterion.origin === "topic") return "topic";
  if (criterion.origin !== "analysis") return null;
  return ENTITY_CATALOG.find((e) => criterion.entityIds.includes(e.id))?.kind ?? null;
}

const rules = ref<ResemblanceRule[]>(
  PRESETS.map(([id, name, description, criteria, scope, certainty]) => ({
    id,
    name,
    description,
    criteria,
    scope,
    certainty,
    active: true,
    versions: [],
  })),
);

const themeOf = (dossierId: string) => MOCK_DOSSIERS.find((d) => d.id === dossierId)?.themeName ?? null;

interface Match {
  key: string;
  label: string;
  dossierIds: string[];
  occurrences: Occurrence[];
}

/** Les valeurs trouvées pour un critère, dans les seuls dossiers des analyses dont il cite des entités. */
function valuesOf(criterion: RuleCriterion): Match[] {
  const kind = mockKindOf(criterion);
  const analyses =
    criterion.origin === "analysis"
      ? ENTITY_CATALOG.filter((e) => criterion.entityIds.includes(e.id)).map((e) => e.analyseName)
      : null;
  const concerns = (id: string) => !analyses || analyses.includes(MOCK_DOSSIERS.find((d) => d.id === id)!.analyseName!);

  return MOCK_ITEMS.filter((item) => item.kind === kind).map((item) => ({
    key: item.id,
    label: item.label,
    dossierIds: item.dossierIds.filter(concerns),
    occurrences: item.occurrences.filter((o) => concerns(o.dossierId)),
  }));
}

/** Les dossiers qui réunissent tous les critères d'un thème. */
function matches(rule: ResemblanceRule): Match[] {
  const [first, ...others] = rule.criteria.map(valuesOf);
  return others.reduce<Match[]>(
    (found, items) =>
      found.flatMap((match) =>
        items.map((item) => {
          const dossierIds = match.dossierIds.filter((id) => item.dossierIds.includes(id));
          return {
            key: `${match.key}+${item.key}`,
            label: `${match.label} + ${item.label}`,
            dossierIds,
            occurrences: [...match.occurrences, ...item.occurrences].filter((o) => dossierIds.includes(o.dossierId)),
          };
        }),
      ),
    first ?? [],
  );
}

/** La portée : découper par thème d'analyse, ou n'accepter que ce qui en traverse plusieurs. */
function scoped(rule: ResemblanceRule, match: Match): Match[] {
  const themes = [...new Set(match.dossierIds.map(themeOf))];
  if (rule.scope === "across") return themes.length > 1 ? [match] : [];
  if (rule.scope === "all") return [match];
  return themes.map((theme) => {
    const dossierIds = match.dossierIds.filter((id) => themeOf(id) === theme);
    return {
      key: `${match.key}@${theme}`,
      label: `${match.label} · ${theme ?? "Sans thème"}`,
      dossierIds,
      occurrences: match.occurrences.filter((o) => dossierIds.includes(o.dossierId)),
    };
  });
}

/** Maquette : ce que l'analyse préalable aurait trouvé. L'API ne renverra que les dossiers visibles de la personne. */
export function mockResemblances(rule: ResemblanceRule): Resemblance[] {
  const kinds = rule.criteria.map(mockKindOf);
  const caution = [...new Set(kinds.flatMap((kind) => (kind && LINK_REASONS[kind].caution) || []))].join(" ");
  const reason = `En commun : ${rule.criteria.map((c) => c.name.toLowerCase()).join(" et ")}.`;

  return matches(rule)
    .flatMap((match) => scoped(rule, match))
    .filter((match) => match.dossierIds.length > 1)
    .map((match) => ({
      id: `${rule.id}:${match.key}`,
      ruleId: rule.id,
      label: match.label,
      certainty: rule.certainty,
      reason,
      caution: caution || undefined,
      dossierIds: match.dossierIds,
      occurrences: match.occurrences,
    }))
    .sort((a, b) => b.dossierIds.length - a.dossierIds.length);
}

/** Copie indépendante : les critères sont des objets, l'historique ne doit pas suivre les modifications. */
export const draftOf = ({ name, description, criteria, scope, certainty, active }: RuleDraft): RuleDraft => ({
  name,
  description,
  criteria: JSON.parse(JSON.stringify(criteria)) as RuleCriterion[],
  scope,
  certainty,
  active,
});

export function useResemblances() {
  /** Crée ou modifie un thème ; l'état précédent est gardé dans l'historique. */
  function saveRule(draft: RuleDraft, id?: string) {
    const rule = rules.value.find((r) => r.id === id);
    if (!rule) {
      const created = { ...draftOf(draft), id: `rule-${Date.now()}`, versions: [] };
      rules.value = [...rules.value, created];
      return created.id;
    }
    const previous = { id: `v-${Date.now()}-${rule.versions.length}`, content: draftOf(rule), createdAt: new Date().toISOString() };
    Object.assign(rule, draftOf(draft), { versions: [previous, ...rule.versions] });
    return rule.id;
  }

  function restoreRule(id: string, versionId: string) {
    const version = rules.value.find((r) => r.id === id)?.versions.find((v) => v.id === versionId);
    if (version) saveRule(version.content, id);
  }

  const removeRule = (id: string) => (rules.value = rules.value.filter((r) => r.id !== id));

  return { rules, saveRule, restoreRule, removeRule };
}
