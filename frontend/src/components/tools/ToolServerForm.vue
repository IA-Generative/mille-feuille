<script setup lang="ts">
import ToolAudienceField from "@/components/tools/ToolAudienceField.vue";
import ToolAuthChoice from "@/components/tools/ToolAuthChoice.vue";
import ToolServiceAccountToggle from "@/components/tools/ToolServiceAccountToggle.vue";
import ToolVisibilityChoice from "@/components/tools/ToolVisibilityChoice.vue";
import type { ToolServerDraft } from "@/types/tool";

const draft = defineModel<ToolServerDraft>({ required: true });
</script>

<template>
  <div class="tool-server-form">
    <DsfrInput v-model="draft.name" label="Nom" label-visible placeholder="Légifrance" required />
    <DsfrInput
      v-model="draft.url"
      label="Adresse du serveur MCP"
      label-visible
      placeholder="https://exemple.gouv.fr/mcp"
      hint="Les adresses internes et locales sont refusées."
      required
    />
    <ToolAuthChoice v-model="draft.authMode" />
    <template v-if="draft.authMode === 'token_exchange'">
      <ToolAudienceField v-model="draft.audience" />
      <ToolServiceAccountToggle />
    </template>
    <ToolVisibilityChoice v-model="draft.visibility" />
  </div>
</template>

<style scoped>
.tool-server-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
</style>
