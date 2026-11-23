<script setup lang="ts">
import { computed } from "vue";

import { useBackendStatus, type BackendHealth } from "@/composables/useBackendStatus";

const { version, health } = useBackendStatus();

const LABELS: Record<BackendHealth, string> = {
  unknown: "Vérification en cours",
  healthy: "Opérationnel",
  unhealthy: "Dégradé",
  unreachable: "Injoignable",
};
const label = computed(() => LABELS[health.value]);
</script>

<template>
  <span class="backend-status" role="status">
    <span class="backend-status__dot" :class="`backend-status__dot--${health}`" aria-hidden="true" />
    <span>Backend {{ version ? `v${version}` : "" }} · {{ label }}</span>
  </span>
</template>

<style scoped>
.backend-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}

.backend-status__dot {
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 50%;
  background: var(--background-contrast-grey);
}

.backend-status__dot--healthy {
  background: var(--background-action-high-success);
}

.backend-status__dot--unhealthy {
  background: var(--background-action-high-warning);
}

.backend-status__dot--unreachable {
  background: var(--background-action-high-error);
}
</style>
