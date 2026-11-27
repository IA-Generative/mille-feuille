<script setup lang="ts">
/** Dessine le graphe avec sigma.js. La liste à côté en est l'équivalent textuel (le dessin n'est pas lisible au clavier). */
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import type Sigma from "sigma";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import GraphControls from "@/components/crossSearch/GraphControls.vue";
import { createRenderer } from "@/components/crossSearch/graphRenderer";
import { iconOf, readPalette } from "@/components/crossSearch/graphTheme";
import type { Selection } from "@/types/crossSearch";
import { edgeId, highlightOf, type LinkGraphData } from "@/utils/linkGraph";

const props = defineProps<{ data: LinkGraphData; selection: Selection | null }>();
const emit = defineEmits<{ select: [selection: Selection | null] }>();

const container = ref<HTMLElement | null>(null);
const isUnavailable = ref(false);
let renderer: Sigma | null = null;
let graph = new Graph();
let palette: ReturnType<typeof readPalette>;

/**
 * Le dessin est mis aux proportions du cadre : couché s'il est en hauteur, puis étiré pour que les nœuds et leurs
 * libellés ne s'entassent pas.
 */
function fitFrame(target: Graph, frameRatio: number) {
  const spread = (axis: "x" | "y") => {
    const values = target.mapNodes((_, attributes) => attributes[axis] as number);
    return Math.max(...values) - Math.min(...values);
  };
  if (spread("y") > spread("x")) {
    target.updateEachNodeAttributes((_, attributes) => ({ ...attributes, x: attributes.y, y: attributes.x }));
  }
  const height = spread("y");
  if (!height || !frameRatio) return;
  const stretch = Math.min(2.5, Math.max(1, spread("x") / height / frameRatio));
  target.updateEachNodeAttributes((_, attributes) => ({ ...attributes, y: attributes.y * stretch }));
}

/** Libellé court dans le dessin : le nom complet est dans la liste et le détail. */
const shorten = (label: string) => (label.length > 24 ? `${label.slice(0, 23)}…` : label);

/** Positions de départ en cercle puis ForceAtlas2 : le même résultat donne toujours le même dessin. */
function buildGraph(data: LinkGraphData, frameRatio: number) {
  const next = new Graph();
  data.nodes.forEach((node, index) => {
    const angle = (2 * Math.PI * index) / data.nodes.length;
    next.addNode(node.id, {
      label: shorten(node.label),
      color: node.color,
      size: node.size,
      // Un dossier est un carré arrondi, tout ce qui relie est rond.
      shape: node.type === "dossier" ? "square" : "circle",
      image: iconOf(node),
      iconColor: "#ffffff",
      x: Math.cos(angle),
      y: Math.sin(angle),
    });
  });
  for (const { source, target } of data.edges) {
    next.addEdgeWithKey(edgeId(source, target), source, target, { size: 1.5, color: palette.edge });
  }
  if (next.order > 1) {
    // Gravité faible et répulsion forte : un graphe de quelques dizaines de nœuds doit rester aéré.
    const settings = { ...forceAtlas2.inferSettings(next), strongGravityMode: false, gravity: 0.5, scalingRatio: 20 };
    forceAtlas2.assign(next, { iterations: 300, settings });
    fitFrame(next, frameRatio);
  }
  return next;
}

/** Met en avant la sélection ; le reste s'efface, libellés compris. Le nœud choisi annonce son nombre de liens. */
function highlight() {
  const active = highlightOf(props.data, props.selection);
  const chosen = props.selection?.type === "node" ? props.selection.id : null;

  for (const node of props.data.nodes) {
    if (!graph.hasNode(node.id)) continue;
    const isActive = !active || active.nodes.has(node.id);
    const count = node.id === chosen ? graph.degree(node.id) : 0;
    graph.mergeNodeAttributes(node.id, {
      color: isActive ? node.color : palette.dimmed,
      iconColor: isActive ? "#ffffff" : palette.border,
      size: node.id === chosen ? node.size + 4 : node.size,
      label: !isActive ? "" : shorten(node.label) + (count ? ` · ${count} lien${count > 1 ? "s" : ""}` : ""),
    });
  }
  graph.forEachEdge((key) => {
    const isActive = active?.edges.has(key);
    graph.mergeEdgeAttributes(key, {
      color: isActive ? palette.activeEdge : active ? palette.dimmed : palette.edge,
      size: isActive ? 3.5 : 1.5,
    });
  });
}

/** Le curseur dit que nœuds et traits se cliquent. */
function setPointer(on: boolean) {
  if (container.value) container.value.style.cursor = on ? "pointer" : "";
}

function render() {
  renderer?.kill();
  renderer = null;
  if (!container.value) return;
  palette = readPalette(container.value);
  const { clientWidth, clientHeight } = container.value;
  graph = buildGraph(props.data, clientHeight ? clientWidth / clientHeight : 0);
  try {
    renderer = createRenderer(graph, container.value, palette);
  } catch (error) {
    // Pas de WebGL (poste verrouillé, bureau distant) : la liste reste utilisable.
    console.warn("Le graphe ne peut pas s'afficher", error);
    isUnavailable.value = true;
    return;
  }
  renderer.on("clickNode", ({ node }) => emit("select", { type: "node", id: node }));
  renderer.on("clickEdge", ({ edge }) => {
    const [dossierId, targetId] = graph.extremities(edge);
    emit("select", { type: "link", dossierId: dossierId!, targetId: targetId! });
  });
  renderer.on("clickStage", () => emit("select", null));
  renderer.on("enterNode", () => setPointer(true));
  renderer.on("leaveNode", () => setPointer(false));
  renderer.on("enterEdge", () => setPointer(true));
  renderer.on("leaveEdge", () => setPointer(false));
  highlight();
}

// Les couleurs sont lues au dessin : on redessine quand le thème clair ou sombre change.
const themeObserver = new MutationObserver(render);

onMounted(() => {
  themeObserver.observe(document.documentElement, { attributeFilter: ["data-fr-theme"] });
  render();
});
watch(() => props.data, render);
watch(() => props.selection, highlight);
onBeforeUnmount(() => {
  themeObserver.disconnect();
  renderer?.kill();
});
</script>

<template>
  <div class="link-graph">
    <p v-if="isUnavailable" class="fr-text--sm fr-p-2w">
      Le graphe ne peut pas s'afficher sur ce navigateur. La liste des résultats donne les mêmes liens.
    </p>
    <div ref="container" class="link-graph__canvas" role="img" aria-label="Graphe des liens entre les dossiers trouvés" />
    <GraphControls
      v-if="!isUnavailable"
      @zoom-in="renderer?.getCamera().zoomIn()"
      @zoom-out="renderer?.getCamera().zoomOut()"
      @reset="renderer?.getCamera().reset()"
    />
  </div>
</template>

<style scoped>
.link-graph {
  position: relative;
  height: 38rem;
  /* Trame de points discrète, aux couleurs du thème. */
  background-image: radial-gradient(var(--border-default-grey) 1px, transparent 1px);
  background-size: 20px 20px;
}

.link-graph__canvas {
  position: absolute;
  inset: 0;
}
</style>
