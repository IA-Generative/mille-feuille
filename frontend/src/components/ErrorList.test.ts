import { render, screen } from "@testing-library/vue";
import { describe, expect, it } from "vitest";
import ErrorList from "./ErrorList.vue";

describe("ErrorList", () => {
  it("annonce les erreurs dans une alerte", () => {
    render(ErrorList, { props: { errors: ["Nom requis", "Fichier trop gros"] } });
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Nom requis")).toBeTruthy();
  });
  it("n'affiche rien sans erreur", () => {
    render(ErrorList, { props: { errors: [] } });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
