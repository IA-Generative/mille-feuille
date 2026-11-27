<script setup lang="ts">
/** Le graphe d'un thème de ressemblance : un amas par groupe, sur lequel on zoome. La liste à côté dit la même chose. */
import { bindWebGLLayer, createContoursProgram } from "@sigma/layer-webgl";
import Graph from "graphology";
import type Sigma from "sigma";
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";

import GraphControls from "@/components/crossSearch/GraphControls.vue";
import { createRenderer } from "@/components/crossSearch/graphRenderer";
import { readPalette } from "@/components/crossSearch/graphTheme";
import type { ResemblanceTheme } from "@/components/crossSearch/resemblanceThemes";
import { DOSSIER_COLOR, type Resemblance } from "@/types/crossSearch";
import { layoutClusters, type ClusterLayout } from "@/utils/clusterLayout";
import folderIcon from "@gouvfr/dsfr/dist/icons/document/folder-2-fill.svg?url";

const props = defineProps<{
  theme: ResemblanceTheme;
  /** Les seuls groupes du thème affiché. */
  groups: Resemblance[];
  dossierNames: Record<string, string>;
  groupId: string | null;
}>();
const emit = defineEmits<{ group: [id: string | null] }>();

const container = ref<HTMLElement | null>(null);
const isUnavailable = ref(false);
/** Titres des amas (des boutons, utilisables au clavier), replacés à chaque image pour suivre le zoom. */
const titles = shallowRef<{ groupId: string; label: string; left: number; top: number }[]>([]);
const layout = computed<ClusterLayout>(() => layoutClusters(props.groups));

let renderer: Sigma | null = null;
let graph = new Graph();
let palette: ReturnType<typeof readPalette>;

const labelOf = (groupId: string) => props.groups.find((g) => g.id === groupId)?.label ?? "";
const shorten = (label: string) => (label.length > 24 ? `${label.slice(0, 23)}…` : label);

/**
 * Des repères cachés aux coins de chaque amas : sigma cadre sur les nœuds, et ferait sans eux déborder le contour d'un
 * thème à un seul groupe.
 */
const frameCorners = () =>
  layout.value.clusters.flatMap(({ groupId, x, y, radius }) => [
    { id: `${groupId}:corner-low`, x: x - radius, y: y - radius },
    { id: `${groupId}:corner-high`, x: x + radius, y: y + radius },
  ]);

function buildGraph() {
  const next = new Graph();
  for (const node of layout.value.nodes) {
    const isHub = !node.dossierId;
    next.addNode(node.id, {
      x: node.x,
      y: node.y,
      groupId: node.groupId,
      shape: isHub ? "circle" : "square",
      size: isHub ? 15 : 12,
      color: isHub ? props.theme.color : DOSSIER_COLOR,
      image: isHub ? props.theme.icon : folderIcon,
      iconColor: "#ffffff",
      label: "",
    });
  }
  for (const { source, target } of layout.value.edges) next.addEdge(source, target, { size: 1.2, color: palette.edge });
  for (const { id, x, y } of frameCorners()) next.addNode(id, { x, y, size: 0, label: "" });
  return next;
}

/**
 * Hors du groupe choisi, tout s'efface. Les noms des dossiers n'apparaissent qu'une fois sur un groupe (ou s'il n'y en a
 * qu'un) : de plus loin ils se chevauchent. Le nom du centre est déjà dans le titre de l'amas.
 */
function highlight() {
  const isActive = (groupId: string) => !props.groupId || groupId === props.groupId;
  const isClose = Boolean(props.groupId) || layout.value.clusters.length === 1;
  for (const node of layout.value.nodes) {
    if (!graph.hasNode(node.id)) continue;
    const active = isActive(node.groupId);
    graph.mergeNodeAttributes(node.id, {
      color: active ? (node.dossierId ? DOSSIER_COLOR : props.theme.color) : palette.dimmed,
      iconColor: active ? "#ffffff" : palette.border,
      label: active && isClose && node.dossierId ? shorten(props.dossierNames[node.dossierId]!) : "",
    });
  }
  graph.forEachEdge((edge, _, source) => {
    const active = isActive(graph.getNodeAttribute(source, "groupId"));
    graph.setEdgeAttribute(edge, "color", active ? palette.edge : palette.dimmed);
  });
}

function placeTitles() {
  if (!renderer) return;
  titles.value = layout.value.clusters.map((cluster) => {
    // Juste au-dessus du contour, plus bas que le rayon réservé à l'amas.
    const top = renderer!.graphToViewport({ x: cluster.x, y: cluster.y + cluster.radius * 0.75 });
    return { groupId: cluster.groupId, label: labelOf(cluster.groupId), left: top.x, top: top.y };
  });
}

