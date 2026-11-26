import { vi } from "vitest";

/** Matrice des tests : UTC (référence) et Auckland (+12/+13, avec changement d'heure en septembre et en avril). */
export const TIMEZONES = ["UTC", "Pacific/Auckland"] as const;
/** À l'ouest de UTC, comme la Guadeloupe, la Martinique ou la Guyane : c'est là que se cachent les bugs « date lue en UTC ». */
export const WEST_TIMEZONE = "America/Martinique";
export type Timezone = (typeof TIMEZONES)[number] | typeof WEST_TIMEZONE;

// getTimezoneOffset() le 15 janvier 2026, en minutes.
const JANUARY_OFFSET: Record<Timezone, number> = { UTC: 0, "Pacific/Auckland": -780, "America/Martinique": 240 };

/** Passe le test dans ce fuseau. Annulé par vi.unstubAllEnvs() (voir vitest.setup.ts). */
export function useTimezone(tz: Timezone) {
  vi.stubEnv("TZ", tz);
  // Garde-fou : si le changement n'avait aucun effet, tous les tests « multi-fuseaux » passeraient pour rien.
  const offset = new Date(2026, 0, 15, 10).getTimezoneOffset();
  if (offset !== JANUARY_OFFSET[tz]) throw new Error(`Fuseau ${tz} non appliqué (décalage ${offset} min)`);
}
