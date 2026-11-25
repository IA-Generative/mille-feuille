import { describe, expect, it } from "vitest";
import { paginationPages } from "./paginationPages";

describe("paginationPages", () => {
  it("génère une page par numéro, avec un href pour rester focusable", () => {
    expect(paginationPages(2)).toEqual([
      { label: "1", title: "Page 1", href: "#" },
      { label: "2", title: "Page 2", href: "#" },
    ]);
  });
  it("renvoie au moins une page", () => {
    expect(paginationPages(0)).toHaveLength(1);
  });
});