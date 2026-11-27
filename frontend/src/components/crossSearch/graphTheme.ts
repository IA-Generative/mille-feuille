/** L'habillage du graphe : pictogrammes et couleurs du DSFR (thème clair ou sombre). */
import articleIcon from "@gouvfr/dsfr/dist/icons/document/article-fill.svg?url";
import fileIcon from "@gouvfr/dsfr/dist/icons/document/file-text-fill.svg?url";
import folderIcon from "@gouvfr/dsfr/dist/icons/document/folder-2-fill.svg?url";
import buildingIcon from "@gouvfr/dsfr/dist/icons/buildings/building-fill.svg?url";
import passportIcon from "@gouvfr/dsfr/dist/icons/map/passport-fill.svg?url";
import pinIcon from "@gouvfr/dsfr/dist/icons/map/map-pin-2-fill.svg?url";
import lockIcon from "@gouvfr/dsfr/dist/icons/system/lock-fill.svg?url";
import userIcon from "@gouvfr/dsfr/dist/icons/user/user-fill.svg?url";

import type { SharedKind } from "@/types/crossSearch";
import type { GraphNode } from "@/utils/linkGraph";

export const KIND_ICONS: Record<SharedKind, string> = {
  person: userIcon,
  company: buildingIcon,
  address: pinIcon,
  identifier: passportIcon,
  document: fileIcon,
  topic: articleIcon,
};

export const iconOf = (node: GraphNode) =>
  node.type === "dossier" ? folderIcon : node.type === "hidden" ? lockIcon : KIND_ICONS[node.kind!];

/** Les couleurs viennent des variables du DSFR : le graphe suit le thème de l'application. */
export function readPalette(element: HTMLElement) {
  const style = getComputedStyle(element);
  const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    background: read("--background-default-grey", "#ffffff"),
    text: read("--text-title-grey", "#161616"),
    border: read("--border-default-grey", "#dddddd"),
    edge: read("--text-disabled-grey", "#929292"),
    activeEdge: read("--border-active-blue-france", "#000091"),
    dimmed: read("--background-contrast-grey", "#eeeeee"),
  };
}
