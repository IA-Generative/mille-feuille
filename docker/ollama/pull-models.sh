#!/bin/sh
# Télécharge dans Ollama les modèles de OLLAMA_MODELS (séparés par des espaces), sauf ceux déjà présents.
# Lancé une fois par le service `ollama-pull` du profil `ollama` (voir docker-compose.yaml).
set -eu

for model in $OLLAMA_MODELS; do
  if ollama list | awk 'NR > 1 {print $1}' | grep -qx "$model"; then
    echo "Modèle déjà présent : $model"
  else
    echo "Téléchargement de $model"
    ollama pull "$model"
  fi
done
