<script setup lang="ts">
import { ref } from "vue";

import ToolTestModal from "@/components/tools/ToolTestModal.vue";
import type { Tool } from "@/types/tool";
import { TOOLS_PREVIEW } from "@/utils/featureFlags";

defineProps<{ tool: Tool }>();
const opened = ref(false);
</script>

<template>
  <template v-if="TOOLS_PREVIEW">
    <DsfrButton label="Tester" icon="ri-play-line" tertiary no-outline size="sm" @click="opened = true" />
    <ToolTestModal v-model:opened="opened" :tool="tool" />
  </template>
</template>
