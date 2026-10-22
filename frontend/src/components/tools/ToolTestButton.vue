<script setup lang="ts">
import { ref } from "vue";

import ToolTestModal from "@/components/tools/ToolTestModal.vue";
import type { Tool } from "@/types/tool";

defineProps<{ tool: Tool }>();
const opened = ref(false);
</script>

<template>
  <!-- Les tools internes sont exécutés par le worker : seuls les tools MCP se testent ici. -->
  <template v-if="tool.kind === 'mcp'">
    <DsfrButton label="Tester" icon="ri-play-line" tertiary no-outline size="sm" @click="opened = true" />
    <ToolTestModal v-model:opened="opened" :tool="tool" />
  </template>
</template>
