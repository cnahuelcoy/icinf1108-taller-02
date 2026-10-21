from python:3.13-slim
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./


RUN uv sync --frozen --no-dev

COPY app/ ./app/
COPY public/ ./public/

EXPOSE 3000

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]