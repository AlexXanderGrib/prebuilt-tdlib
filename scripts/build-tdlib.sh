#!/usr/bin/env bash
set -euo pipefail

if (( $# < 2 )); then
  echo "Usage: $0 SOURCE_DIR BUILD_DIR [CMake options...]" >&2
  exit 2
fi

source_dir=$(cd "$1" && pwd)
mkdir -p "$2"
build_dir=$(cd "$2" && pwd)
shift 2

# Reserve memory for the linker and OS; TDLib has large translation units even
# after splitting. An explicit CMAKE_BUILD_PARALLEL_LEVEL overrides this limit.
case $(uname -s) in
  Linux)
    cores=$(nproc)
    memory_kb=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
    for limit_file in /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory/memory.limit_in_bytes; do
      if [[ -r "$limit_file" ]]; then
        limit=$(cat "$limit_file")
        if [[ "$limit" =~ ^[0-9]+$ ]] && (( limit / 1024 < memory_kb )); then
          memory_kb=$((limit / 1024))
        fi
      fi
    done
    ;;
  Darwin)
    cores=$(sysctl -n hw.ncpu)
    memory_kb=$(($(sysctl -n hw.memsize) / 1024))
    ;;
  *) echo "This script supports Linux and macOS." >&2; exit 2 ;;
esac

jobs=$(((memory_kb - 2 * 1024 * 1024) / (1536 * 1024)))
(( jobs > 0 )) || jobs=1
(( jobs < cores )) || jobs=$cores
jobs=${CMAKE_BUILD_PARALLEL_LEVEL:-$jobs}
if [[ ! "$jobs" =~ ^[1-9][0-9]*$ ]]; then
  echo "CMAKE_BUILD_PARALLEL_LEVEL must be a positive integer." >&2
  exit 2
fi
echo "Building with $jobs jobs ($cores CPUs, $((memory_kb / 1024)) MiB available)."

export CC=${CC:-clang}
export CXX=${CXX:-clang++}
export CCACHE_BASEDIR="$source_dir"
export CCACHE_NOHASHDIR=true

cmake_options=(
  -G Ninja
  -DCMAKE_BUILD_TYPE=Release
  -DBUILD_TESTING=OFF
  -DTD_ENABLE_LTO=ON
  -DOPENSSL_USE_STATIC_LIBS=TRUE
  -DZLIB_USE_STATIC_LIBS=TRUE
)
if [[ $(uname -s) == Linux ]]; then
  # LLD understands Clang's ThinLTO bitcode without a separate gold plugin.
  # Limit LTO workers too: Ninja's job limit doesn't apply inside the linker.
  link_flags="-fuse-ld=${TDLIB_LINKER:-lld} -Wl,--thinlto-jobs=$jobs"
  # Ninja runs link commands in the build directory. Keep cached native
  # objects separate from ccache's LLVM bitcode and bound disk use.
  link_flags+=" -Wl,--thinlto-cache-dir=lto-cache -Wl,--thinlto-cache-policy=cache_size_bytes=512m"
  cmake_options+=(
    "-DCMAKE_EXE_LINKER_FLAGS=$link_flags"
    "-DCMAKE_SHARED_LINKER_FLAGS=$link_flags"
  )
fi

# Older TDLib revisions split generated sources as well, so generate first.
cmake -S "$source_dir" -B "$build_dir" "${cmake_options[@]}" "$@"
cmake --build "$build_dir" --target prepare_cross_compiling --parallel "$jobs"
(cd "$source_dir" && php SplitSource.php)
cmake -S "$source_dir" -B "$build_dir" "${cmake_options[@]}" "$@"
cmake --build "$build_dir" --target tdjson --parallel "$jobs"

if command -v ccache >/dev/null 2>&1; then
  ccache --show-stats
fi
