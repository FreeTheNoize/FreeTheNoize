FROM python:3.13-slim
# The audio-only ffmpeg pinned in packaging/ffmpeg/assets.txt (~4 MB, hash
# checked). Until a build is pinned for this architecture (exit 3), Debian's
# ffmpeg, which brings ~300 MB of libraries. Any other failure stops the build.
COPY packaging/ffmpeg/fetch.py packaging/ffmpeg/assets.txt /tmp/ffmpeg/
RUN python /tmp/ffmpeg/fetch.py /usr/local/bin \
    || { [ $? = 3 ] && apt-get update && apt-get install -y --no-install-recommends ffmpeg \
         && rm -rf /var/lib/apt/lists/*; } \
    && rm -rf /tmp/ffmpeg
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY freethenoize ./freethenoize
RUN pip install --no-cache-dir .
ENV FTN_DATA_DIR=/data FTN_MUSIC_DIR=/music FTN_HOST=0.0.0.0 FTN_PORT=8765
VOLUME ["/data", "/music"]
EXPOSE 8765
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/api/health')"
CMD ["freethenoize", "serve"]
