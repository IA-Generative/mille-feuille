<script setup lang="ts">
import { ref, watch } from "vue";

import AppModal from "@/components/AppModal.vue";
import { FEEDBACK_REASON_LABELS, type FeedbackReasonCode } from "@/types/conversation";

const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ submit: [reasons: FeedbackReasonCode[], comment: string | null] }>();

const reasonOptions = (Object.keys(FEEDBACK_REASON_LABELS) as FeedbackReasonCode[]).map((code) => ({
  name: code,
  value: code,
  label: FEEDBACK_REASON_LABELS[code],
}));

const reasons = ref<FeedbackReasonCode[]>([]);
const comment = ref("");

watch(opened, (isOpened) => {
  if (isOpened) {
    reasons.value = [];
    comment.value = "";
  }
});

function submit() {
  emit("submit", reasons.value, comment.value.trim() || null);
  opened.value = false;
}
</script>

<template>
  <AppModal
    :opened="opened"
    @close="opened = false"
    title="Que s'est-il mal passé ?"
    icon="ri-thumb-down-line"
    :actions="[
      { label: 'Annuler', secondary: true, onClick: () => (opened = false) },
      { label: 'Envoyer', onClick: submit },
    ]"
  >
    <DsfrCheckboxSet v-model="reasons" legend="Raison(s)" :options="reasonOptions" small />
    <DsfrInput v-model="comment" label="Commentaire (optionnel)" label-visible is-textarea class="fr-mt-2w" />
  </AppModal>
</template>
