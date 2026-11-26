import { describe, expect, it } from "vitest";

import { METADATA_KEY_LABELS, type AnalyseDefinitions, type ElementKind, type FieldDefinition, type MetadataKey } from "@/types/documentTemplate";

import { defaultField, isValidFieldName, validateTemplate } from "./documentTemplateValidation";

const fd = (name: string, over: Partial<FieldDefinition> = {}): FieldDefinition => ({
  name, label: name || "libellé", type: "text", required: true, instruction: "", source: { kind: "instruction" }, ...over,
});
const analysis = (elementKind: ElementKind, definitionName: string): FieldDefinition["source"] => ({ kind: "analysis", elementKind, definitionName });
const kinds = (...args: Parameters<typeof validateTemplate>) => validateTemplate(...args).map((i) => `${i.kind}:${i.name}`);
// Données fictives : aucune donnée personnelle.
const DEFS: AnalyseDefinitions = { entity: ["Nom du demandeur", " Montant "], classification: ["Type de dossier"], synthesis: ["Résumé"] };

describe("isValidFieldName", () => {
  it.each(["nom", "_x", "a1", "A", "Loop", "x".repeat(10_000)])("accepte %.20s", (n) => expect(isValidFieldName(n)).toBe(true));
  it.each(["", "1a", "a-b", "a b", "é", "prénom", "loop", "true", "false", "none", "True", "False", "None", "self", "caller", "varargs", "kwargs"])(
    "refuse %j (vide, chiffre en tête, caractère spécial, accent ou mot réservé)", (n) => expect(isValidFieldName(n)).toBe(false));
});

describe("validateTemplate", () => {
  it("modèle cohérent, ou vide : aucune anomalie", () => {
    expect(kinds(["nom"], [fd("nom")])).toEqual([]);
    expect(kinds([], [])).toEqual([]);
  });
  it.each<[string, Parameters<typeof validateTemplate>, string[]]>([
    ["champ sans nom", [[], [fd("")]], ["missing_name:"]],
    ["nom invalide", [["a-b"], [fd("a-b")]], ["invalid_name:a-b"]],
    ["nom accentué (règle du serveur : lettres ASCII)", [["prénom"], [fd("prénom")]], ["invalid_name:prénom"]],
    ["nom en double", [["nom"], [fd("nom"), fd("nom")]], ["duplicate_name:nom"]],
    ["libellé de blancs", [["nom"], [fd("nom", { label: "   " })]], ["missing_label:nom"]],
    ["source d'analyse sans nom d'élément", [["nom"], [fd("nom", { source: analysis("entity", "  ") })]], ["incomplete_source:nom"]],
    ["champ sans placeholder", [[], [fd("nom")]], ["unused_field:nom"]],
    ["placeholder sans champ", [["nom", "age"], [fd("nom")]], ["unknown_placeholder:age"]],
    ["placeholder répété dans le fichier : une seule exigence", [["nom", "nom"], [fd("nom")]], []],
  ])("%s", (_l, args, expected) => expect(kinds(...args)).toEqual(expected));

  describe("sources comparées aux définitions de l'analyse", () => {
    it.each<[string, ElementKind, string, string[]]>([
      ["élément inconnu", "entity", "Inconnu", ["unknown_source:nom"]],
      ["casse et espaces ignorés", "entity", "  nom DU demandeur ", []],
      ["classification inconnue", "classification", "Nope", ["unknown_source:nom"]],
      ["synthèse, casse ignorée", "synthesis", "résumé", []],
      ["relation : pas de définition à vérifier", "relation", "Inconnu", []],
      ["champ renseigné : idem", "field", "Inconnu", []],
    ])("%s", (_l, kind, name, expected) => expect(kinds(["nom"], [fd("nom", { source: analysis(kind, name) })], DEFS)).toEqual(expected));

    it("sans définitions (null), la source n'est pas vérifiée", () => {
      expect(kinds(["nom"], [fd("nom", { source: analysis("entity", "Inconnu") })], null)).toEqual([]);
    });
    it("une métadonnée du dossier n'est pas vérifiée", () => {
      const key = Object.keys(METADATA_KEY_LABELS)[0] as MetadataKey;
      expect(kinds(["nom"], [fd("nom", { source: { kind: "dossier_metadata", key } })], DEFS)).toEqual([]);
    });
  });

  it("ordre stable des anomalies quand tout se cumule", () => {
    expect(kinds(["x", "loop"], [fd("loop"), fd("loop", { label: "" }), fd("")])).toEqual([
      "invalid_name:loop", "invalid_name:loop", "duplicate_name:loop", "missing_label:loop", "missing_name:", "unknown_placeholder:x",
    ]);
  });
  it("messages : accents conservés, et un très long texte ne casse rien", () => {
    expect(validateTemplate(["prénom"], [])[0].message).toBe("Le placeholder {{ prénom }} du fichier n'a pas de champ défini.");
    expect(validateTemplate(["é".repeat(5000)], [])[0].message.length).toBeGreaterThan(5000);
    expect(kinds(["nom"], [fd("nom", { label: "é".repeat(100_000) })])).toEqual([]);
  });
});

it("defaultField : texte obligatoire, renseigné au fil de l'instruction", () => {
  expect(defaultField("nom")).toEqual({ name: "nom", label: "nom", type: "text", required: true, instruction: "", source: { kind: "instruction" } });
});