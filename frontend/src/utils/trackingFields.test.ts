import { beforeEach, describe, expect, it } from "vitest";

import { freezeTime } from "@/test/clock";
import { TIMEZONES, useTimezone, WEST_TIMEZONE, type Timezone } from "@/test/timezones";
import type { CustomField, CustomValue, FieldFilter, FieldType } from "@/types/tracking";

import { formatValue, matchesFieldFilter, parseInput, validateValue } from "./trackingFields";

const field = (type: FieldType, over: Partial<CustomField> = {}): CustomField => ({
  id: "f1", name: "Champ", definition: "", type, required: false, defaultValue: null, choices: ["A", "B"], currency: "EUR", ...over,
});
// ICU met des espaces insécables (U+202F, U+00A0) selon sa version : on compare avec des espaces normaux.
const plain = (s: string) => s.replace(/[\u202f\u00a0]/g, " ");
const LONG = "é".repeat(100_000);
const SPECIAL = "<script>alert('é')</script> 日本語 😀 \u0000";

describe("validateValue", () => {
  it.each<[string, CustomField, CustomValue | undefined, string | null]>([
    ["obligatoire, chaîne vide", field("text", { required: true }), "", "Ce champ est obligatoire."],
    ["obligatoire, null", field("text", { required: true }), null, "Ce champ est obligatoire."],
    ["obligatoire, undefined", field("number", { required: true }), undefined, "Ce champ est obligatoire."],
    ["oui/non obligatoire, vide : jamais bloquant", field("boolean", { required: true }), null, null],
    ["facultatif, vide", field("text"), "", null],
    ["0 est une valeur, pas un vide", field("number", { required: true }), 0, null],
    ["false est une valeur", field("boolean", { required: true }), false, null],
    ["nombre NaN", field("number"), NaN, "Saisissez un nombre."],
    ["nombre infini", field("number"), Infinity, "Saisissez un nombre."],
    ["nombre en texte", field("number"), "12", "Saisissez un nombre."],
    ["nombre négatif accepté", field("number"), -5, null],
    ["montant 0", field("amount"), 0, null],
    ["montant négatif", field("amount"), -0.01, "Saisissez un montant positif."],
    ["date valide", field("date"), "2026-01-15", null],
    ["date non analysable", field("date"), "abc", "Saisissez une date valide."],
    ["mois 13", field("date"), "2026-13-01", "Saisissez une date valide."],
    ["date en nombre", field("date"), 20260115, "Saisissez une date valide."],
    ["choix dans la liste", field("choice"), "A", null],
    ["choix hors liste", field("choice"), "C", "Choisissez une valeur de la liste."],
    ["choix : la casse compte", field("choice"), "a", "Choisissez une valeur de la liste."],
    ["choix avec accents", field("choice", { choices: ["été", "Éco"] }), "été", null],
    ["oui/non en texte", field("boolean"), "true", "Valeur invalide."],
    ["texte de 100 000 caractères", field("text"), LONG, null],
    ["texte avec balises, CJK, emoji, NUL", field("text"), SPECIAL, null],
  ])("%s", (_l, f, value, expected) => expect(validateValue(f, value as CustomValue)).toBe(expected));

  it.each(["2026-02-30", "2026-04-31"])("une date au jour inexistant (%s) est refusée", (value) => {
    expect(validateValue(field("date"), value)).toBe("Saisissez une date valide.");
  });
});

describe("parseInput", () => {
  it.each<[string, FieldType, string | number, CustomValue]>([
    ["nombre déjà typé", "number", 5, 5], ["NaN → null", "number", NaN, null], ["vide → null", "text", "", null],
    ["virgule décimale", "amount", "12,5", 12.5], ["négatif", "number", "-3,2", -3.2], ["notation scientifique", "number", "1e3", 1000],
    ["« 0 »", "number", "0", 0], ["texte non numérique gardé tel quel", "number", "abc", "abc"],
    ["espaces des milliers non gérés : texte gardé", "number", "1 234,5", "1 234,5"],
    ["texte : la virgule n'est pas touchée", "text", "12,5", "12,5"], ["accents", "text", "été", "été"], ["date inchangée", "date", "2026-01-15", "2026-01-15"],
  ])("%s", (_l, type, raw, expected) => expect(parseInput(field(type), raw)).toEqual(expected));

  it("des espaces seuls sont une saisie vide, pas un zéro", () => {
    expect(parseInput(field("number"), "  ")).toBeNull();
  });
  it("les espaces autour d'un nombre sont ignorés", () => {
    expect(parseInput(field("number"), " 12,5 ")).toBe(12.5);
  });
});

