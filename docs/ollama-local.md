# Hub LLM local avec Ollama

En local, un modèle servi par [Ollama](https://ollama.com) peut tenir lieu de hub LLM : Ollama expose l'API compatible
OpenAI (`/v1`) que le backend et les workers utilisent déjà (`OPENAI_API_BASE_URL`). L'exemple ci-dessous sert
**SmolVLM-500M** pour décrire les images, sans hub distant.

## Démarrer

1. Dans `.env` (copie de `.env.example`), décommenter le bloc « Hub LLM local avec Ollama » :

   ```bash
   OLLAMA_MODELS=hf.co/ggml-org/SmolVLM-500M-Instruct-GGUF:Q8_0
   OPENAI_API_KEY=ollama
   OPENAI_API_BASE_URL=http://ollama:11434/v1
   VLM_MODEL=hf.co/ggml-org/SmolVLM-500M-Instruct-GGUF:Q8_0
   ```

2. Lancer la stack avec le profil `ollama` :

   ```bash
   docker compose --profile ollama up --build
   ```

   `ollama` démarre, puis `ollama-pull` télécharge les modèles d'`OLLAMA_MODELS` (une fois : ils restent dans le volume
   `ollama-data`) et s'arrête.

3. Vérifier : `curl localhost:11434/v1/models`, ou `GET /api/models` côté backend.

Avec un Ollama installé sur la machine plutôt que dans Docker : `OPENAI_API_BASE_URL=http://host.docker.internal:11434/v1`
et pas de profil `ollama`.

## À savoir

- **Un seul hub** : `OPENAI_API_BASE_URL` vaut pour tout. Avec Ollama, `LLM_MODEL` (classification, extraction, agents) et
  les embeddings viennent aussi d'Ollama : ajouter à `OLLAMA_MODELS` un modèle de texte (`LLM_MODEL=...`) et, pour la
  recherche, un modèle d'embeddings. SmolVLM-500M seul ne sait que lire des images.
- **SmolVLM n'est pas dans la bibliothèque d'Ollama** : il vient de Hugging Face (`hf.co/ggml-org/...`, GGUF). Cette
  configuration n'a pas été vérifiée de bout en bout : si Ollama ne charge pas la partie vision (le dépôt a un fichier
  `mmproj` séparé), la réponse ignore l'image. À tester avec une image avant de s'en servir.
