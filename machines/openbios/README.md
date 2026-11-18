# OpenBIOS for sun4m and sun4u

**TL;DR** `pc-bios/openbios-sparc32` and `pc-bios/openbios-sparc64` are
built from OpenBIOS at the commit of `roms/openbios` with the patches in
[patches/](patches). They fix the default disk boot on the SPARCstation 5,
Stop-A in a running guest on sun4m, and on sun4u what Solaris 8 to 10 and
illumos need from the firmware and RAM above 3 GB (up to 8 GB). [build.sh](build.sh) makes both images again.

## What the patches fix

The sparc32 image has 0001 and 0008. The sparc64 image has all fifteen.

| Patch | Guest and symptom |
|---|---|
| 0001 esp: selection timeout is no device | sun4m, all guests: every empty SCSI target was listed as a device of type `UNKNOWN`, the disk on target 3 got only `disk3`, there was no `disk` alias, and the default boot (`disk:a disk`) failed with `No valid state has been set by load or init-program` (QEMU 9.2 and later) |
| 0003 sparc64: whole virtual space available | sun4u, Solaris 8 to 10: `/virtual-memory` `available` ended at `0xff000000`. Solaris 10 panicked with `no nucleus hblk8 to allocate`, Solaris 8 and 9 with `BOP_ALLOC failed` |
| 0004 sparc64: I-cache size in the CPU node | sun4u, Solaris 9: the CPU node gave the E-cache (1 MB, 64-byte lines) as the I-cache; `VAC too big!` |
| 0005 sparc64: no active package after preopen | sun4u, Solaris 10: `/chosen` stayed the active package at the prompt and for client programs, so `' unix-tte is va>tte-data` failed (`exception -13`) |
| 0006 client: no `forth` constant | `11 constant forth` hid the FORTH vocabulary; `only forth also definitions` left 0x11 on the stack. Generic code, tested on sun4u only |
| 0007 fcode: defining words consume `instance` | an FCode program that used `instance` left the flag set, and the next Forth `defer` became an instance word; Solaris 10 crashed in `@`. Generic code, tested on sun4u only |
| 0008 sparc32: op_enter enters the prompt | sun4m, Solaris and SunOS: Stop-A (L1-A) or a break on the serial console turned the machine off (`abort, power off`). It now stops at the prompt, `go` resumes the guest, `boot` resets first |
| 0009 sparc64: UPA and ebus names like OBP | sun4u, Solaris 10: the sabre was `pci@1fe,0` and the ebus children `su@0`, `8042@0`, ...; OBP names them `pci@1f,0` and `su@14,3f8`. Solaris found no console and its installer took no input on ttya |
| 0010 pathres: interposed package gets my-unit | `my-unit` of the disk-label package on a device was 0 0. NetBSD's ofwboot reads the boot device's target with it; with 0011 alone NetBSD rooted on `wd0` instead of `cd0`. Generic code, tested on sun4u only |
| 0011 sparc64: IDE drives under the controller | sun4u, Solaris 10: drives were in a node per channel (`ide@3/ide@1/cdrom@0`). OBP has `ide@3/disk@0,0` and `ide@3/cdrom@2,0` (target = 2 x channel + unit) with `compatible` `ide-disk`/`ide-cdrom`. The installer refused its DVD and the installed disk did not mount root |
| 0013 ofmem: upper bits in align_ptr() | sun4u with more than about 4.3 GB: the firmware's heap (at the top of RAM) lost the upper bits of its physical address, and OpenBIOS stopped before its banner (`Unhandled Exception 0x0000000000000030`, with 8 GB `out of malloc memory (28)!`). Generic code, tested on sun4u only |
| 0014 ofmem: claim where the 1:1 virtual range is free | sun4u with 4 GB: a client `claim` with an alignment took the top of RAM, inside the firmware's own virtual range, and failed; NetBSD stopped with `panic: Can't claim two pages of memory.` Generic code, tested on sun4u only |
| 0015 sparc64: whole physical address in phys.lo | sun4u with more than 4 GB: `claim`, `SUNW,retain` and `translate` cut phys.lo to 32 bits, which 64-bit NetBSD and Solaris read alone. NetBSD's kernel pages were not where it believed, and it panicked under memory pressure (`illegal instruction`) |
| 0016 sparc64: client interface with interrupts off | sun4u, illumos (Tribblix) and Solaris 10: an interrupt in the middle of the client interface's register window walk ran the client's trap handler on a wrong window: in four of seven boots of the Tribblix live CD, an endless window spill or `bad stack overflow at TL 2` |
| 0017 fcode: xa+ and xa1+ in the 64-bit table | sun4u, illumos: two missing entries shifted every 64-bit FCode token from 0x24a on (`xlsplit` ran `xwflips`); the ZFS boot block of a Tribblix disk crashed (`Unhandled Exception 0x0000000000000030`). Generic code, tested on sun4u only |

Each patch header has the details. The numbers and file names match
another tree that carries the same patches, and later patches keep their
numbers from there. The gaps:

- **0002**, the cg3's FCode ROM for screens of any size, is
  [../sun4m/cgthree/cgthree.fs](../sun4m/cgthree/README.md) in LEMU.
- **0012** (the client interface's `boot` service resets the machine, for
  Solaris's reboot) does not work yet: the machine hangs.
- **0018** (sparc32: the SS-5's `SUNW,CS4231` node gets `intr` 9, the level
  of its SBus level) needs a QEMU change that LEMU doesn't have yet (the
  codec's interrupt at SBus level 5). Without it, it would break the sound
  of the SunOS kit. It comes with that change.

## Rebuild

```sh
machines/openbios/build.sh
```

It clones OpenBIOS from the URL of `roms/openbios` in `.gitmodules`, checks
out the commit `roms/openbios` points at (the submodule need not be checked
out), applies the patches and builds in a `debian:13` container with
`gcc-sparc64-linux-gnu`, `fcode-utils` and `xsltproc`, then writes
`pc-bios/openbios-sparc32` and `pc-bios/openbios-sparc64`.

- The sparc32 build takes the patches whose names don't have `-sparc64-`:
  0001 and 0008. 0006, 0007, 0010, 0013, 0014 and 0017 change generic
  code that sparc32 runs too, but were tested on sun4u only, so they are
  named `-sparc64-`.
- The sparc32 build gets `../sun4m/cgthree/cgthree.fs` as
  `drivers/cgthree.fs`, and the script says whether the `QEMU,cgthree.bin`
  it makes is the same as `pc-bios/QEMU,cgthree.bin`. It does not write it;
  `../sun4m/cgthree/build.sh` does.
- `pc-bios/openbios-ppc` is QEMU's image and is not touched.
- Without network in the container, give it a clone:
  `OPENBIOS_IMAGE=builder OPENBIOS_GIT=/w/openbios.git DOCKER_ARGS="-v vol:/w"`,
  where `vol` holds the clone and `builder` has the tools.

The images are not byte for byte reproducible: they hold their build date
(`Welcome to OpenBIOS v1.1 built on ...`), and two sparc64 builds of the
same tree also differ in about 66 bytes of Forth dictionary cells.

When `roms/openbios` moves to a new commit, check that the patches still
apply and run the tests below.

## Testing

In a build with `sparc-softmmu` and `sparc64-softmmu`:

- `tests/functional/sparc/test_openbios.py` (0001: no device on an empty
  SCSI target, the `disk` alias) and
  `tests/functional/sparc64/test_openbios.py` (0003 to 0007, 0009 to 0011,
  0013 with 8 GB, 0015 with 6 GB and 0017, one test each)
  stop at the OpenBIOS prompt on the serial console and check the device
  tree and the Forth state there. They need no downloads and fail with
  QEMU's images: `make check-functional-sparc` and
  `make check-functional-sparc64`.
- `tests/functional/sparc/test_netbsd.py` and
  `tests/functional/sparc64/test_netbsd.py` boot the NetBSD 11.1 install CDs.
  On sun4u that goes through 0010 and 0011 (NetBSD must root on `cd0`),
  and the boots with 4 GB and 8 GB through 0013 and 0014.
- `prom-env-test` and `boot-serial-test` (`make check-qtest-sparc
  check-qtest-sparc64`) start OpenBIOS on every sun4m and sun4u machine.
- No test runs 0008: it needs a guest that calls the firmware's op_enter,
  such as Solaris or SunOS on Stop-A. NetBSD 11.1's installer ignores
  Stop-A.
- No test runs 0016: it needs a client that calls the firmware with
  interrupts enabled (illumos, Solaris). 0017's test runs the FCode
  token at the prompt, not the ZFS boot block.

To try another image, give it with `-bios`.

## What does not work

Reported with QEMU 11.1.3 and these patches; not run with LEMU:

- **Solaris reboot on sun4u.** The client interface's `boot` service prints
  `BOOT` and returns, so the installer's reboot ends with `panic - kernel:
  prom_reboot: reboot call returned!`. Resetting from inside that call hung
  the machine in a trial, so there is no patch for it. Power the machine off
  and start it again.
- **Solaris 7, 8 and 9 on sun4u** panic later in boot (`boot_alloc: pp is
  NULL or free`, `kmem_getpages: pp is NULL or free`); not found why.
  Solaris 2.6 and 2.5.1 stop in the boot block (`open isn't unique.`).
