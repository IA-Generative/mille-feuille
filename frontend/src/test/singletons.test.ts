import { describe, expect, it } from "vitest";

import type { UserStats } from "@/types/profile";

import { mockApi } from "./mockApi";
import { freshImport } from "./singletons";

const STATS: UserStats = {
  conversations_count: 4,
  messages_sent_count: 12,
  agent_conversations_count: 1,
  agent_messages_sent_count: 3,
  dossiers_count: 2,
  analyses_shared_count: 0,
  last_activity_at: null,
};

const loadUseProfile = () => freshImport(() => import("@/composables/useProfile"));

describe("freshImport", () => {
  it("un import normal retrouve l'état du singleton (c'est ce qu'on veut éviter entre deux tests)", async () => {
    mockApi.get("/api/me/stats", STATS);
    const { useProfile } = await loadUseProfile();
    await useProfile().fetchStats();

    const { useProfile: again } = await import("@/composables/useProfile");

    expect(again().stats.value).toEqual(STATS);
  });

  it("repart de l'état initial après freshImport", async () => {
    mockApi.get("/api/me/stats", STATS);
    const { useProfile } = await loadUseProfile();
    const before = useProfile();
    await before.fetchStats();
    expect(before.stats.value).toEqual(STATS);

    const { useProfile: fresh } = await loadUseProfile();

    expect(fresh().stats.value).toBeNull();
  });
});
