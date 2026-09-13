FROM debian:bookworm-slim AS stockfish-builder
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential ca-certificates \
    && git clone --depth 1 --branch sf_19 https://github.com/official-stockfish/Stockfish.git /stockfish-src \
    && make -C /stockfish-src/src -j2 build ARCH=x86-64

FROM python:3.12-slim
WORKDIR /app
COPY --from=stockfish-builder /stockfish-src/src/stockfish /usr/local/bin/stockfish
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

