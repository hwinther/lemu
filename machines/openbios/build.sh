#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Make pc-bios/openbios-sparc32 and pc-bios/openbios-sparc64 from OpenBIOS at
# the commit of roms/openbios with the patches in patches/, in Docker.
# usage: build.sh
#
# The sparc32 build takes the patches whose names don't have -sparc64-:
# 0001 (esp selection timeout), 0008 (Stop-A/op_enter) and 0018 (the
# cs4231's "intr"). The sparc64
# build takes all of them. 0006, 0007, 0010, 0013, 0014 and 0017 change
# generic code that sparc32 also runs (client.fs "forth", fcode.fs
# "instance", pathres.fs my-unit, ofmem align_ptr() and claim, the 64-bit
# FCode table), but they were only tested on sparc64, so they are named
# -sparc64- and sparc32 leaves them out. The numbers have gaps, see
# README.md.
#
# The sparc32 build also tokenizes drivers/cgthree.fs into QEMU,cgthree.bin.
# The tree gets ../sun4m/cgthree/cgthree.fs there first, so that build is the
# same source as pc-bios/QEMU,cgthree.bin; this script only compares the two
# and leaves pc-bios/QEMU,cgthree.bin alone (../sun4m/cgthree/build.sh makes
# it). pc-bios/openbios-ppc is not touched.
#
# Everything goes in and out of the container through stdin and stdout, so a
# remote Docker engine works too. Settings, from the environment:
#   OPENBIOS_IMAGE  image to build in (default debian:13; the cross compiler,
#                   fcode-utils and xsltproc are installed when missing)
#   OPENBIOS_GIT    OpenBIOS repository to clone, as the container sees it
#                   (default: the URL of roms/openbios in .gitmodules)
#   DOCKER_ARGS     more arguments for docker run, such as a volume that
#                   holds a clone to give as OPENBIOS_GIT
set -e
cd "$(dirname "$0")"
top=../..
ref=$(git -C $top ls-tree HEAD roms/openbios | awk '{print $3}')
url=$(git -C $top config -f .gitmodules submodule.roms/openbios.url)
[ -n "$ref" ] && [ -n "$url" ] || { echo "no roms/openbios commit or URL" >&2; exit 1; }
image=${OPENBIOS_IMAGE:-debian:13}
git=${OPENBIOS_GIT:-$url}
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

cat > "$out/inner.sh" <<'EOF'
set -e
exec 3>&1 1>&2
git config --global init.defaultBranch master
need=
command -v sparc64-linux-gnu-gcc >/dev/null || need="$need gcc-sparc64-linux-gnu binutils-sparc64-linux-gnu"
command -v toke >/dev/null || need="$need fcode-utils"
command -v xsltproc >/dev/null || need="$need xsltproc"
command -v git >/dev/null || need="$need git ca-certificates"
command -v make >/dev/null || need="$need build-essential"
if [ -n "$need" ]; then
    apt-get update -qq && apt-get install -y -qq --no-install-recommends $need python3 >/dev/null
fi
cd /b
git clone -q "$OPENBIOS_GIT" src
git -C src -c advice.detachedHead=false checkout -q "$OPENBIOS_REF"
mkdir out
for arch in sparc32 sparc64; do
    git clone -q src $arch
    cd $arch
    if [ $arch = sparc32 ]; then
        patches=$(ls /b/patches/*.patch | grep -v -- -sparc64-)
        cp /b/cgthree.fs drivers/cgthree.fs
    else
        patches=$(ls /b/patches/*.patch)
    fi
    for p in $patches; do
        echo "$arch: applying $(basename "$p")"
        git apply "$p"
    done
    ./config/scripts/switch-arch $arch
    make build-verbose > ../$arch-build.log 2>&1 || { tail -50 ../$arch-build.log; exit 1; }
    cp obj-$arch/openbios-builtin.elf ../out/openbios-$arch
    [ $arch = sparc32 ] && cp obj-sparc32/QEMU,cgthree.bin ../out/
    cd ..
done
{
    echo "OpenBIOS $OPENBIOS_REF"
    sparc64-linux-gnu-gcc --version | head -1
    echo "toke $(dpkg-query -W -f '${Version}' fcode-utils 2>/dev/null)"
} > out/build-info.txt
tar -C out -cf - . >&3
EOF

mkdir "$out/res"
tar -C "$out" -cf - inner.sh -C "$PWD" patches -C "$PWD/../sun4m/cgthree" cgthree.fs |
    docker run -i --rm $DOCKER_ARGS -e OPENBIOS_REF="$ref" -e OPENBIOS_GIT="$git" \
        "$image" sh -c 'mkdir -p /b && cd /b && tar -xf - && sh inner.sh' |
    tar -C "$out/res" -xf -
cp "$out/res/openbios-sparc32" "$out/res/openbios-sparc64" $top/pc-bios/
cat "$out/res/build-info.txt"
if cmp -s "$out/res/QEMU,cgthree.bin" "$top/pc-bios/QEMU,cgthree.bin"; then
    echo "QEMU,cgthree.bin of this build is the same as pc-bios/QEMU,cgthree.bin"
else
    echo "WARNING: QEMU,cgthree.bin of this build differs from pc-bios/QEMU,cgthree.bin" >&2
fi
ls -l $top/pc-bios/openbios-sparc32 $top/pc-bios/openbios-sparc64
