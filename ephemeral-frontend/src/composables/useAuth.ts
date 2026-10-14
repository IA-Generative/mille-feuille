import { computed, ref } from "vue";

import { API_BASE_URL, apiFetch } from "@/api";

const email = ref<string | null>(null);
const checked = ref(false);

export function useAuth() {
  const fetchProfile = async () => {
    try {
      const me = await apiFetch<{ email: string }>("/api/auth/me");
      email.value = me.email;
    } catch {
      email.value = null;
    } finally {
      checked.value = true;
    }
  };

  // Le backend renvoie ici après le login (URL absolue, autorisée via EPHEMERAL_FRONTEND_URL).
  const login = () => {
    window.location.href = `${API_BASE_URL}/api/auth/login?redirect=${encodeURIComponent(window.location.origin + "/")}`;
  };

  const logout = async () => {
    try {
      const data = await apiFetch<{ redirectUrl: string }>("/api/auth/logout", { method: "POST" });
      window.location.href = data.redirectUrl;
    } catch {
      email.value = null;
    }
  };

  return { email: computed(() => email.value), checked: computed(() => checked.value), fetchProfile, login, logout };
}
