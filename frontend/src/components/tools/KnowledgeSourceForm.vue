<script setup lang="ts">
import ToolAudienceField from "@/components/tools/ToolAudienceField.vue";
import ToolAuthChoice from "@/components/tools/ToolAuthChoice.vue";
import ToolServiceAccountToggle from "@/components/tools/ToolServiceAccountToggle.vue";
import ToolVisibilityChoice from "@/components/tools/ToolVisibilityChoice.vue";
import type { KnowledgeSourceDraft } from "@/types/knowledge";

const draft = defineModel<KnowledgeSourceDraft>({ required: true });
</script>

<template>
  <div class="knowledge-source-form">
    <DsfrInput v-model="draft.name" label="Nom" label-visible placeholder="Textes de référence" required />
    <DsfrInput
      v-model="draft.url"
      label="Adresse de l'API"
      label-visible
      placeholder="https://base-de-connaissances.exemple.gouv.fr"
      hint="L'API doit respecter le contrat de la base de connaissances. Les adresses internes et locales sont refusées."
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
.knowledge-source-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
</style>
