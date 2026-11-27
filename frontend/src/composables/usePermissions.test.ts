import { flushPromises } from "@vue/test-utils";
import { effectScope, ref } from "vue";
import { describe, expect, it, vi } from "vitest";

import { usePermissions } from "@/composables/usePermissions";
import { apiFetch } from "@/utils/api";

const auth = vi.hoisted(() => ({ isAdmin: false }));
vi.mock("@/composables/useAuth", () => ({ useAuth: () => ({ isAdmin: ref(auth.isAdmin) }) }));
vi.mock("@/utils/api", () => ({ apiFetch: vi.fn() }));

const setup = () => effectScope().run(() => usePermissions("dossiers", () => "d1"))!;

describe("usePermissions", () => {
  it("suit les permissions renvoyées par le serveur", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ permissions: ["dossier.view"] });
    const { can, loaded } = setup();
    await flushPromises();

    expect(apiFetch).toHaveBeenCalledWith("/api/dossiers/d1/permissions");
    expect(loaded.value).toBe(true);
    expect([can("dossier.view"), can("dossier.edit")]).toEqual([true, false]);
  });

  it("n'interroge pas le serveur pour un super admin", async () => {
    auth.isAdmin = true;
    vi.mocked(apiFetch).mockClear();

    expect(setup().can("dossier.delete")).toBe(true);
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
