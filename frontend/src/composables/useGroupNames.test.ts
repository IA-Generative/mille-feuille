import { describe, expect, it, vi } from "vitest";

import { useGroupNames } from "@/composables/useGroupNames";
import { apiFetch } from "@/utils/api";

vi.mock("@/utils/api", () => ({ apiFetch: vi.fn() }));

const ID = "0b9c7a52-1111-4222-8333-444455556666";

describe("useGroupNames", () => {
  it("nomme un groupe par son identifiant, et garde les anciens chemins lisibles", async () => {
    vi.mocked(apiFetch).mockResolvedValue([{ id: ID, name: "service-culture" }]);
    const { resolve, nameOf } = useGroupNames();

    expect(nameOf(ID)).toBe("Groupe");
    await resolve([ID, "/service-culture"]);
    await resolve([ID]);

    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(apiFetch).toHaveBeenCalledWith(`/api/groups/names?ids=${ID}`);
    expect(nameOf(ID)).toBe("service-culture");
    expect(nameOf("/service-culture")).toBe("Service culture");
  });
});
