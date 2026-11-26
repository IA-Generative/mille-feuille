import type { CustomField, CustomValue, FieldFilter } from "@/types/tracking";
import { NO_VALUE, parseCalendarDate } from "@/utils/dates";

/** Erreur de validation d'une valeur selon le type du champ, ou `null` si elle est valide. */
export function validateValue(field: CustomField, value: CustomValue): string | null {
  const empty = value === null || value === "" || value === undefined;
  if (empty) return field.required && field.type !== "boolean" ? "Ce champ est obligatoire." : null;
  switch (field.type) {
    case "number":
      return typeof value === "number" && Number.isFinite(value) ? null : "Saisissez un nombre.";
    case "amount":
      return typeof value === "number" && Number.isFinite(value) && value >= 0
        ? null
        : "Saisissez un montant positif.";
    case "date":
      return typeof value === "string" && parseCalendarDate(value) ? null : "Saisissez une date valide.";
    case "choice":
      return typeof value === "string" && field.choices.includes(value) ? null : "Choisissez une valeur de la liste.";
    case "boolean":
      return typeof value === "boolean" ? null : "Valeur invalide.";
    default:
      return null;
  }
}

/** Convertit la saisie brute d'un champ en valeur typée. */
export function parseInput(field: CustomField, raw: string | number): CustomValue {
  // Un <input type="number"> lié par v-model fournit déjà un nombre.
  if (typeof raw === "number") return Number.isNaN(raw) ? null : raw;
  if (raw === "") return null;
  if (field.type === "number" || field.type === "amount") {
    // Des espaces seuls sont une saisie vide, pas un zéro (Number("  ") vaut 0).
    const text = raw.trim();
    if (text === "") return null;
    const n = Number(text.replace(",", "."));
    return Number.isNaN(n) ? raw : n;
  }
  return raw;
}

export function formatValue(field: CustomField, value: CustomValue | undefined): string {
  if (value === null || value === undefined || value === "") return NO_VALUE;
  switch (field.type) {
    case "amount": {
      const amount = Number(value);
      if (!Number.isFinite(amount)) return NO_VALUE; // plus de « NaN € »
      const currency = field.currency || "EUR";
      try {
        return new Intl.NumberFormat("fr-FR", { style: "currency", currency }).format(amount);
      } catch (error) {
        if (!(error instanceof RangeError)) throw error; // seulement le code de devise invalide
        return `${new Intl.NumberFormat("fr-FR").format(amount)} ${currency}`;
      }
    }
    case "number": {
      const n = Number(value);
      return Number.isFinite(n) ? new Intl.NumberFormat("fr-FR").format(n) : NO_VALUE;
    }
    case "date": {
      const day = parseCalendarDate(String(value));
      return day ? day.toLocaleDateString("fr-FR") : NO_VALUE;
    }
    case "boolean":
      return value ? "Oui" : "Non";
    default:
      return String(value);
  }
}

/** Une valeur passe-t-elle le filtre d'un champ ? */
export function matchesFieldFilter(field: CustomField, value: CustomValue | undefined, filter: FieldFilter): boolean {
  if (typeof filter === "string") {
    if (filter === "") return true;
    if (field.type === "boolean") return String(Boolean(value)) === filter;
    if (field.type === "choice") return value === filter;
    return String(value ?? "").toLowerCase().includes(filter.toLowerCase());
  }
  if (!filter.min && !filter.max) return true;
  if (value === null || value === undefined || value === "") return false;
  const compare = field.type === "date" ? String(value) : Number(value);
  const min = field.type === "date" ? filter.min : Number(filter.min);
  const max = field.type === "date" ? filter.max : Number(filter.max);
  return (!filter.min || compare >= min) && (!filter.max || compare <= max);
}
