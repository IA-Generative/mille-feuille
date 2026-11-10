import { ref } from "vue";

// MAQUETTE : « où chercher » une entité n'est pas envoyé au backend. L'état vit en mémoire, par entité, le temps de la
// page. À remplacer par l'API : le label et les zones feront partie de la définition de l'entité (donc versionnés).

/** Un rectangle, en fractions (0 à 1) de la page. */
export interface ZoneRect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Une page sur laquelle on peut dessiner une zone : un exemple du label, ou une image ajoutée à la main. */
export interface ZonePage {
  id: string;
  name: string;
  /** Aperçu de la page (URL d'objet) : n'existe que tant que la page est ouverte. */
  url: string;
}

export interface EntityLocation {
  /** Label de classification dans lequel chercher ; null = toutes les pages. */
  labelId: string | null;
  /** Pages ajoutées à la main, en plus des exemples du label. */
  pages: ZonePage[];
  /** Zones par page, facultatives : une page peut en avoir plusieurs, ou aucune (pas d'entrée). */
  zones: Record<string, ZoneRect[]>;
}

const locations = ref<Record<string, EntityLocation>>({});

const empty = (): EntityLocation => ({ labelId: null, pages: [], zones: {} });

export function useEntityLocations() {
  const locationOf = (entityId: string): EntityLocation => locations.value[entityId] ?? empty();

  function update(entityId: string, patch: Partial<EntityLocation>) {
    locations.value = { ...locations.value, [entityId]: { ...locationOf(entityId), ...patch } };
  }

  function addZone(entityId: string, pageId: string, rect: ZoneRect) {
    const zones = { ...locationOf(entityId).zones, [pageId]: [...(locationOf(entityId).zones[pageId] ?? []), rect] };
    update(entityId, { zones });
  }

  function removeZone(entityId: string, pageId: string, index: number) {
    const zones = { ...locationOf(entityId).zones };
    const rest = (zones[pageId] ?? []).filter((_, i) => i !== index);
    if (rest.length > 0) zones[pageId] = rest;
    else delete zones[pageId];
    update(entityId, { zones });
  }

  /** Nombre total de zones de l'entité, toutes pages confondues. */
  function zoneCount(entityId: string): number {
    return Object.values(locationOf(entityId).zones).reduce((sum, rects) => sum + rects.length, 0);
  }

  function forget(entityId: string) {
    const { [entityId]: gone, ...rest } = locations.value;
    gone?.pages.forEach((page) => URL.revokeObjectURL(page.url));
    locations.value = rest;
  }

  return { locationOf, update, addZone, removeZone, zoneCount, forget };
}
