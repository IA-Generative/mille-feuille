import { beforeEach, describe, expect, it } from "vitest";

import { freezeTime } from "@/test/clock";
import { freshImport } from "@/test/singletons";
import { TIMEZONES, useTimezone, type Timezone } from "@/test/timezones";

const MIN = 60_000;
const HOUR = 60 * MIN;
type Ymdh = [year: number, month: number, day: number, hour?: number, minute?: number];
/** Date en heure LOCALE (mois de 1 à 12). À appeler dans un test, jamais au chargement du fichier. */
const at = ([y, m, d, h = 12, min = 0]: Ymdh) => new Date(y, m - 1, d, h, min);
// dates.ts crée son Intl.DateTimeFormat à l'import : on le recharge pour qu'il suive le fuseau courant.
const loadDates = () => freshImport(() => import("./dates"));

describe.each(TIMEZONES)("dates, fuseau %s", (tz) => {
  let dates: Awaited<ReturnType<typeof loadDates>>;
  beforeEach(async () => {
    useTimezone(tz);
    freezeTime(at([2026, 1, 15, 10])); // jeudi 15 janvier 2026, 10 h
    dates = await loadDates();
  });

  describe("formatRelativeTime", () => {
    const ago = (ms: number) => new Date(Date.now() - ms).toISOString();
    it.each([
      [0, "à l'instant"], [29_000, "à l'instant"], [30_000, "il y a 1 min"],
      [59 * MIN, "il y a 59 min"], [60 * MIN, "il y a 1 h"], [89 * MIN, "il y a 1 h"], [90 * MIN, "il y a 2 h"],
      [23 * HOUR, "il y a 23 h"], [24 * HOUR, "il y a 1 j"], [36 * HOUR, "il y a 2 j"],
      [-5 * MIN, "à l'instant"], // une date future ne devient pas négative
    ])("%i ms plus tôt → %s", (ms, expected) => {
      expect(dates.formatRelativeTime(ago(ms))).toBe(expected);
    });

    it.each(["", "abc"])("une date invalide (%j) donne « — » et non « il y a NaN j »", (bad) => {
      expect(dates.formatRelativeTime(bad)).toBe("—");
    });
  });

  describe("dayOffset", () => {
    it.each<[string, Ymdh, Ymdh, number]>([
      ["même jour, 23 h 59", [2026, 1, 15, 10], [2026, 1, 15, 23, 59], 0],
      ["lendemain, minuit pile", [2026, 1, 15, 10], [2026, 1, 16, 0, 0], 1],
      ["veille, 23 h 59", [2026, 1, 15, 10], [2026, 1, 14, 23, 59], -1],
      ["minuit contre minuit", [2026, 1, 15, 0, 0], [2026, 1, 15, 0, 0], 0],
      ["fin de mois (31 janv. → 1er févr.)", [2026, 1, 31, 10], [2026, 2, 1], 1],
      ["bissextile : 28 févr. → 29 févr. 2028", [2028, 2, 28, 10], [2028, 2, 29], 1],
      ["bissextile : 28 févr. → 1er mars 2028", [2028, 2, 28, 10], [2028, 3, 1], 2],
      ["non bissextile : 28 févr. → 1er mars 2026", [2026, 2, 28, 10], [2026, 3, 1], 1],
      ["jour de 23 h (heure d'été à Auckland, 27 sept. 2026)", [2026, 9, 26, 12], [2026, 9, 28, 0], 2],
      ["jour de 25 h (heure d'hiver à Auckland, 5 avr. 2026)", [2026, 4, 4, 12], [2026, 4, 6, 0], 2],
    ])("%s", (_label, now, target, expected) => {
      freezeTime(at(now));
      expect(dates.dayOffset(at(target).toISOString())).toBe(expected);
    });

    it("renvoie NaN pour une date invalide ou vide", () => {
      expect(dates.dayOffset("abc")).toBeNaN();
      expect(dates.dayOffset("")).toBeNaN();
    });
  });

  describe("formatDayLabel / dayLabel / formatDue", () => {
    it("formatDayLabel : jour de la semaine, jour sur 2 chiffres, mois", () => {
      expect(dates.formatDayLabel(at([2026, 11, 5]))).toBe("jeudi 05 novembre");
      expect(dates.formatDayLabel(at([2026, 1, 1]))).toBe("jeudi 01 janvier");
    });

    it.each<[string, Ymdh, string]>([
      ["hier", [2026, 1, 14], "En retard"],
      ["aujourd'hui, 23 h", [2026, 1, 15, 23], "Aujourd'hui"],
      ["demain, 0 h 05", [2026, 1, 16, 0, 5], "Demain"],
      ["samedi 17", [2026, 1, 17], "samedi 17 janvier"],
    ])("dayLabel : %s", (_l, target, expected) => {
      expect(dates.dayLabel(at(target).toISOString())).toBe(expected);
    });

    it.each<[string, Ymdh, string]>([
      ["aujourd'hui", [2026, 1, 15], "aujourd'hui"],
      ["demain", [2026, 1, 16], "demain"],
      ["dans 3 j", [2026, 1, 18], "dans 3 j"],
      ["2 j de retard", [2026, 1, 13], "2 j de retard"],
    ])("formatDue : %s", (_l, target, expected) => {
      expect(dates.formatDue(at(target).toISOString())).toBe(expected);
    });

    it.each(["", "abc"])("une date invalide (%j) donne « — » : dayLabel ne lève plus d'exception, formatDue n'affiche plus NaN", (bad) => {
      expect(dates.dayLabel(bad)).toBe("—");
      expect(dates.formatDue(bad)).toBe("—");
    });
  });

  describe("parseCalendarDate", () => {
    const ymd = (d: Date | null) => d && [d.getFullYear(), d.getMonth() + 1, d.getDate()];

    it.each<[string, number[]]>([
      ["2026-01-15", [2026, 1, 15]],
      ["2028-02-29", [2028, 2, 29]], // bissextile
      ["2026-12-31", [2026, 12, 31]],
    ])("« %s » est le jour %j, lu en heure locale", (text, expected) => {
      expect(ymd(dates.parseCalendarDate(text))).toEqual(expected);
    });

    it.each(["2026-02-30", "2026-02-29", "2026-04-31", "2026-13-01", "2026-00-10", "abc", ""])(
      "« %s » est refusé (jour inexistant ou texte illisible)",
      (text) => expect(dates.parseCalendarDate(text)).toBeNull(),
    );

    it("une date ISO complète reste acceptée", () => {
      expect(dates.parseCalendarDate("2026-01-15T10:00:00Z")).not.toBeNull();
    });
  });
});

// Ici le fuseau change le résultat, et c'est voulu : un INSTANT UTC tombe sur des jours différents.
describe("un instant exprimé en UTC selon le fuseau de l'utilisateur", () => {
  it.each<[Timezone, number]>([
    ["UTC", 0],
    ["Pacific/Auckland", 1],
  ])("2026-01-15T23:30:00Z vu depuis %s", async (tz, expected) => {
    useTimezone(tz);
    freezeTime(at([2026, 1, 15, 10]));
    const dates = await loadDates();
    expect(dates.dayOffset("2026-01-15T23:30:00Z")).toBe(expected);
  });
});
