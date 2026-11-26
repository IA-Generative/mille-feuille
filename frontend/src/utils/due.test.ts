import { beforeEach, describe, expect, it } from "vitest";

import { freezeTime } from "@/test/clock";
import { TIMEZONES, useTimezone } from "@/test/timezones";
import type { DueInfo } from "@/types/dossier";

import { dueInfo, dueLabel, formatDueDate } from "./due";

const inDays = (n: number) => new Date(2026, 0, 15 + n, 12).toISOString(); // heure locale, à midi

describe.each(TIMEZONES)("due, fuseau %s", (tz) => {
  beforeEach(() => {
    useTimezone(tz);
    freezeTime(new Date(2026, 0, 15, 10));
  });

  describe("dueInfo", () => {
    it.each([null, ""])("%j → sans échéance", (value) => {
      expect(dueInfo(value)).toEqual({ label: "Sans échéance", tone: "none", days: null });
    });
    it.each([
      [-1, "overdue", "Échéance dépassée depuis 1 j"], [0, "danger", "Échéance aujourd'hui"],
      [1, "danger", "Échéance dans 1 j"], [6, "danger", "Échéance dans 6 j"],
      [7, "warning", "Échéance dans 7 j"], [30, "warning", "Échéance dans 30 j"], [31, "ok", "Échéance dans 31 j"],
    ])("à %i jour(s) → %s", (days, tone, label) => {
      expect(dueInfo(inDays(days))).toEqual({ label, tone, days });
    });
    // Défaut actuel : une date invalide donne « Échéance dans NaN j » avec le niveau « ok » (le plus rassurant).
    it.fails("ne devrait pas classer une date invalide comme « ok »", () => {
      expect(dueInfo("abc").tone).not.toBe("ok");
    });
  });

  describe("dueLabel", () => {
    const due = (level: DueInfo["level"], daysLeft: number): DueInfo => ({ level, daysLeft });
    it.each([
      ["closed", 5, false, "Dossier clos"], ["closed", 5, true, "Dossier clos"],
      ["overdue", -3, false, "Échéance dépassée depuis 3 j"], ["overdue", -3, true, "Dépassée de 3 j"],
      ["soon", 0, false, "Échéance aujourd'hui"], ["soon", 0, true, "Aujourd'hui"],
      ["ok", 12, false, "Échéance dans 12 j"], ["ok", 12, true, "Dans 12 j"],
    ] as const)("%s, %i j, compact=%s → %s", (level, days, compact, expected) => {
      expect(dueLabel(due(level, days), compact)).toBe(expected);
    });
  });

  describe("formatDueDate", () => {
    it.each([
      ["2026-01-15", "15 janvier 2026"], ["2028-02-29", "29 février 2028"], ["2026-12-31", "31 décembre 2026"],
    ])("%s → %s", (input, expected) => expect(formatDueDate(input)).toBe(expected));
    it("ne valide pas : un jour impossible déborde sur le mois suivant (comportement actuel)", () => {
      expect(formatDueDate("2026-02-30")).toBe("2 mars 2026");
    });
    it.fails("ne devrait pas afficher « Invalid Date »", () => {
      expect(formatDueDate("")).not.toContain("Invalid");
    });
  });
});
