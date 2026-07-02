
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
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
