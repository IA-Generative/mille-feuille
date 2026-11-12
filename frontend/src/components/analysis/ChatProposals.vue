<script setup lang="ts">
/**
 * Propositions de modification de l'analyse déposées par le chat dans une
 * réponse (#115) : une carte par proposition, avec accepter / modifier /
 * rejeter. Rien n'est appliqué tant que l'utilisateur n'a pas cliqué. La
 * carte reflète l'état réel côté serveur (une proposition déjà traitée ailleurs
 * s'affiche comme telle).
 */
import { onMounted, ref } from "vue";

import ProposalCard from "@/components/analysis/ProposalCard.vue";
import { mapProposal } from "@/composables/useDossierAnalysis";
import { ApiError, apiFetch } from "@/utils/api";
import { valueToText, type ElementValue, type Proposal } from "@/types/dossierAnalysis";

const props = defineProps<{
  dossierId: string;
  analysisId: string;
  proposalIds: string[];
}>();

const emit = defineEmits<{
  /** Une décision a été prise : le parent peut rafraîchir ce qui dépend de l'analyse. */
  decided: [];
}>();

const proposals = ref<Proposal[]>([]);
const currentTexts = ref<Record<string, string>>({});
const errors = ref<Record<string, string>>({});
const busyId = ref<string | null>(null);
const loadFailed = ref(false);

const base = () => `/api/dossiers/${props.dossierId}/analyses-dossier/${props.analysisId}`;

async function load() {
  loadFailed.value = false;
  try {
    const loaded = await Promise.all(
      props.proposalIds.map(async (id) => mapProposal(await apiFetch<any>(`${base()}/proposals/${id}`))),
    );
    proposals.value = loaded;
    // Valeur retenue des éléments visés, pour montrer le changement proposé.
    if (loaded.some((p) => p.elementId)) {
      const analysis = await apiFetch<any>(base());
      const texts: Record<string, string> = {};
      for (const element of analysis.elements ?? []) {
        const value = element.retained_version?.value;
        if (value) texts[element.id] = valueToText(element.kind, value);
      }
      currentTexts.value = texts;
    }
  } catch {
    loadFailed.value = true;
  }
}

async function decide(proposal: Proposal, action: "accept" | "modify" | "reject", body: object = {}) {
  busyId.value = proposal.id;
  errors.value = { ...errors.value, [proposal.id]: "" };
  try {
    await apiFetch(`${base()}/proposals/${proposal.id}/${action}`, { method: "POST", body: JSON.stringify(body) });
    await load();
    emit("decided");
  } catch (e) {
    errors.value = {
      ...errors.value,
      [proposal.id]: e instanceof ApiError ? e.message : "L'action a échoué",
    };
  } finally {
    busyId.value = null;
  }
}

const accept = (proposal: Proposal) => decide(proposal, "accept");
const modify = (proposal: Proposal, value: ElementValue, reason: string) =>
  decide(proposal, "modify", { value, reason: reason || null });
const reject = (proposal: Proposal, reason: string) => decide(proposal, "reject", { reason: reason || null });

onMounted(load);
</script>

<template>
  <div class="chat-proposals">
    <DsfrAlert v-if="loadFailed" alert type="error" small description="Impossible de charger les propositions de cette réponse." />
    <ProposalCard
      v-for="proposal in proposals"
      :key="proposal.id"
      :proposal="proposal"
      :current-text="proposal.elementId ? (currentTexts[proposal.elementId] ?? null) : null"
      :disabled="busyId === proposal.id"
      :error="errors[proposal.id]"
      @accept="accept(proposal)"
      @modify="(value, reason) => modify(proposal, value, reason)"
      @reject="(reason) => reject(proposal, reason)"
    />
  </div>
</template>

<style scoped>
.chat-proposals {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
</style>
