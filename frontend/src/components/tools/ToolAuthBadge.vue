<script setup lang="ts">
import { computed } from "vue";

import { TOOL_AUTH_LABELS, type ToolAuthMode } from "@/types/tool";

const props = defineProps<{ mode: ToolAuthMode }>();

const badgeType = computed(() => (props.mode === "none" ? "warning" : props.mode === "token_exchange" ? "success" : "info"));
</script>

<template>
  <DsfrBadge :label="TOOL_AUTH_LABELS[mode]" :type="badgeType" small no-icon />
</template>
