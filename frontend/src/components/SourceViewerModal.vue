<script setup lang="ts">
/**
 * Modale « source » du chat : affiche la page citée par l'assistant (capture
 * avec les zones citées encadrées) à côté du texte de la page, avec le passage
 * d'où vient l'extrait surligné. Si la source cite plusieurs pages, on navigue
 * de l'une à l'autre.
 */
import { computed, onBeforeUnmount, ref, watch } from "vue";

import type { ChatWindowSource } from "@/components/ChatWindow.vue";
import { API_BASE_URL, apiFetch } from "@/utils/api";
import { highlightExcerpt } from "@/utils/highlightExcerpt";

interface PageView {
  id: string;
  page_number: number;
  content: string | null;
  has_screenshot: boolean;
  document_name: string;
}

const props = defineProps<{
  opened: boolean;
  dossierId: string;
  source: ChatWindowSource | null;
}>();
const emit = defineEmits<{ close: [] }>();

const pageIndex = ref(0);
const page = ref<PageView | null>(null);
const imageUrl = ref<string | null>(null);
const isLoading = ref(false);
const error = ref<string | null>(null);

const pages = computed(() => props.source?.pages ?? []);
const currentPageRef = computed(() => pages.value[pageIndex.value]);
const boxes = computed(
  () => props.source?.boundingBoxes?.filter((box) => box.pageId === currentPageRef.value?.id) ?? [],
);
const segments = computed(() => highlightExcerpt(page.value?.content ?? "", props.source?.excerpt));
const title = computed(() => {
  const name = page.value?.document_name ?? "Source";
  const number = currentPageRef.value?.pageNumber;
  return number ? `${name} — page ${number}` : name;
});

function releaseImage() {
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value);
  imageUrl.value = null;
}

// Jeton anti-course : une réponse tardive d'une page déjà quittée est ignorée.
let loadToken = 0;

async function loadPage() {
  const source = props.source;
  const ref_ = currentPageRef.value;
  releaseImage();
  page.value = null;
  error.value = null;
  if (!source?.dossierDocumentId || !ref_) {
    error.value = "Cette source n'est pas rattachée à une page de document.";
    return;
  }
  const token = ++loadToken;
  isLoading.value = true;
  const base = `/api/dossiers/${props.dossierId}/documents/${source.dossierDocumentId}/pages/${ref_.id}`;
  try {
    const view = await apiFetch<PageView>(base);
    if (token !== loadToken) return;
    page.value = view;
    if (view.has_screenshot) {
      const response = await fetch(`${API_BASE_URL}${base}/screenshot`, { credentials: "include" });
      if (token !== loadToken) return;
      if (response.ok) imageUrl.value = URL.createObjectURL(await response.blob());
    }
  } catch {
    if (token === loadToken) error.value = "Impossible de charger cette page.";
  } finally {
    if (token === loadToken) isLoading.value = false;
  }
}

watch(
  () => [props.opened, props.source?.id] as const,
  ([opened]) => {
    if (opened) {
      pageIndex.value = 0;
      loadPage();
    } else {
      loadToken++;
      releaseImage();
    }
  },
);
watch(pageIndex, () => props.opened && loadPage());
onBeforeUnmount(releaseImage);
</script>

<template>
  <DsfrModal :opened="opened" :title="title" icon="ri-file-text-line" size="lg" @close="emit('close')">
    <div v-if="pages.length > 1" class="source-viewer__pager">
      <DsfrButton
        label="Page précédente"
        icon="ri-arrow-left-s-line"
        tertiary
        no-outline
        size="sm"
        :disabled="pageIndex === 0"
        @click="pageIndex--"
      />
      <span class="fr-text--sm">Page {{ pageIndex + 1 }} sur {{ pages.length }} citées</span>
      <DsfrButton
        label="Page suivante"
        icon="ri-arrow-right-s-line"
        icon-right
        tertiary
        no-outline
        size="sm"
        :disabled="pageIndex === pages.length - 1"
        @click="pageIndex++"
      />
    </div>

    <p v-if="source?.excerpt" class="fr-text--sm source-viewer__excerpt">« {{ source.excerpt }} »</p>

    <p v-if="isLoading" class="fr-text--sm source-viewer__state">Chargement de la page…</p>
    <DsfrAlert v-else-if="error" alert type="error" small :description="error" />

    <div v-else-if="page" class="source-viewer" :class="{ 'source-viewer--with-image': imageUrl }">
      <figure v-if="imageUrl" class="source-viewer__figure">
        <div class="source-viewer__image-wrapper">
          <img :src="imageUrl" :alt="`Capture de la page ${page.page_number}`" class="source-viewer__image" />
          <span
            v-for="box in boxes"
            :key="box.id"
            class="source-viewer__box"
            :style="{
              left: `${box.xMin * 100}%`,
              top: `${box.yMin * 100}%`,
              width: `${(box.xMax - box.xMin) * 100}%`,
              height: `${(box.yMax - box.yMin) * 100}%`,
            }"
            aria-hidden="true"
          />
        </div>
      </figure>

      <div class="source-viewer__text">
        <h3 class="fr-text--sm source-viewer__text-title">Texte de la page</h3>
        <p v-if="!page.content" class="fr-text--sm source-viewer__state">Aucun texte extrait pour cette page.</p>
        <p v-else class="source-viewer__content">
          <template v-for="(segment, index) in segments" :key="index">
            <mark v-if="segment.highlighted" class="source-viewer__mark">{{ segment.text }}</mark>
            <template v-else>{{ segment.text }}</template>
          </template>
        </p>
      </div>
    </div>
  </DsfrModal>
</template>

<style scoped>
.source-viewer__pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.source-viewer__excerpt {
  margin: 0 0 1rem;
  padding-left: 0.75rem;
  border-left: 3px solid var(--border-plain-yellow-tournesol, #c8aa39);
  font-style: italic;
  color: var(--text-mention-grey);
  overflow-wrap: anywhere;
}

.source-viewer__state {
  color: var(--text-mention-grey);
}

.source-viewer {
  display: grid;
  gap: 1.5rem;
  grid-template-columns: minmax(0, 1fr);
}

@media (min-width: 768px) {
  .source-viewer--with-image {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
}

.source-viewer__figure {
  margin: 0;
}

.source-viewer__image-wrapper {
  position: relative;
  border: 1px solid var(--border-default-grey);
  line-height: 0;
}

.source-viewer__image {
  width: 100%;
  height: auto;
}

/* Zone citée : encadrée sur la capture (coordonnées normalisées en %). */
.source-viewer__box {
  position: absolute;
  border: 2px solid var(--border-plain-yellow-tournesol, #c8aa39);
  background: rgba(255, 224, 70, 0.3);
  border-radius: 2px;
  pointer-events: none;
}

.source-viewer__text {
  min-width: 0;
}

.source-viewer__text-title {
  margin: 0 0 0.5rem;
  font-weight: 700;
  color: var(--text-mention-grey);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.source-viewer__content {
  margin: 0;
  max-height: 60vh;
  overflow-y: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.6;
}

.source-viewer__mark {
  background: rgba(255, 224, 70, 0.55);
  color: inherit;
  padding: 0.05em 0.1em;
  border-radius: 0.2em;
}
</style>
