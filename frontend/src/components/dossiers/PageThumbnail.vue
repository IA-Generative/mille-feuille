<script setup lang="ts">
/**
 * Vignette d'une page de document avec, si elles sont fournies, les zones du résultat encadrées. La capture est
 * chargée quand la vignette devient visible (une liste en affiche plusieurs à la fois) : le cookie de session
 * impose un `fetch` avec identifiants, pas un simple `<img src>`.
 */
import { onBeforeUnmount, onMounted, ref } from "vue";

import { API_BASE_URL } from "@/utils/api";

const props = defineProps<{
  dossierId: string;
  documentId: string;
  pageId: string;
  boundingBoxes?: { id: string; xMin: number; yMin: number; xMax: number; yMax: number }[];
}>();

const root = ref<HTMLElement | null>(null);
const imageUrl = ref<string | null>(null);
const failed = ref(false);
let observer: IntersectionObserver | undefined;
let destroyed = false;

async function load() {
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/dossiers/${props.dossierId}/documents/${props.documentId}/pages/${props.pageId}/screenshot`,
      { credentials: "include" },
    );
    if (!response.ok) throw new Error(String(response.status));
    const url = URL.createObjectURL(await response.blob());
    if (destroyed) URL.revokeObjectURL(url);
    else imageUrl.value = url;
  } catch {
    failed.value = true;
  }
}

onMounted(() => {
  if (!root.value || typeof IntersectionObserver === "undefined") return void load();
  observer = new IntersectionObserver((entries) => {
    if (!entries.some((e) => e.isIntersecting)) return;
    observer?.disconnect();
    load();
  });
  observer.observe(root.value);
});

onBeforeUnmount(() => {
  destroyed = true;
  observer?.disconnect();
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value);
});
</script>

<template>
  <div ref="root" class="page-thumbnail" :class="{ 'page-thumbnail--empty': !imageUrl }">
    <div v-if="imageUrl" class="page-thumbnail__wrapper">
      <img :src="imageUrl" alt="" class="page-thumbnail__image" />
      <span
        v-for="box in boundingBoxes"
        :key="box.id"
        class="page-thumbnail__box"
        :style="{
          left: `${box.xMin * 100}%`,
          top: `${box.yMin * 100}%`,
          width: `${(box.xMax - box.xMin) * 100}%`,
          height: `${(box.yMax - box.yMin) * 100}%`,
        }"
      />
    </div>
    <VIcon v-else name="ri-file-text-line" class="page-thumbnail__placeholder" :class="{ 'page-thumbnail__placeholder--failed': failed }" />
  </div>
</template>

<style scoped>
.page-thumbnail {
  flex: 0 0 auto;
  width: 4.5rem;
  aspect-ratio: 1 / 1.414;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.35rem;
  overflow: hidden;
  background: var(--background-alt-grey);
}

.page-thumbnail--empty {
  display: flex;
  align-items: center;
  justify-content: center;
}

.page-thumbnail__placeholder {
  color: var(--text-mention-grey);
}

.page-thumbnail__placeholder--failed {
  opacity: 0.4;
}

.page-thumbnail__wrapper {
  position: relative;
  width: 100%;
  height: 100%;
}

.page-thumbnail__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: top;
}

.page-thumbnail__box {
  position: absolute;
  border: 1px solid #b34000;
  background: #ffd9004d;
}
</style>
