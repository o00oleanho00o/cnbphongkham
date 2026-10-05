#!/usr/bin/env bash
# Download the chat and embedding models into an Ollama that runs natively (see infra/ubuntu).
# For the compose `ollama` profile the one-shot service `ollama-pull` does the same.
#
#   infra/scripts/pull-models.sh                      # Qwen3-8B Q5_K_M + bge-m3
#   PEMA_LLM_MODEL_PULL=hf.co/Qwen/Qwen3-8B-GGUF:Q6_K infra/scripts/pull-models.sh
#
# The Ollama library only ships qwen3:8b as q4_K_M, q8_0 and fp16. Q5_K_M (5.85 GB) and Q6_K (6.73 GB) come
# from the official GGUF repository through the hf.co/<repo>:<quant> form. Quality vs size on a 12 GB card:
# Q5_K_M leaves the most room for context; Q6_K is closer to Q8 quality. Decide with the evals, not by taste.
set -euo pipefail

LLM="${PEMA_LLM_MODEL_PULL:-hf.co/Qwen/Qwen3-8B-GGUF:Q5_K_M}"
EMBED="${PEMA_EMBED_MODEL_PULL:-bge-m3}"

command -v ollama >/dev/null || { echo "ollama not installed (infra/ubuntu/HUONG-DAN-UBUNTU.md, step 5)" >&2; exit 1; }

ollama pull "$LLM"
ollama pull "$EMBED"
ollama list

# Give the chat model a short stable name so the dashboard setting does not carry a repository path.
# `num_ctx` here is the default context the model is loaded with; OLLAMA_CONTEXT_LENGTH overrides it.
MODELFILE="$(mktemp)"
trap 'rm -f "$MODELFILE"' EXIT
printf 'FROM %s\nPARAMETER num_ctx 16384\n' "$LLM" >"$MODELFILE"
ollama create pema-chat -f "$MODELFILE"
echo "models ready: pema-chat (chat), $EMBED (embeddings, 1024 dimensions)"
