#!/usr/bin/env bash
# Build and install llama.cpp Vulkan for AMD BC-250.
# Pin: build 9596 (tag b9596, commit 18ef86ece).
set -euo pipefail

LLAMA_CPP_REF="${LLAMA_CPP_REF:-18ef86ece}"
LLAMA_SRC="${LLAMA_SRC:-/workspace/llama.cpp}"
BUILD_DIR="${BUILD_DIR:-${LLAMA_SRC}/build}"
DST_BIN="/usr/local/bin"
DST_LIB="/usr/local/lib"
NO_COOPMAT2="${NO_COOPMAT2:-auto}"  # auto | yes | no

usage() {
  cat <<'EOF'
Usage: build-llama-vulkan.sh [--no-coopmat2] [--coopmat2] [--ref COMMIT]

  --no-coopmat2   Force-disable GL_NV_cooperative_matrix2 (BC-250 shader gen incomplete)
  --coopmat2      Attempt full coopmat2 build (may fail link on RADV GFX1013)
  --ref COMMIT    llama.cpp git ref (default: 18ef86ece / b9596)

After install: run smoke test (128 tokens, esc_ratio < 0.01) before enabling Vulkan unit.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-coopmat2) NO_COOPMAT2=yes; shift ;;
    --coopmat2) NO_COOPMAT2=no; shift ;;
    --ref) LLAMA_CPP_REF="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ ! -d "$LLAMA_SRC/.git" ]]; then
  echo "Missing llama.cpp clone at $LLAMA_SRC" >&2
  exit 1
fi

cd "$LLAMA_SRC"
git fetch origin --tags 2>/dev/null || true
git checkout "$LLAMA_CPP_REF"
git clean -fd ggml/src/ggml-vulkan/vulkan-shaders/feature-tests/ 2>/dev/null || true

patch_disable_coopmat2() {
  python3 - <<'PY'
from pathlib import Path
p = Path("ggml/src/ggml-vulkan/CMakeLists.txt")
text = p.read_text()
block = """    test_shader_extension_support(
        \"GL_NV_cooperative_matrix2\"
        \"${CMAKE_CURRENT_SOURCE_DIR}/vulkan-shaders/feature-tests/coopmat2.comp\"
        \"GGML_VULKAN_COOPMAT2_GLSLC_SUPPORT\"
    )

    test_shader_extension_support(
        \"GL_NV_cooperative_matrix_decode_vector\"
        \"${CMAKE_CURRENT_SOURCE_DIR}/vulkan-shaders/feature-tests/coopmat2_decode_vector.comp\"
        \"GGML_VULKAN_COOPMAT2_DECODE_VECTOR_GLSLC_SUPPORT\"
    )
"""
replacement = """    # BC-250/RADV: coopmat2 glslc test passes but shader gen is incomplete
    set(GGML_VULKAN_COOPMAT2_GLSLC_SUPPORT OFF)
    set(GGML_VULKAN_COOPMAT2_DECODE_VECTOR_GLSLC_SUPPORT OFF)
"""
if block not in text:
    raise SystemExit("coopmat2 cmake block not found — already patched?")
p.write_text(text.replace(block, replacement))
print("patched: coopmat2 disabled")
PY
}

restore_coopmat2_cmake() {
  git checkout -- ggml/src/ggml-vulkan/CMakeLists.txt
}

if [[ "$NO_COOPMAT2" == "yes" ]]; then
  patch_disable_coopmat2
elif [[ "$NO_COOPMAT2" == "auto" ]]; then
  restore_coopmat2_cmake
  rm -rf "$BUILD_DIR"
  cmake -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON -DLLAMA_BUILD_SERVER=ON
  if ! cmake --build "$BUILD_DIR" --target ggml-vulkan -j"$(nproc)" 2>/tmp/llama-vulkan-build.log; then
    echo "coopmat2 build failed — retrying with --no-coopmat2" >&2
    patch_disable_coopmat2
  elif nm -D "$BUILD_DIR/bin/libggml-vulkan.so" 2>/dev/null | grep -q ' U matmul.*cm2'; then
    echo "coopmat2 link incomplete — retrying with --no-coopmat2" >&2
    patch_disable_coopmat2
  else
    echo "coopmat2 build OK"
    NO_COOPMAT2=skip
  fi
fi

if [[ "$NO_COOPMAT2" != "skip" ]]; then
  rm -rf "$BUILD_DIR"
  cmake -B "$BUILD_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_VULKAN=ON \
    -DLLAMA_BUILD_SERVER=ON
  cmake --build "$BUILD_DIR" -j"$(nproc)"
fi

undefined_cm2="$(nm -D "$BUILD_DIR/bin/libggml-vulkan.so" 2>/dev/null | grep -c ' U matmul.*cm2' || true)"
if [[ "$undefined_cm2" != "0" ]]; then
  echo "ERROR: libggml-vulkan has $undefined_cm2 undefined cm2 symbols" >&2
  exit 1
fi

systemctl stop llama-server-bielik llama-server-bielik-cpu 2>/dev/null || true
killall llama-server 2>/dev/null || true
sleep 2

cp -f "$BUILD_DIR/bin/llama-server" "$BUILD_DIR/bin/llama-bench" "$BUILD_DIR/bin/llama-cli" "$DST_BIN/"
cp -a "$BUILD_DIR/bin/lib"*.so* "$DST_LIB/"
ldconfig
if command -v restorecon >/dev/null 2>&1; then
  restorecon -Rv "$DST_BIN/llama-server" "$DST_BIN/llama-bench" "$DST_BIN/llama-cli" "$DST_LIB/lib"*.so* 2>/dev/null || true
fi

echo "=== installed ==="
"$DST_BIN/llama-server" --version | head -2
ls -la "$DST_LIB/libllama-server-impl.so"

echo "=== smoke test (requires running server on :8006) ==="
if curl -sf http://127.0.0.1:8006/v1/models >/dev/null 2>&1; then
  python3 - <<'PY'
import json, urllib.request
req = urllib.request.Request(
    "http://127.0.0.1:8006/v1/completions",
    data=json.dumps({"prompt": '{"overall_fit":', "max_tokens": 128, "temperature": 0.1}).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=120) as r:
    t = json.load(r)["choices"][0]["text"]
esc = t.count("\x1b")
ratio = esc / max(len(t), 1)
print(f"esc_ratio={ratio:.2f} sample={t[:80]!r}")
if ratio > 0.01:
    raise SystemExit("FAIL: ESC degeneration detected")
print("smoke OK")
PY
else
  echo "Server not running — skip smoke test"
fi

echo "Done. Restart: systemctl restart llama-server-bielik  # or llama-server-bielik-cpu"