describe("formatValue", () => {
  it.each<[string, CustomField, CustomValue | undefined, string]>([
    ["null", field("text"), null, "—"], ["undefined", field("text"), undefined, "—"], ["chaîne vide", field("text"), "", "—"],
    ["0 n'est pas vide", field("number"), 0, "0"], ["false → Non", field("boolean"), false, "Non"], ["true → Oui", field("boolean"), true, "Oui"],
    ["montant en euros", field("amount"), 1234.5, "1 234,50 €"], ["montant en dollars", field("amount", { currency: "USD" }), 1234.5, "1 234,50 $US"],
    ["devise vide : euro par défaut", field("amount", { currency: "" }), 7, "7,00 €"],
    ["nombre", field("number"), 1234567.891, "1 234 567,891"], ["texte accentué", field("text"), "été", "été"], ["choix", field("choice"), "A", "A"],
  ])("%s", (_l, f, value, expected) => expect(plain(formatValue(f, value))).toBe(expected));

  it("un texte de 100 000 caractères est rendu en entier", () => {
    expect(formatValue(field("text"), LONG)).toHaveLength(100_000);
  });
  it("une devise invalide n'empêche pas d'afficher le montant", () => {
    expect(plain(formatValue(field("amount", { currency: "EU" }), 7))).toBe("7 EU");
  });
  it.each(["amount", "number"] as const)("une valeur non numérique (%s) donne « — » et non « NaN »", (type) => {
    expect(formatValue(field(type), "abc")).toBe("—");
  });
  it.each(["abc", "2026-02-30"])("une date illisible (%s) donne « — » et non « Invalid Date »", (value) => {
    expect(formatValue(field("date"), value)).toBe("—");
  });

  describe.each<Timezone>([...TIMEZONES, WEST_TIMEZONE])("date, fuseau %s", (tz) => {
    beforeEach(() => { useTimezone(tz); freezeTime(new Date(2026, 0, 15, 10)); });
    it("« 2026-01-15 » s'affiche 15/01/2026", () => expect(formatValue(field("date"), "2026-01-15")).toBe("15/01/2026"));
  });
});

describe("matchesFieldFilter", () => {
  it.each<[string, CustomField, CustomValue | undefined, FieldFilter, boolean]>([
    ["filtre vide : tout passe", field("text"), "x", "", true],
    ["texte : insensible à la casse et aux accents majuscules", field("text"), "Été indien", "ÉTÉ", true],
    ["texte : valeur absente", field("text"), null, "x", false],
    ["oui/non : true", field("boolean"), true, "true", true], ["oui/non : false", field("boolean"), false, "false", true],
    ["oui/non : null compte comme false", field("boolean"), null, "false", true],
    ["choix égal", field("choice"), "A", "A", true], ["choix différent", field("choice"), "B", "A", false],
    ["plage sans bornes", field("number"), 5, { min: "", max: "" }, true], ["nombre dans la plage", field("number"), 5, { min: "1", max: "10" }, true],
    ["nombre sous le minimum", field("number"), 0, { min: "1", max: "" }, false], ["nombre vide dans une plage", field("number"), null, { min: "1", max: "10" }, false],
    ["borne haute incluse", field("number"), 10, { min: "1", max: "10" }, true], ["0 avec min « 0 »", field("number"), 0, { min: "0", max: "5" }, true],
    ["date dans la plage", field("date"), "2026-01-15", { min: "2026-01-01", max: "2026-01-31" }, true],
    ["date après le maximum", field("date"), "2026-02-01", { min: "", max: "2026-01-31" }, false],
    ["montant dans la plage", field("amount"), 50, { min: "10", max: "100" }, true], ["texte dans une plage numérique", field("number"), "abc", { min: "1", max: "" }, false],
  ])("%s", (_l, f, value, filter, expected) => expect(matchesFieldFilter(f, value, filter)).toBe(expected));
});
