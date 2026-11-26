import type { DueInfo } from "@/types/dossier";
import { dayOffset, NO_VALUE, parseCalendarDate } from "@/utils/dates";

export type DueTone = "none" | "ok" | "warning" | "danger" | "overdue";

// MOCK (#172) : seuils de couleur de l'analyse, en jours restants.
const THRESHOLDS = { ok: 30, warning: 7 };

/** Libellé et niveau d'une date d'échéance : la couleur n'est jamais le seul signal. */
export function dueInfo(iso: string | null): { label: string; tone: DueTone; days: number | null } {
  const days = iso ? dayOffset(iso) : NaN;
  // Une date absente ou illisible n'est pas « dans NaN j » : elle compte comme sans échéance.
  if (Number.isNaN(days)) return { label: "Sans échéance", tone: "none", days: null };
  if (days < 0) return { label: `Échéance dépassée depuis ${-days} j`, tone: "overdue", days };
  if (days === 0) return { label: "Échéance aujourd'hui", tone: "danger", days };
  const label = `Échéance dans ${days} j`;
  if (days < THRESHOLDS.warning) return { label, tone: "danger", days };
  if (days <= THRESHOLDS.ok) return { label, tone: "warning", days };
  return { label, tone: "ok", days };
}

/** Libellé d'une échéance calculée par le serveur (`compact` : version courte pour une colonne de tableau). */
export function dueLabel(due: DueInfo, compact = false): string {
  if (due.level === "closed") return "Dossier clos";
  if (compact) {
    if (due.daysLeft < 0) return `Dépassée de ${-due.daysLeft} j`;
    return due.daysLeft === 0 ? "Aujourd'hui" : `Dans ${due.daysLeft} j`;
  }
  if (due.daysLeft < 0) return `Échéance dépassée depuis ${-due.daysLeft} j`;
  if (due.daysLeft === 0) return "Échéance aujourd'hui";
  return `Échéance dans ${due.daysLeft} j`;
}

/** Date d'échéance (AAAA-MM-JJ, un jour du calendrier) en français, sans décalage de fuseau. */
export function formatDueDate(dueAt: string): string {
  const day = parseCalendarDate(dueAt);
  return day ? day.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }) : NO_VALUE;
}
