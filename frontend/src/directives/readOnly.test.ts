import { render, screen, waitFor } from "@testing-library/vue";
import { describe, expect, it } from "vitest";
import { defineComponent, nextTick, ref } from "vue";

import { vReadOnly } from "@/directives/readOnly";

const locked = ref(true);
const late = ref(false);
const Zone = defineComponent({
  directives: { readOnly: vReadOnly },
  setup: () => ({ locked, late }),
  template: `
    <div v-read-only="locked">
      <input aria-label="Nom" />
      <button>Enregistrer</button>
      <button disabled>Indisponible</button>
      <button aria-expanded="false">Historique des versions</button>
      <button data-read>Historique</button>
      <nav><button>Page suivante</button></nav>
      <button v-if="late">Restaurer</button>
    </div>`,
});

const disabled = (name: string) => screen.getByRole<HTMLButtonElement>("button", { name }).disabled;

describe("v-read-only", () => {
  it("désactive ce qui modifie, laisse ce qui consulte, et suit le contenu et le droit", async () => {
    locked.value = true;
    late.value = false;
    render(Zone);

    expect(screen.getByRole<HTMLInputElement>("textbox", { name: "Nom" }).disabled).toBe(true);
    expect([disabled("Enregistrer"), disabled("Historique des versions"), disabled("Historique"), disabled("Page suivante")])
      .toEqual([true, false, false, false]);

    late.value = true;
    await nextTick();
    await waitFor(() => expect(disabled("Restaurer")).toBe(true));

    locked.value = false;
    await nextTick();
    // On ne réactive que ce qu'on avait désactivé.
    expect([disabled("Enregistrer"), disabled("Restaurer"), disabled("Indisponible")]).toEqual([false, false, true]);
  });
});
