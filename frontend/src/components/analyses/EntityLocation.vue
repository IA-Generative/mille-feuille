<script setup lang="ts">
import { computed, ref } from "vue";

import ZoneCrop from "@/components/analyses/ZoneCrop.vue";
import ZoneDrawer from "@/components/analyses/ZoneDrawer.vue";
import { useEntityLocations, type ZonePage, type ZoneRect } from "@/composables/useEntityLocations";
import { useLabelExamples } from "@/composables/useLabelExamples";
import type { LabelDefinition } from "@/types/analyse";

const props = defineProps<{ entityId: string; labels: LabelDefinition[] }>();

const { locationOf, update, addZone, removeZone } = useEntityLocations();
const { listOf } = useLabelExamples();

const location = computed(() => locationOf(props.entityId));
const input = ref<HTMLInputElement | null>(null);
const activeId = ref<string | null>(null);

const labelOptions = computed(() => [
  { value: "", text: "Toutes les pages du dossier" },
  ...props.labels.map((label) => ({ value: label.id, text: label.name || "(sans nom)" })),
]);

// Les pages sur lesquelles on peut désigner la zone : les images d'exemple du label choisi, puis celles ajoutées à la main.
const pages = computed<ZonePage[]>(() => {
  const fromLabel = location.value.labelId
    ? listOf(location.value.labelId)
        .filter((example) => example.previewUrl)
        .map((example) => ({ id: example.id, name: example.name, url: example.previewUrl! }))
    : [];
  return [...fromLabel, ...location.value.pages];
});

const active = computed(() => pages.value.find((page) => page.id === activeId.value) ?? null);

function setLabel(value: string | number | undefined) {
  activeId.value = null;
  update(props.entityId, { labelId: value ? String(value) : null });
}

function onFile(event: Event) {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  target.value = "";
  if (!file) return;
  const page = { id: `page-${Date.now()}`, name: file.name, url: URL.createObjectURL(file) };
  update(props.entityId, { pages: [...location.value.pages, page] });
  activeId.value = page.id;
}

function toggle(pageId: string) {
  activeId.value = activeId.value === pageId ? null : pageId;
}

function onAdd(rect: ZoneRect) {
  if (active.value) addZone(props.entityId, active.value.id, rect);
}

const rectsOf = (pageId: string) => location.value.zones[pageId] ?? [];
</script>

<template>
  <div class="entity-location">
    <DsfrSelect
      :model-value="location.labelId ?? ''"
      label="Où chercher"
      hint="Seules les pages classées dans ce label sont lues pour cette entité."
      :options="labelOptions"
      :disabled="labels.length === 0"
      @update:model-value="setLabel"
    />
    <p v-if="labels.length === 0" class="entity-location__note">Aucun label de classification défini : l'entité est cherchée dans toutes les pages.</p>

    <div class="entity-location__zones">
      <p class="entity-location__legend">Zones <span class="entity-location__optional">(facultatif)</span></p>
      <p class="entity-location__note">
        Sur un document type, désignez l'endroit où se trouve l'information : le modèle lit cette zone en priorité. À faire seulement
        pour les documents où l'emplacement est connu ; les autres restent lus avec la définition.
      </p>

      <ul v-if="pages.length > 0" class="entity-location__pages">
        <li v-for="page in pages" :key="page.id" class="entity-location__page" :class="{ 'entity-location__page--active': activeId === page.id }">
          <img :src="page.url" alt="" class="entity-location__thumb" />
          <span class="entity-location__meta">
            <span class="entity-location__name" :title="page.name">{{ page.name }}</span>
            <span v-if="rectsOf(page.id).length > 0" class="entity-location__state entity-location__state--set">
              {{ rectsOf(page.id).length }} zone{{ rectsOf(page.id).length > 1 ? "s" : "" }} définie{{ rectsOf(page.id).length > 1 ? "s" : "" }}
            </span>
            <span v-else class="entity-location__state">Aucune zone</span>
          </span>
          <DsfrButton
            :label="activeId === page.id ? 'Fermer' : rectsOf(page.id).length > 0 ? 'Modifier' : 'Dessiner'"
            secondary
            size="sm"
            @click="toggle(page.id)"
          />
        </li>
      </ul>
      <p v-else class="entity-location__note">
        {{ location.labelId ? "Ce label n'a pas d'image d'exemple." : "Choisissez un label pour utiliser ses exemples," }}
        ou ajoutez une page.
      </p>

      <div v-if="active" class="entity-location__draw">
        <p class="entity-location__note">
          Tracez un rectangle sur « {{ active.name }} » pour ajouter une zone ; une page peut en avoir plusieurs.
        </p>
        <ZoneDrawer :url="active.url" :rects="rectsOf(active.id)" @add="onAdd" />
        <ul v-if="rectsOf(active.id).length > 0" class="entity-location__rects">
          <li v-for="(rect, index) in rectsOf(active.id)" :key="index" class="entity-location__rect">
            <span class="entity-location__number">{{ index + 1 }}</span>
            <ZoneCrop :url="active.url" :rect="rect" />
            <DsfrButton
              :label="`Retirer la zone ${index + 1}`"
              icon-only
              tertiary
              no-outline
              icon="ri-delete-bin-line"
              size="sm"
              @click="removeZone(entityId, active.id, index)"
            />
          </li>
        </ul>
      </div>

      <div>
        <DsfrButton label="Ajouter une page" tertiary size="sm" icon="ri-image-add-line" @click="input?.click()" />
        <input ref="input" class="entity-location__input" type="file" accept="image/png,image/jpeg,image/webp" tabindex="-1" @change="onFile" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.entity-location {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.entity-location__note {
  margin: 0;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}

.entity-location__legend {
  margin: 0;
  font-weight: 600;
  font-size: 0.875rem;
}

.entity-location__optional {
  font-weight: 400;
  color: var(--text-mention-grey);
}

.entity-location__zones {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-alt-grey);
}

.entity-location__pages {
  list-style: none;
  margin: 0;
  padding: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.entity-location__page {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.375rem 0.5rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
}

.entity-location__page--active {
  border-color: #9d6cff;
}

.entity-location__thumb {
  width: 2.5rem;
  height: 3.25rem;
  flex-shrink: 0;
  object-fit: cover;
  border-radius: 0.25rem;
}

.entity-location__meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.entity-location__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.875rem;
}

.entity-location__state {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.entity-location__state--set {
  color: #6a2fd0;
  font-weight: 600;
}

.entity-location__rects {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.entity-location__rect {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.entity-location__number {
  min-width: 1.25rem;
  padding: 0 0.25rem;
  background: #9d6cff;
  color: #fff;
  font-size: 0.75rem;
  line-height: 1.25rem;
  text-align: center;
}

.entity-location__input {
  display: none;
}

.entity-location__draw {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
  max-width: 100%;
}
</style>
