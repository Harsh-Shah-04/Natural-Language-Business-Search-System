# Deployment

Deployment-only files. Nothing here is imported by the application; removing
this directory and `backend/Dockerfile` returns the project to a local-only
setup.

- `hf-space-README.md` — front-matter README for the Hugging Face Space repo
  (declares `sdk: docker` and `app_port: 7860`). Copied to the Space repo root
  as `README.md` by `push-hf-space.sh`.
- `push-hf-space.sh` — syncs `backend/` into a clone of the Space repo and
  pushes. Reads `HF_TOKEN` and `HF_SPACE` from the environment; writes no
  secrets to disk.

The backend runs on Hugging Face Spaces (Docker) and the frontend on Vercel.
See the Deployment guide in the root README for the full walkthrough.
