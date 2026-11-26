#!/usr/bin/env bash
# Audio-only static ffmpeg for the desktop builds and the Docker image.
#
#   packaging/ffmpeg/build.sh <out-dir> [windows]
#
# The stock builds (imageio-ffmpeg, apt) carry every video codec: ~50 MB we
# never use. This one has only what FreeTheNoize does with ffmpeg:
#   - decode anything audio for analysis, playback and conversion
#   - encode wav/aiff/flac/mp3/aac (convert) and wav (playback in WebView)
#   - remux what yt-dlp downloads (opus/webm → .opus, aac/HLS → .m4a)
#   - resize cover art (jpeg/png/webp → jpeg)
#   - stream previews from https/HLS (TLS from the OS: Secure Transport,
#     SChannel; OpenSSL on Linux, linked dynamically)
# Adding a format to convert/ or a filter? Add it to the lists below.
# GPL-2.0-or-later + LAME (LGPL): compatible with the project's GPL-2.0.
set -euo pipefail

OUT=$(mkdir -p "$1" && cd "$1" && pwd)
TARGET=${2:-native}
FFMPEG_VERSION=9.0.2
FFMPEG_SHA256=8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e
LAME_VERSION=3.100
LAME_SHA256=ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e
ZLIB_VERSION=1.3.1
ZLIB_SHA256=9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23

WORK=${WORK:-$(mktemp -d)}
DEPS="$WORK/deps"
mkdir -p "$DEPS" "$WORK/src"
JOBS=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)

fetch() {  # url sha256
  local file="$WORK/src/$(basename "$1")"
  [ -f "$file" ] || curl -fsSL --retry 3 -o "$file" "$1"
  echo "$2  $file" | shasum -a 256 -c - >/dev/null
  tar -xf "$file" -C "$WORK/src"
}

fetch "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" "$FFMPEG_SHA256"
fetch "https://downloads.sourceforge.net/project/lame/lame/$LAME_VERSION/lame-$LAME_VERSION.tar.gz" "$LAME_SHA256"
fetch "https://zlib.net/fossils/zlib-$ZLIB_VERSION.tar.gz" "$ZLIB_SHA256"

CROSS=() HOST=() TLS=() EXE=ffmpeg
case "$TARGET" in
  windows)
    CROSS=(--enable-cross-compile --target-os=mingw32 --arch=x86_64 --cross-prefix=x86_64-w64-mingw32-)
    HOST=(--host=x86_64-w64-mingw32)
    TLS=(--enable-schannel)
    EXE=ffmpeg.exe ;;
  native)
    if [ "$(uname)" = Darwin ]; then
      export MACOSX_DEPLOYMENT_TARGET=${MACOSX_DEPLOYMENT_TARGET:-11.0}
      HOST=(--build="$(uname -m | sed 's/arm64/aarch64/')-apple-darwin")
      TLS=(--enable-securetransport)
    else
      TLS=(--enable-openssl)  # needs libssl-dev to build, libssl3 to run
    fi ;;
  *) echo "unknown target $TARGET" >&2; exit 2 ;;
esac

# zlib: png covers.
(
  cd "$WORK/src/zlib-$ZLIB_VERSION"
  if [ "$TARGET" = windows ]; then
    make -s -f win32/Makefile.gcc PREFIX=x86_64-w64-mingw32- libz.a
    mkdir -p "$DEPS/lib" "$DEPS/include"
    cp libz.a "$DEPS/lib/" && cp zlib.h zconf.h "$DEPS/include/"
  else
    CFLAGS="-O2 -fPIC" ./configure --static --prefix="$DEPS" >/dev/null
    make -s -j"$JOBS" install >/dev/null
  fi
)

# LAME: mp3 encoding (ffmpeg has no native mp3 encoder).
(
  cd "$WORK/src/lame-$LAME_VERSION"
  sed -i.bak '/lame_init_old/d' include/libmp3lame.sym  # symbol removed upstream; breaks newer linkers
  CFLAGS="-O2 -fPIC" ./configure "${HOST[@]}" --prefix="$DEPS" --enable-static --disable-shared \
    --disable-frontend --disable-decoder --disable-gtktest >/dev/null
  make -s -j"$JOBS" install >/dev/null
)

DECODERS="aac,aac_fixed,aac_latm,ac3,alac,ape,dca,eac3,flac,mp1,mp1float,mp2,mp2float,mp3,mp3float,
opus,tta,vorbis,wavpack,wmav1,wmav2,dsd_lsbf,dsd_msbf,dsd_lsbf_planar,dsd_msbf_planar,
pcm_alaw,pcm_mulaw,pcm_f32be,pcm_f32le,pcm_f64be,pcm_f64le,pcm_s16be,pcm_s16be_planar,pcm_s16le,
pcm_s16le_planar,pcm_s24be,pcm_s24le,pcm_s24le_planar,pcm_s32be,pcm_s32le,pcm_s32le_planar,pcm_s8,
pcm_u8,pcm_u16le,pcm_u24le,pcm_u32le,mjpeg,png,webp,bmp,gif"
ENCODERS="aac,flac,libmp3lame,pcm_s16le,pcm_s24le,pcm_s16be,pcm_s24be,pcm_f32le,mjpeg"
DEMUXERS="aac,ac3,aiff,ape,asf,caf,concat,dsf,dts,eac3,flac,matroska,mov,mp3,mpegts,ogg,tta,w64,wav,wv,
hls,image2,image2pipe,image_jpeg_pipe,image_png_pipe,image_webp_pipe,image_bmp_pipe,image_gif_pipe"
MUXERS="adts,aiff,pcm_f32le,flac,ipod,matroska,mov,mp3,mp4,null,ogg,opus,wav,webm,image2,image2pipe,mjpeg"
PARSERS="aac,aac_latm,ac3,dca,flac,mpegaudio,opus,vorbis,mjpeg,png,webp,bmp,gif"
FILTERS="aresample,aformat,anull,volume,alimiter,pan,channelmap,amerge,loudnorm,ebur128,scale,format,null,copy"
BSFS="aac_adtstoasc,null"

cd "$WORK/src/ffmpeg-$FFMPEG_VERSION"
./configure "${CROSS[@]}" --prefix="$WORK/ffmpeg" \
  --pkg-config=false --disable-autodetect --enable-gpl --enable-version3 \
  --enable-static --disable-shared --enable-small --disable-debug --disable-doc \
  --disable-ffplay --disable-ffprobe --disable-avdevice \
  --disable-everything \
  --enable-avcodec --enable-avformat --enable-avfilter --enable-swresample --enable-swscale \
  --enable-zlib --enable-libmp3lame "${TLS[@]}" \
  --enable-decoder="${DECODERS//$'\n'/}" --enable-encoder="$ENCODERS" \
  --enable-demuxer="${DEMUXERS//$'\n'/}" --enable-muxer="$MUXERS" \
  --enable-parser="$PARSERS" --enable-filter="$FILTERS" --enable-bsf="$BSFS" \
  --enable-protocol=file,pipe,http,https,tcp,tls,crypto \
  --extra-cflags="-I$DEPS/include" --extra-ldflags="-L$DEPS/lib $([ "$TARGET" = windows ] && echo -static)" \
  >"$WORK/configure.log" || { tail -30 ffbuild/config.log; exit 1; }
make -s -j"$JOBS" >/dev/null
cp "$EXE" "$OUT/$EXE"
if [ "$TARGET" = windows ]; then x86_64-w64-mingw32-strip "$OUT/$EXE"; else strip "$OUT/$EXE"; fi
ls -l "$OUT/$EXE"
