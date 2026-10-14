#!/bin/sh
# Écrit /tmp/config.js à partir des variables d'environnement du conteneur ; nginx le sert à /config.js (voir
# nginx.conf) et l'interface le lit au chargement. Les scripts de /docker-entrypoint.d/ sont lancés par l'entrypoint de
# l'image nginx, avant le démarrage du serveur.
#
#   API_BASE_URL     adresse du backend ; vide = même hôte. À renseigner (adresse de MilleFeuille) quand ce frontend
#                    est sur un autre hôte : le cookie de session est posé là où le backend reçoit la connexion.
#   MILLEFEUILLE_URL adresse du frontend MilleFeuille, pour le lien de renvoi ; vide = pas de lien.
set -eu

# Les valeurs deviennent des chaînes JavaScript : barres obliques inverses et guillemets sont échappés, et tout
# caractère de contrôle (retour à la ligne compris) est retiré.
js_string() {
  printf '%s' "$1" | tr -d '\000-\037' | sed 's/\\/\\\\/g; s/"/\\"/g'
}

cat > /tmp/config.js <<CONFIG
window.__CONFIG__ = {
  apiBaseUrl: "$(js_string "${API_BASE_URL:-}")",
  millefeuilleUrl: "$(js_string "${MILLEFEUILLE_URL:-}")"
};
CONFIG
echo "40-runtime-config: /tmp/config.js écrit (API_BASE_URL='${API_BASE_URL:-}', MILLEFEUILLE_URL='${MILLEFEUILLE_URL:-}')"
