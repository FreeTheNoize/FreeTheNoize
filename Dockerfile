FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY freethenoize ./freethenoize
RUN pip install --no-cache-dir .
ENV FTN_DATA_DIR=/data FTN_MUSIC_DIR=/music FTN_HOST=0.0.0.0 FTN_PORT=8765
VOLUME ["/data", "/music"]
EXPOSE 8765
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/api/health')"
CMD ["freethenoize", "serve"]
