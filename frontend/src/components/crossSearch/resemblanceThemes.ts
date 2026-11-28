/** L'apparence d'un thème de ressemblance et le résumé de ses groupes. */
import { KIND_ICONS } from "@/components/crossSearch/graphTheme";
import { CERTAINTIES, SCOPES, SHARED_KINDS, type Resemblance, type ResemblanceRule } from "@/types/crossSearch";

export interface ResemblanceTheme {
  value: string;
  label: string;
  color: string;
  icon: string;
  explanation: string;
}

/** Couleur et pictogramme disent la nature du premier critère ; l'explication, comment le rapprochement est fait. */
export function themeFor(rule: ResemblanceRule): ResemblanceTheme {
  const kind = rule.criteria[0]?.origin === "file" ? "document" : "value";
  const criteria = rule.criteria.map((c) => c.name.toLowerCase()).join(" et ");
  return {
    value: rule.id,
    label: rule.name,
    color: SHARED_KINDS.find((k) => k.value === kind)!.color,
    icon: KIND_ICONS[kind],
    explanation: `${rule.description} Réunit les dossiers ayant en commun : ${criteria}. Portée : ${SCOPES[rule.scope].label.toLowerCase()}.`.trim(),
  };
}

const plural = (count: number, word: string) => `${count} ${word}${count > 1 ? "s" : ""}`;

/** Résumé d'un thème, calculé à partir de ses groupes (aucun modèle de langage). */
export function summarize(groups: Resemblance[], themeOf: (dossierId: string) => string | null) {
  const dossierIds = [...new Set(groups.flatMap((g) => g.dossierIds))];
  const dossierThemes = [...new Set(dossierIds.map((id) => themeOf(id) ?? "Sans thème"))];
  const largest = [...groups].sort((a, b) => b.dossierIds.length - a.dossierIds.length)[0];
  const certainties = [...new Set(groups.map((g) => CERTAINTIES[g.certainty].label.toLowerCase()))];

  return {
    sentence: largest
      ? `${plural(groups.length, "groupe")} réunissant ${plural(dossierIds.length, "dossier")}. ` +
        `Le plus étendu : « ${largest.label} » (${plural(largest.dossierIds.length, "dossier")}).`
      : "Aucun rapprochement de ce type.",
    dossierThemes,
    certainties,
  };
}
