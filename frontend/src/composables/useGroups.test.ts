import { beforeEach, describe, expect, it } from "vitest";

import { resetMockGroups, useGroups } from "@/composables/useGroups";

describe("useGroups (maquette)", () => {
  beforeEach(resetMockGroups);

  it("limite l'admin d'un groupe à ses groupes", () => {
    const { personaId, visibleGroups, creationGroups, can } = useGroups();
    personaId.value = "admin";

    expect(visibleGroups.value.map((g) => g.id)).toEqual(["culture"]);
    expect(creationGroups.value.map((g) => g.id)).toEqual(["culture"]);
    expect(can("group.members", "road")).toBe(false);
  });

  it("met en attente une adresse jamais connectée et refuse les doublons", () => {
    const { addMember, groupById } = useGroups();

    expect(addMember("road", " Nouveau@Example.org ", "reader")).toBeNull();
    expect(addMember("road", "nouveau@example.org", "reader")).toContain("déjà membre");
    expect(groupById("road")!.members.at(-1)).toEqual({ email: "nouveau@example.org", name: "", roleId: "reader" });
  });

  it("garde l'historique d'un rôle et le restaure", () => {
    const { saveRole, restoreRole, roleById } = useGroups();

    saveRole({ name: "Lecteur", description: "", permissions: ["dossier.view", "dossier.edit"] }, "reader");
    restoreRole("reader", roleById("reader")!.versions[0].id);

    expect(roleById("reader")!.permissions).toEqual(["dossier.view"]);
    expect(roleById("reader")!.versions).toHaveLength(2);
  });

  it("ne modifie pas un rôle fourni et ne supprime rien qui serve encore", () => {
    const { saveRole, removeRole, removeGroup, roleById, groupById } = useGroups();

    saveRole({ name: "Autre", description: "", permissions: [] }, "group-admin");
    removeRole("instructor");
    removeGroup("culture");
    removeGroup("archive");

    expect(roleById("group-admin")!.name).toBe("Admin de groupe");
    expect(roleById("instructor")).toBeDefined();
    expect(groupById("culture")).toBeDefined();
    expect(groupById("archive")).toBeUndefined();
  });

  it("restaure les accès d'une analyse", () => {
    const { accessOf, saveAccess, restoreAccess } = useGroups();

    saveAccess("a1", { groupIds: ["road"], people: [] });
    restoreAccess("a1", accessOf("a1").versions[0].id);

    expect(accessOf("a1").groupIds).toEqual(["culture"]);
  });
});
