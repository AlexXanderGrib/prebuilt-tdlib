# Prebuilt TDLib

> This repository provides prebuilt tdjson binaries of [tdlib](https://github.com/tdlib/td) - C++ library for interacting with Telegram API

## How to use it in JavaScript/TypeScript

Check out [tdlib-native](https://github.com/tdlib-native/tdlib-native)

## How to use it in Python and other programming languages

1. Download correct binary for your platform https://github.com/AlexXanderGrib/prebuilt-tdlib/releases
2. Grab example from https://github.com/tdlib/td/blob/master/example

## Building

The build follows TDLib's [official instructions](https://tdlib.github.io/td/build.html)
and [low-memory build procedure](https://github.com/tdlib/td#building). Only the
shared JSON interface (`tdjson`) is compiled in Release mode. Unix builds use
Clang, Ninja, source splitting and LTO; Linux uses LLD for ThinLTO. OpenSSL and
zlib are linked statically. Linux musl and Windows also link the C++ runtime
statically, so the musl artifact only needs musl itself.

Run **Build TDLib and Release** in GitHub Actions, supply a TDLib tag or commit,
and select `build` to test without publishing. The workflow resolves the ref
once, then builds and verifies the same commit for every platform. Select
`build_publish` to update metadata and publish a release. Artifact filenames
remain the same.

Compiler output is cached across Linux and macOS builds; Linux also caches
ThinLTO's native objects (up to 512 MiB). Windows caches vcpkg binary packages,
uses the 64-bit MSVC host tools for both x86 and x64, and musl uses Docker layer caching. Compilation parallelism
is limited by CPU count and available memory to avoid exhausting the runners.
Artifacts use fast ZIP compression to reduce upload time and storage.

### Local Linux build

```sh
sudo apt-get update
sudo apt-get install clang-14 llvm-14 lld-14 cmake ninja-build gperf php-cli ccache libssl-dev zlib1g-dev
git clone https://github.com/tdlib/td.git td
git -C td checkout YOUR_TDLIB_REF
CC=clang-14 CXX=clang++-14 TDLIB_LINKER=lld-14 bash scripts/build-tdlib.sh td build
strip build/libtdjson.so
python3 scripts/verify-tdjson.py build/libtdjson.so \
  --version "$(sed -nE 's/^project\(TDLib VERSION ([0-9.]+) .*/\1/p' td/CMakeLists.txt)" \
  --commit "$(git -C td rev-parse HEAD)"
```

Use CMake 3.24 or newer for static zlib discovery. The script modifies the TDLib
checkout using upstream's `SplitSource.php`; use a dedicated checkout. It repairs
the known missing comma in that helper in TDLib revision `bc9c263` and checks PHP
syntax before compiling. Set
`CMAKE_BUILD_PARALLEL_LEVEL` to a positive integer to override the job limit.
The smoke test loads the shared library, checks its version and commit, and
executes a JSON request without connecting to Telegram.

### Local musl build

```sh
docker buildx build --file Dockerfile.musl \
  --build-arg GIT_REF=YOUR_TDLIB_REF \
  --output type=local,dest=./result .
```

This builds and verifies `result/libtdjson.so` inside Alpine. `GIT_REF` defaults
to upstream HEAD; CI always passes an exact commit. Optionally pass
`--build-arg BUILD_JOBS=2` to override parallelism. CI runs each architecture on
a native runner, avoiding emulation.
