<script setup lang="ts">
import { computed, ref } from "vue";

import ZoneCrop from "@/components/analyses/ZoneCrop.vue";
import ZoneDrawer from "@/components/analyses/ZoneDrawer.vue";
import { useLabelExamples } from "@/composables/useLabelExamples";
import type { EntityZone, LabelDefinition, ZoneRect } from "@/types/analyse";

// « Où chercher » une entité : dans quels labels de classification (un ou plusieurs, aucun = tout le dossier) et, facultatif,
// dans quelles zones. Les zones se tracent sur les documents d'exemple des labels choisis ; elles sont enregistrées avec
// l'entité.
const props = defineProps<{ labels: LabelDefinition[] }>();
const labelIds = defineModel<string[]>("labelIds", { required: true });
const zones = defineModel<EntityZone[]>("zones", { required: true });

const { listOf } = useLabelExamples();
const activeId = ref<string | null>(null);

const labelOptions = computed(() =>
  props.labels.map((label) => ({ name: `label-${label.id}`, label: label.name || "(sans nom)", value: label.id })),
);

interface ZonePage {
  id: string;
  name: string;
  url: string;
  labelName: string;
}

// Les pages sur lesquelles on peut désigner une zone : les images d'exemple des labels choisis.
const pages = computed<ZonePage[]>(() =>
  props.labels
    .filter((label) => labelIds.value.includes(label.id))
    .flatMap((label) =>
      listOf(label.id)
        .filter((example) => example.previewUrl)
        .map((example) => ({ id: example.id, name: example.name, url: example.previewUrl!, labelName: label.name })),
    ),
);

const pdfCount = computed(
  () =>
    props.labels
      .filter((label) => labelIds.value.includes(label.id))
      .flatMap((label) => listOf(label.id))
      .filter((example) => example.kind === "pdf").length,
);

const active = computed(() => pages.value.find((page) => page.id === activeId.value) ?? null);

function setLabels(value: unknown) {
  const next = (Array.isArray(value) ? value : []) as string[];
  labelIds.value = next;
  // Les zones tracées sur l'exemple d'un label retiré n'ont plus de page où s'afficher : on les retire.
  const kept = new Set(props.labels.filter((label) => next.includes(label.id)).flatMap((label) => listOf(label.id).map((e) => e.id)));
  zones.value = zones.value.filter((zone) => zone.exampleId === null || kept.has(zone.exampleId));
  if (activeId.value && !kept.has(activeId.value)) activeId.value = null;
}

const rectsOf = (pageId: string): ZoneRect[] => zones.value.filter((zone) => zone.exampleId === pageId);

function toggle(pageId: string) {
  activeId.value = activeId.value === pageId ? null : pageId;
}

function onAdd(rect: ZoneRect) {
  if (active.value) zones.value = [...zones.value, { exampleId: active.value.id, ...rect }];
}

function removeZone(pageId: string, index: number) {
  let seen = -1;
  zones.value = zones.value.filter((zone) => zone.exampleId !== pageId || ++seen !== index);
}
</script>

<template>
  <div class="entity-location">
    <DsfrCheckboxSet
      :model-value="labelIds"
      legend="Où chercher"
      :options="labelOptions"
      small
      @update:model-value="setLabels"
    />
    <p class="entity-location__note">
      {{
        labels.length === 0
          ? "Aucun label de classification défini : l'entité est cherchée dans toutes les pages."
          : labelIds.length === 0
            ? "Aucun label coché : l'entité est cherchée dans toutes les pages du dossier."
            : "Seules les pages classées dans l'un des labels cochés sont lues pour cette entité."
      }}
    </p>

    <div v-if="labelIds.length > 0" class="entity-location__zones">
      <p class="entity-location__legend">Zones <span class="entity-location__optional">(facultatif)</span></p>
      <p class="entity-location__note">
        Sur un document d'exemple, désignez l'endroit où se trouve l'information : le modèle lit cette zone en priorité. À faire
        seulement pour les documents où l'emplacement est connu ; les autres restent lus avec la définition.
      </p>

      <ul v-if="pages.length > 0" class="entity-location__pages">
        <li v-for="page in pages" :key="page.id" class="entity-location__page" :class="{ 'entity-location__page--active': activeId === page.id }">
          <img :src="page.url" alt="" class="entity-location__thumb" />
          <span class="entity-location__meta">
            <span class="entity-location__name" :title="page.name">{{ page.name }}</span>
            <span class="entity-location__label">{{ page.labelName }}</span>
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
        Ces labels n'ont pas d'image d'exemple : ajoutez-en dans l'onglet Classification pour tracer une zone.
      </p>
      <p v-if="pdfCount > 0" class="entity-location__note">
        {{ pdfCount }} exemple{{ pdfCount > 1 ? "s" : "" }} PDF : on ne trace de zone que sur une image.
      </p>

      <div v-if="active" class="entity-location__draw">
        <p class="entity-location__note">
          Tracez un rectangle sur « {{ active.name }} » pour ajouter une zone ; un exemple peut en avoir plusieurs.
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
              @click="removeZone(active.id, index)"
            />
          </li>
        </ul>
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