- **OpenBSD's installed kernel on sun4u** stops in OpenBIOS
  (`Unimplemented service set-symbol-lookup`), with or without these
  patches; its `bsd.rd` boots.
- **Solaris kernel debugger words:** `kdbg.fth` stops at `could not find
  debugger-vocabulary-hook`; OBP-internal words OpenBIOS lacks. Only the
  firmware's symbol lookup is lost.

## Known issues

Seen with the images in `pc-bios/`:

- **`decode-unit isn't unique.` and `encode-unit isn't unique.`** at
  sun4u power-on. 0009 defines `decode-unit` and `encode-unit` with
  `feval` in the ebus node, which already has the two methods of the PCI
  bridge, and Forth warns that the names are defined twice in that word
  list. The new definitions are found first, so the ebus children get
  their space,offset names (`su@14,3f8`) as intended; nothing else
  changes. A fix at the source would give the ebus node methods of its
  own instead of redefining the inherited ones. A build without 0011
  prints the same; 0011 needs 0009 (it uses 0009's `encode-unit-2hex`),
  and an image with 0011 but without 0009 stops at power-on.
- **`(enter)` typed at the sun4m prompt, then `go`,** stops QEMU with
  `Trap 0x21 (Instruction Access Error) while interrupts disabled, Error
  state` right after the next ` ok`. `(enter)` is 0008's word for the
  romvec's op_enter, which a client calls with the client in memory; at
  the firmware's own prompt it is not meant to be run (0008 leaves
  Stop-A at the prompt ignored). `go` alone gives `No valid state has
  been set by load or init-program`, as with QEMU's image.
