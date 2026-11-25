import { defineConfig, mergeConfig } from "vitest/config";

import viteConfig from "./vite.config";

// mergeConfig : on hérite du plugin Vue, de l'alias "@" et de __APP_VERSION__ de vite.config.ts.
// Pas de seconde déclaration à maintenir.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      setupFiles: ["./vitest.setup.ts"],
      globalSetup: ["./vitest.global-setup.ts"],
      include: ["src/**/*.test.ts"],
      exclude: ["e2e/**", "node_modules/**", "dist/**"], // e2e = Playwright
      restoreMocks: true,
      coverage: {
        provider: "v8",
        reporter: ["text", "lcov", "html"],
        include: ["src/**/*.{ts,vue}"], // sans ça, les fichiers jamais importés ne comptent pas
        exclude: ["src/test/**", "src/main.ts", "src/**/*.d.ts", "src/**/*.test.ts"],
        // Plancher global : juste en dessous de la couverture mesurée (voir « Couverture » dans README.md).
        // Mesure de départ : instructions 0,21 %, branches 0,04 %, fonctions 0,24 %, lignes 0,24 %.
        thresholds: { statements: 0.2, branches: 0.03, functions: 0.2, lines: 0.2 },
      },
    },
  }),
);