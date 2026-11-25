import { describe, expect, it } from "vitest";

import { advance, freezeTime, FROZEN_NOW } from "./clock";

describe("freezeTime", () => {
  it("fige la date du jour", () => {
    freezeTime();
    expect(new Date().toISOString()).toBe(FROZEN_NOW);
  });

  it("accepte une autre date", () => {
    freezeTime("2025-12-31T23:59:59.000Z");
    expect(new Date().getUTCFullYear()).toBe(2025);
  });

  it("avance l'horloge à la demande", async () => {
    freezeTime();
    await advance(5_000);
    expect(Date.now()).toBe(Date.parse(FROZEN_NOW) + 5_000);
  });
});

describe("fuseau de la suite", () => {
  it("est UTC (vitest.global-setup.ts) : l'heure locale égale l'heure UTC", () => {
    expect(new Date(2026, 0, 15, 10, 0, 0).toISOString()).toBe(FROZEN_NOW);
  });
});
