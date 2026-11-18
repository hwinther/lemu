# sun4u (Ultra 5/10 class)

**TL;DR** `-M sun4u` with LEMU's OpenBIOS. LEMU fixes the interrupt status
of the built-in IDE controller and the firmware's device tree, which
Solaris 10 needs. NetBSD boots from its CD as on QEMU.

## IDE interrupt status (cmd646)

- The cmd646 latches a drive's interrupt in its status bits (`MRDMODE`,
  mirrored in `CFR` and `ARTTIM23`) until the driver writes 1 to clear
  them. QEMU cleared them as soon as the drive dropped its interrupt line,
  which it does when the driver reads the drive's status.
- Solaris 10's `ata` driver reads the status first and then looks at the
  bits, so it printed `WARNING: Interrupt not seen after set_features` for
  every IDE device.
- LEMU keeps the bits until they are cleared (`hw/ide/cmd646.c`). The PCI
  interrupt line still follows the drive: driving it from the bits instead
  hangs Linux and OpenBSD, which never clear them.

## Testing

- `tests/qtest/sun4u-cmd646-test.c` checks the bits and the line through
  the sabre. In a build with `sparc64-softmmu`:
  `QTEST_QEMU_BINARY=./qemu-system-sparc64 tests/qtest/sun4u-cmd646-test`
- `tests/functional/sparc64/test_netbsd.py` boots the NetBSD 11.1 CD from
  `ide-cd,bus=ide.1,unit=0` to the installer, and
  `tests/functional/sparc64/test_openbios.py` checks the OpenBIOS changes
  at the firmware's prompt: `make check-functional-sparc64`.

## OpenBIOS

`pc-bios/openbios-sparc64` is built with LEMU's patches
([../openbios](../openbios/README.md)). What changes for a sun4u guest:

- **Node names like OBP's.** The sabre is `/pci@1f,0` (was `pci@1fe,0`)
  and the ebus children `su@14,3f8`, `8042@14,60`, `eeprom@14,2000`,
  `power@14,7240` (were `su@0`, `8042@0`, ...).
- **IDE drives under the controller,** addressed target,lun with target =
  2 x channel + unit: `ide@3/disk@0,0` for `ide.0` unit 0 and
  `ide@3/cdrom@2,0` for `ide.1` unit 0 (were `ide@3/ide@0/disk@0` and
  `ide@3/ide@1/cdrom@0`). The aliases `disk` and `cdrom` point there. A
  script or `boot-device` with the old paths must change.
- **For Solaris:** the virtual memory list covers the whole address space,
  the CPU node gives the I-cache size (16 KB, 32-byte lines), no package is
  active at the prompt, and two Forth fixes. Reported without them, with
  QEMU 11.1: Solaris 8 to 10 panic early in boot (`no nucleus hblk8 to
  allocate`, `BOP_ALLOC failed` or `VAC too big!`).
- **RAM above 3 GB.** With QEMU's OpenBIOS, NetBSD panicked with 4 GB
  before its kernel banner (its first memory claim failed), and the
  firmware itself stopped before its banner with 6 GB (`Unhandled
  Exception`) and 8 GB (`out of malloc memory (28)!`). Now the NetBSD
  11.1 CD boots to its installer with 4 GB and with 8 GB, and the firmware
  gives 64-bit clients whole physical addresses above 4 GB.
- **For illumos (Tribblix):** the client interface runs with interrupts
  disabled, and the 64-bit FCode words from `xa+` on run the right word
  (the ZFS boot block uses `xlsplit`). Reported with QEMU 11.1; LEMU's
  tests have no illumos medium.
- At power-on the firmware prints `decode-unit isn't unique.` and
  `encode-unit isn't unique.`: Forth notes that a word got a second
  definition. LEMU's tests pass with them.

## Solaris

Reported with QEMU 11.1.3, the cmd646 fix above and OpenBIOS patches 0003
to 0011: Solaris 10 1/13 boots from its DVD on `ide.1` to the installer on
the serial console, installs to a disk on `ide.0` and boots from it. Not run
with LEMU: there is no free Solaris medium. What does not work yet is in
[../openbios](../openbios/README.md#what-does-not-work), first of all the
reboot: power the machine off instead.
