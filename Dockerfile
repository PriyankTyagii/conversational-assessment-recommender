
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
# Install the CPU-only torch build first — the default PyPI resolution for
# sentence-transformers' torch dependency pulls the full CUDA build (nvidia-*
# packages, triton, cuda-toolkit), which is gigabytes larger and pushes
# runtime memory past free-tier limits (e.g. Render's 512MB) even though no
# GPU is ever used here. Installing CPU-only torch first satisfies the
# dependency without pip reaching for the CUDA variant.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image so a fresh deploy doesn't need to
# hit the HF Hub during the cold-start window.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY app ./app

EXPOSE 8000

# Railway/Render inject PORT at runtime and expect the app to bind to it;
# fall back to 8000 for local `docker run`. Shell form is required so $PORT
# actually expands (exec-form CMD would pass it through literally).
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