/** Le contour de chaque amas, dessiné par sigma autour de ses nœuds ; il grandit avec le zoom. */
function drawClusters() {
  if (!renderer) return;
  const origin = renderer.graphToViewport({ x: 0, y: 0 });
  const unit = Math.abs(renderer.graphToViewport({ x: 1, y: 0 }).x - origin.x);
  const ratio = renderer.getCamera().ratio;
  for (const cluster of layout.value.clusters) {
    const nodes = layout.value.nodes.filter((node) => node.groupId === cluster.groupId).map((node) => node.id);
    const program = createContoursProgram(nodes, {
      radius: unit * ratio * 1.1,
      zoomToRadiusRatioFunction: (current: number) => current,
      levels: [{ color: `${props.theme.color}22`, threshold: 0.5 }],
      border: { color: `${props.theme.color}aa`, thickness: 1.5 },
    });
    bindWebGLLayer("clusters" as never, renderer as never, program, `cluster-${cluster.groupId}`);
  }
}

/** Amène la caméra sur le groupe choisi, ou revient à tout le thème. */
function moveCamera() {
  if (!renderer || !container.value) return;
  const camera = renderer.getCamera();
  const cluster = layout.value.clusters.find((c) => c.groupId === props.groupId);
  if (!cluster || layout.value.clusters.length < 2) {
    camera.reset();
    return;
  }
  const center = renderer.graphToViewport(cluster);
  const edge = renderer.graphToViewport({ x: cluster.x + cluster.radius, y: cluster.y });
  const { clientWidth, clientHeight } = container.value;
  const ratio = (camera.ratio * 2 * Math.abs(edge.x - center.x)) / (0.9 * Math.min(clientWidth, clientHeight));
  const { x, y } = renderer.graphToFramedGraph(cluster);
  camera.animate({ x, y, ratio }, { duration: 500 });
}

function render() {
  renderer?.kill();
  renderer = null;
  titles.value = [];
  if (!container.value || !props.groups.length) return;
  palette = readPalette(container.value);
  graph = buildGraph();
  try {
    renderer = createRenderer(graph, container.value, palette);
  } catch (error) {
    console.warn("Le graphe ne peut pas s'afficher", error);
    isUnavailable.value = true;
    return;
  }
  renderer.on("clickNode", ({ node }) => emit("group", graph.getNodeAttribute(node, "groupId")));
  renderer.on("clickStage", () => emit("group", null));
  renderer.on("afterRender", placeTitles);
  for (const { id } of frameCorners()) renderer.setNodeState(id, { isHidden: true });
  highlight();
  renderer.refresh();
  // Avant tout zoom : le rayon des contours se mesure sur la vue du thème entier.
  drawClusters();
  moveCamera();
}

// Les couleurs sont lues au dessin : on redessine quand le thème clair ou sombre change.
const themeObserver = new MutationObserver(render);

onMounted(() => {
  themeObserver.observe(document.documentElement, { attributeFilter: ["data-fr-theme"] });
  render();
});
watch(() => props.groups, render);
watch(
  () => props.groupId,
  () => {
    highlight();
    moveCamera();
  },
);
onBeforeUnmount(() => {
  themeObserver.disconnect();
  renderer?.kill();
});

function reset() {
  emit("group", null);
  renderer?.getCamera().reset();
}
</script>

<template>
  <div class="cluster-graph">
    <p v-if="!groups.length" class="fr-text--sm fr-p-2w">Aucun rapprochement de ce type.</p>
    <p v-else-if="isUnavailable" class="fr-text--sm fr-p-2w">
      Le graphe ne peut pas s'afficher sur ce navigateur. La liste à côté donne les mêmes rapprochements.
    </p>
    <div ref="container" class="cluster-graph__canvas" role="img" :aria-label="`Graphe des rapprochements : ${theme.label}`" />
    <button
      v-for="title in titles"
      :key="title.groupId"
      type="button"
      class="cluster-graph__title"
      :aria-pressed="groupId === title.groupId"
      :style="{ left: `${title.left}px`, top: `${title.top}px` }"
      @click="emit('group', title.groupId)"
    >
      {{ title.label }}
    </button>
    <GraphControls v-if="!isUnavailable" @zoom-in="renderer?.getCamera().zoomIn()" @zoom-out="renderer?.getCamera().zoomOut()" @reset="reset" />
  </div>
</template>

<style scoped>
.cluster-graph {
  position: relative;
  height: 38rem;
  overflow: hidden;
}

.cluster-graph__canvas {
  position: absolute;
  inset: 0;
}

.cluster-graph__title {
  position: absolute;
  padding: 0.125rem 0.625rem;
  /* Au-dessus de l'amas, pour ne pas masquer de nœud. */
  transform: translate(-50%, -50%);
  border: 1px solid var(--border-default-grey);
  border-radius: 999px;
  background: var(--background-default-grey);
  font-size: 0.75rem;
  font-weight: 700;
  white-space: nowrap;
}
</style>
