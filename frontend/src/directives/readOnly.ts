/**
 * `v-read-only="oui"` : désactive, dans toute une zone, ce qui **modifie** (champs, boutons) en laissant ce qui sert à
 * **consulter** : accordéons et dépliages, onglets, bascules d'aperçu, pagination, fermeture d'une fenêtre, et tout ce
 * qui est marqué `data-read`. Ce n'est qu'un affichage : le serveur refuse de toute façon ce qui n'est pas permis.
 */
import type { Directive } from "vue";

const CONTROLS = "input, textarea, select, button";
const CONSULTATION = "[aria-expanded], [aria-pressed], [role='tab'], .fr-btn--close, [data-read], [data-read] *, nav *";
const MARK = "data-locked";

type Zone = HTMLElement & { readOnlyObserver?: MutationObserver; readOnlyActive?: boolean };

function apply(zone: Zone) {
  for (const control of zone.querySelectorAll<HTMLButtonElement>(zone.readOnlyActive ? CONTROLS : `[${MARK}]`)) {
    if (!zone.readOnlyActive) {
      control.disabled = false;
      control.removeAttribute(MARK);
    } else if (!control.disabled && !control.matches(CONSULTATION)) {
      control.disabled = true;
      control.setAttribute(MARK, "");
    }
  }
}

function update(zone: Zone, active: boolean) {
  const was = zone.readOnlyActive;
  zone.readOnlyActive = active;
  if (active || was) apply(zone);
}

export const vReadOnly: Directive<Zone, boolean> = {
  mounted(zone, { value }) {
    // Le contenu arrive souvent après coup, et un nouveau rendu peut réactiver un bouton : on surveille la zone.
    zone.readOnlyObserver = new MutationObserver(() => zone.readOnlyActive && apply(zone));
    zone.readOnlyObserver.observe(zone, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
    update(zone, value);
  },
  updated: (zone, { value }) => update(zone, value),
  unmounted: (zone) => zone.readOnlyObserver?.disconnect(),
};
