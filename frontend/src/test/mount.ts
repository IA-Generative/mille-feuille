import { mount, type ComponentMountingOptions } from "@vue/test-utils";
import type { Component } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";

/** Comme mount(), avec un router mémoire pour que <RouterLink> (ex. BackLink) se résolve. VueDsfr vient du setup. */
export function mountWithDsfr<T extends Component>(component: T, options: ComponentMountingOptions<T> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/:pathMatch(.*)*", component: { template: "<div />" } }],
  });
  return mount(component, {
    ...options,
    global: { ...options.global, plugins: [router, ...(options.global?.plugins ?? [])] },
  });
}
