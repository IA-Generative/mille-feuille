import { vi } from "vitest";

export const FROZEN_NOW = "2026-01-15T10:00:00.000Z";

export function freezeTime(when: string | Date = FROZEN_NOW) {
  vi.useFakeTimers(); // Vitest ne fige pas nextTick/queueMicrotask par défaut : Vue continue de se mettre à jour
  vi.setSystemTime(new Date(when));
}

export function advance(ms: number) {
  return vi.advanceTimersByTimeAsync(ms);
}
