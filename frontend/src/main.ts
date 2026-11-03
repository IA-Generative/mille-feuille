import "@gouvfr/dsfr/dist/dsfr.min.css";
import "@gouvfr/dsfr/dist/utility/icons/icons-system/icons-system.min.css";
import VueDsfr from "@gouvminint/vue-dsfr";
import { createApp } from "vue";

import App from "./App.vue";
import { router } from "./router";
import { initTheme } from "./composables/useTheme";

// Applique le thème avant le montage de l'app pour éviter le flash (FOUC).
// Lit localStorage en synchrone, puis synchronise avec le backend si connecté.
initTheme();

const app = createApp(App);
app.use(router);
app.use(VueDsfr);
app.mount("#app");
