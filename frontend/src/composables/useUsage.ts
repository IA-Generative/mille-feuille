import { ref, watch, type Ref } from "vue";

import { apiFetch } from "@/utils/api";
import type { Usage, UsageSums } from "@/types/usage";

interface SumsOut {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  calls: number;
}

interface UsageOut {
  days: number;
  totals: SumsOut;
  by_step: (SumsOut & { step: string })[];
  by_day: (SumsOut & { day: string })[];
  by_model: (SumsOut & { model: string })[];
  by_user: (SumsOut & { user_id: string | null; display: string | null })[];
}

function toSums(raw: SumsOut): UsageSums {
  return {
    inputTokens: raw.input_tokens,
    outputTokens: raw.output_tokens,
    totalTokens: raw.total_tokens,
    calls: raw.calls,
  };
}

function toUsage(raw: UsageOut): Usage {
  return {
    days: raw.days,
    totals: toSums(raw.totals),
    byStep: raw.by_step.map((row) => ({ step: row.step, ...toSums(row) })),
    byDay: raw.by_day.map((row) => ({ day: row.day, ...toSums(row) })),
    byModel: raw.by_model.map((row) => ({ model: row.model, ...toSums(row) })),
    byUser: raw.by_user.map((row) => ({ userId: row.user_id, display: row.display, ...toSums(row) })),
  };
}

interface Options {
  /** Consommation de tout le monde (GET /api/admin/usage), restreinte à `userId` quand il est renseigné. */
  admin?: boolean;
  userId?: Ref<string | null>;
  /** Ne charge pas au montage : l'onglet d'administration appelle `reload` à sa première ouverture. */
  lazy?: boolean;
}

export function useUsage(days: Ref<number>, options: Options = {}) {
  const usage = ref<Usage | null>(null);
  const loading = ref(false);
  const error = ref("");

  async function reload() {
    loading.value = true;
    error.value = "";
    const params = new URLSearchParams({ days: String(days.value) });
    if (options.admin && options.userId?.value) params.set("user_id", options.userId.value);
    try {
      const path = options.admin ? "/api/admin/usage" : "/api/usage/me";
      usage.value = toUsage(await apiFetch<UsageOut>(`${path}?${params}`));
    } catch {
      error.value = "Impossible de récupérer la consommation.";
    } finally {
      loading.value = false;
    }
  }

  // Tant qu'un onglet paresseux n'a pas été ouvert, un changement de période ne déclenche rien.
  let started = !options.lazy;
  watch([days, () => options.userId?.value], () => started && reload(), { immediate: !options.lazy });

  return {
    usage,
    loading,
    error,
    reload: () => {
      started = true;
      return reload();
    },
  };
}
