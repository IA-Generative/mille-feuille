import { beforeEach, describe, expect, it } from "vitest";

import { freezeTime } from "@/test/clock";
import { TIMEZONES, useTimezone, type Timezone } from "@/test/timezones";
import type { DashboardUrgency } from "@/types/dashboard";
import type { Recurrence } from "@/types/schedule";

import {
  formatReminder, occurrenceStarts, slotOfUrgency, summarizeRecurrence, summarizeReminders, summarizeSlot, weekdayOf,
} from "./recurrence";

const pad = (n: number) => String(n).padStart(2, "0");
const local = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
// Fonctions, pas des constantes : une Date créée au chargement garderait le fuseau d'avant useTimezone().
const start = () => new Date(2026, 0, 15, 9, 30); // jeudi 15 janvier 2026, 9 h 30
const wide = (): [Date, Date] => [new Date(2026, 0, 1), new Date(2036, 0, 1)];
const run = (from: Date, rec: Recurrence | undefined, [a, b] = wide()) => occurrenceStarts(from, rec, a, b).map(local);
const end = { never: { type: "never" } as const };
const count = (n: number) => ({ type: "count", count: n }) as const;

describe.each(TIMEZONES)("recurrence, fuseau %s", (tz) => {
  beforeEach(() => { useTimezone(tz); freezeTime(new Date(2026, 0, 15, 10)); });

  describe("occurrenceStarts", () => {
    it("sans récurrence : le créneau seul, s'il est dans la fenêtre", () => {
      expect(run(start(), undefined, [new Date(2026, 0, 1), new Date(2026, 0, 31)])).toEqual(["2026-01-15 09:30"]);
      expect(run(start(), undefined, [new Date(2026, 1, 1), new Date(2026, 1, 28)])).toEqual([]);
    });
    it.each([
      ["jour, 3 fois", { unit: "day", interval: 1, end: count(3) }, ["2026-01-15 09:30", "2026-01-16 09:30", "2026-01-17 09:30"]],
      ["jour, tous les 2, jusqu'au 21 inclus", { unit: "day", interval: 2, end: { type: "until", date: "2026-01-21" } },
        ["2026-01-15 09:30", "2026-01-17 09:30", "2026-01-19 09:30", "2026-01-21 09:30"]],
      ["intervalle 0 traité comme 1", { unit: "day", interval: 0, end: count(3) }, ["2026-01-15 09:30", "2026-01-16 09:30", "2026-01-17 09:30"]],
      ["fin avant le début", { unit: "day", interval: 1, end: { type: "until", date: "2026-01-10" } }, []],
      ["semaine : même jour que le début", { unit: "week", interval: 1, end: count(3) }, ["2026-01-15 09:30", "2026-01-22 09:30", "2026-01-29 09:30"]],
      ["semaine : lundi et jeudi, une sur deux", { unit: "week", interval: 2, weekdays: [0, 3], end: count(5) },
        ["2026-01-15 09:30", "2026-01-26 09:30", "2026-01-29 09:30", "2026-02-09 09:30", "2026-02-12 09:30"]],
      ["semaine : jours donnés dans le désordre", { unit: "week", interval: 1, weekdays: [3, 0], end: count(4) },
        ["2026-01-15 09:30", "2026-01-19 09:30", "2026-01-22 09:30", "2026-01-26 09:30"]],
      ["mois, tous les 2", { unit: "month", interval: 2, end: count(3) }, ["2026-01-15 09:30", "2026-03-15 09:30", "2026-05-15 09:30"]],
    ] as const)("%s", (_l, rec, expected) => {
      expect(run(start(), rec as Recurrence)).toEqual(expected);
    });

    it("le lundi qui précède le début n'est pas une occurrence", () => {
      expect(run(start(), { unit: "week", interval: 1, weekdays: [0, 3], end: count(1) })).toEqual(["2026-01-15 09:30"]);
    });
    it("occurrence qui tombe sur un jour inexistant : le 31 devient fin de mois, sans dérive", () => {
      const rec: Recurrence = { unit: "month", interval: 1, end: count(4) };
      expect(run(new Date(2026, 0, 31, 9, 30), rec)).toEqual(["2026-01-31 09:30", "2026-02-28 09:30", "2026-03-31 09:30", "2026-04-30 09:30"]);
      expect(run(new Date(2028, 0, 31, 9, 30), { ...rec, end: count(3) })).toEqual(["2028-01-31 09:30", "2028-02-29 09:30", "2028-03-31 09:30"]);
    });
    it("29 février + annuel : 28 février les années non bissextiles", () => {
      expect(run(new Date(2028, 1, 29, 9, 30), { unit: "year", interval: 1, end: count(5) }, [new Date(2028, 0, 1), new Date(2040, 0, 1)])).toEqual(
        ["2028-02-29 09:30", "2029-02-28 09:30", "2030-02-28 09:30", "2031-02-28 09:30", "2032-02-29 09:30"]);
    });
    it("occurrences passées : elles comptent dans « N fois » mais sortent de la fenêtre", () => {
      expect(run(start(), { unit: "day", interval: 1, end: count(3) }, [new Date(2026, 0, 16), new Date(2026, 0, 31)])).toEqual(["2026-01-16 09:30", "2026-01-17 09:30"]);
    });
    it("la fin de fenêtre est incluse", () => {
      expect(run(start(), { unit: "day", interval: 1, end: end.never }, [new Date(2026, 0, 15, 9, 30), new Date(2026, 0, 16, 9, 30)])).toEqual(["2026-01-15 09:30", "2026-01-16 09:30"]);
    });
    it("garde-fou : jamais plus de 5000 occurrences", () => {
      expect(occurrenceStarts(start(), { unit: "day", interval: 1, end: end.never }, start(), new Date(2100, 0, 1))).toHaveLength(5000);
    });
    it("garde l'heure locale à travers un changement d'heure", () => {
      const hours = occurrenceStarts(new Date(2026, 8, 25, 9, 30), { unit: "day", interval: 1, end: count(5) }, new Date(2026, 8, 1), new Date(2026, 9, 30));
      expect(hours.map((d) => `${d.getHours()}:${d.getMinutes()}`)).toEqual(Array(5).fill("9:30"));
    });
  });

  it("weekdayOf : lundi = 0 … dimanche = 6", () => {
    expect([new Date(2026, 0, 19), new Date(2026, 0, 15), new Date(2026, 0, 18)].map(weekdayOf)).toEqual([0, 3, 6]);
  });

  describe("textes", () => {
    it.each([
      [0, "À l'heure du créneau"], [5, "5 minutes avant"], [60, "1 heure avant"], [1440, "1 jour avant"], [10080, "1 semaine avant"],
      [180, "3 heures avant"], [4320, "3 jours avant"], [20160, "14 jours avant"], [45, "45 minutes avant"], [90, "90 minutes avant"], [1441, "1441 minutes avant"],
    ])("formatReminder(%i) → %s", (minutes, expected) => expect(formatReminder(minutes)).toBe(expected));

    it.each<[string, Recurrence, string]>([
      ["jour", { unit: "day", interval: 1, end: end.never }, "Tous les jours"],
      ["tous les 3 jours", { unit: "day", interval: 3, end: end.never }, "Tous les 3 jours"],
      ["7 jours cochés", { unit: "week", interval: 1, weekdays: [0, 1, 2, 3, 4, 5, 6], end: end.never }, "Tous les jours"],
      ["jours ouvrés, désordre", { unit: "week", interval: 1, weekdays: [4, 0, 1, 2, 3], end: end.never }, "Tous les jours ouvrés"],
      ["lundi et jeudi, 1 sur 2", { unit: "week", interval: 2, weekdays: [3, 0], end: end.never }, "Toutes les 2 semaines le lundi et jeudi"],
      ["trois jours", { unit: "week", interval: 1, weekdays: [0, 2, 4], end: end.never }, "Toutes les semaines le lundi, mercredi et vendredi"],
      ["sans jours : celui du début", { unit: "week", interval: 1, end: end.never }, "Toutes les semaines le jeudi"],
      ["7 jours, 1 sur 2", { unit: "week", interval: 2, weekdays: [0, 1, 2, 3, 4, 5, 6], end: end.never }, "Toutes les 2 semaines le lundi, mardi, mercredi, jeudi, vendredi, samedi et dimanche"],
      ["mois", { unit: "month", interval: 2, end: end.never }, "Tous les 2 mois"],
      ["an", { unit: "year", interval: 1, end: end.never }, "Tous les ans"],
      ["ans", { unit: "year", interval: 3, end: end.never }, "Tous les 3 ans"],
      ["jusqu'au", { unit: "day", interval: 1, end: { type: "until", date: "2026-12-12" } }, "Tous les jours, jusqu'au 12 déc. 2026"],
      ["N fois", { unit: "day", interval: 1, end: count(5) }, "Tous les jours, 5 fois"],
    ])("summarizeRecurrence : %s", (_l, rec, expected) => expect(summarizeRecurrence(rec, start())).toBe(expected));

    it("summarizeReminders / summarizeSlot", () => {
      expect(summarizeReminders([])).toBe("Aucun rappel");
      expect(summarizeReminders([0, 15])).toBe("À l'heure du créneau, 15 minutes avant");
      expect(summarizeSlot({ reminders: [] }, start())).toBe("Une seule fois · Aucun rappel");
      expect(summarizeSlot({ recurrence: { unit: "day", interval: 1, end: end.never }, reminders: [60] }, start())).toBe("Tous les jours · 1 heure avant");
    });

    const urgency = (o: Partial<DashboardUrgency>) => o as DashboardUrgency;
    it("slotOfUrgency : null sans début ou sans fin, rappels vides par défaut", () => {
      expect(slotOfUrgency(urgency({ plannedStart: "a" }))).toBeNull();
      expect(slotOfUrgency(urgency({}))).toBeNull();
      expect(slotOfUrgency(urgency({ plannedStart: "a", plannedEnd: "b" }))).toEqual({ start: "a", end: "b", recurrence: undefined, reminders: [] });
    });
  });
});

// Le fuseau change le résultat, et c'est voulu : une heure qui n'existe pas (saut d'heure) est décalée.
describe("changement d'heure", () => {
  it.each<[Timezone, string]>([["UTC", "2026-09-27 02:30"], ["Pacific/Auckland", "2026-09-27 03:30"]])("tous les jours à 2 h 30, le 27 sept. 2026, à %s", (tz, expected) => {
    useTimezone(tz);
    expect(run(new Date(2026, 8, 26, 2, 30), { unit: "day", interval: 1, end: count(3) })[1]).toBe(expected);
  });
});