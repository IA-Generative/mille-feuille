import { vi } from "vitest";

/** Importe un module avec un état neuf : les ref de module (useProfile, useTheme…) repartent de leur valeur initiale. */
export async function freshImport<T>(load: () => Promise<T>): Promise<T> {
  vi.resetModules();
  return load();
}