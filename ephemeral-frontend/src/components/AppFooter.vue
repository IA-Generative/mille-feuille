<script setup lang="ts">
import { onMounted, ref } from "vue";

import { apiFetch } from "@/api";
import { MILLEFEUILLE_URL } from "@/config";

defineEmits<{ changelog: []; docs: [] }>();

const frontendVersion = __APP_VERSION__;
const millefeuilleUrl = MILLEFEUILLE_URL;
const backendVersion = ref("…");

onMounted(async () => {
  try {
    backendVersion.value = (await apiFetch<{ version: string }>("/api/version")).version;
  } catch {
    backendVersion.value = "indisponible";
  }
});
</script>

<template>
  <footer class="footer fr-text--xs">
    <span>
      UneFeuille, version restreinte de
      <a v-if="millefeuilleUrl" :href="millefeuilleUrl" target="_blank" rel="noopener noreferrer">MilleFeuille</a>
      <template v-else>MilleFeuille</template>
    </span>
    <span aria-hidden="true">·</span>
    <span>Frontend v{{ frontendVersion }}</span>
    <span aria-hidden="true">·</span>
    <span>Backend v{{ backendVersion }}</span>
    <span aria-hidden="true">·</span>
    <a href="#" @click.prevent="$emit('changelog')">Journal des versions</a>
    <span aria-hidden="true">·</span>
    <a href="#" @click.prevent="$emit('docs')">Documentation API</a>
  </footer>
</template>

<style scoped>
.footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.5rem;
  padding: 2rem 1rem;
  color: var(--text-mention-grey);
}
</style>
