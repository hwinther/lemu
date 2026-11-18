#!/usr/bin/env python3
#
# Functional test that stops OpenBIOS at its prompt on sun4u and checks
# the device tree and Forth state that Solaris needs from it
#
# SPDX-License-Identifier: GPL-2.0-or-later

import re

from qemu_test import QemuSystemTest
from qemu_test import exec_command_and_wait_for_pattern
from qemu_test import wait_for_console_pattern


IDE = '/pci@1f,0/pci@1,1/ide@3'


class OpenBIOSSun4u(QemuSystemTest):

    timeout = 60

    def boot_to_prompt(self, ram='512'):
        self.set_machine('sun4u')
        # Disks on the primary master and slave and an empty CD-ROM drive
        # on the secondary master: OBP calls them disk@0,0, disk@1,0 and
        # cdrom@2,0
        self.vm.set_console()
        self.vm.add_args('-m', ram,
                         '-prom-env', 'auto-boot?=false',
                         '-prom-env', 'input-device=ttya',
                         '-prom-env', 'output-device=ttya',
                         '-drive', 'driver=null-co,size=64M,read-zeroes=on,'
                                   'if=none,id=hd',
                         '-device', 'ide-hd,bus=ide.0,unit=0,drive=hd',
                         '-drive', 'driver=null-co,size=64M,read-zeroes=on,'
                                   'if=none,id=hd1',
                         '-device', 'ide-hd,bus=ide.0,unit=1,drive=hd1',
                         '-drive', 'if=none,id=cd,media=cdrom',
                         '-device', 'ide-cd,bus=ide.1,unit=0,drive=cd')
        self.vm.launch()
        wait_for_console_pattern(self, "Type 'help' for detailed information",
                                 'Unhandled Exception')
        wait_for_console_pattern(self, '0 > ')

    def forth(self, cmd):
        # OpenBIOS ends the output of each line with " ok"
        out = exec_command_and_wait_for_pattern(self, cmd, ' ok',
                                                'Unhandled Exception')
        return out.decode(errors='replace').replace('\r', '')

    def test_obp_node_names(self):
        # The sabre is named by its UPA port id and the ebus children by
        # space,offset, as on OBP; Solaris looks the console up by them
        self.boot_to_prompt()
        devs = self.forth('show-devs')
        self.assertIn('/pci@1f,0 (pci)', devs)
        self.assertIn('/pci@1f,0/pci@1,1/ebus@1/su@14,3f8 (serial)', devs)
        self.assertNotIn('pci@1fe,0', devs)

    def test_ide_drives_under_controller(self):
        # Drives directly under the controller as target,lun with
        # target = 2 * channel + unit, and "compatible" for Solaris
        self.boot_to_prompt()
        devs = self.forth('show-devs')
        self.assertIn(IDE + '/disk@0,0 (block)', devs)
        self.assertIn(IDE + '/cdrom@2,0 (block)', devs)
        self.assertNotIn(IDE + '/ide@', devs)
        props = self.forth(f'dev {IDE}/cdrom@2,0 .properties device-end')
        self.assertRegex(props, r'compatible\s+"ide-cdrom"')
        props = self.forth(f'dev {IDE}/disk@0,0 .properties device-end')
        self.assertRegex(props, r'compatible\s+"ide-disk"')

    def test_interposed_my_unit(self):
        # open-dev on a disk gives the instance of the disk-label package
        # interposed on it. Its my-unit is the disk's unit (target 1,
        # lun 0), not 0 0: NetBSD's ofwboot reads the boot device's
        # target there
        self.boot_to_prompt()
        self.forth(f'" {IDE}/disk@1,0" open-dev value ih')
        out = self.forth('" /packages/disk-label" find-package drop '
                         'ih ihandle>phandle = .')
        self.assertRegex(out, r'= \. -1 +ok')
        out = self.forth('ih to my-self my-unit . . 0 to my-self')
        self.assertRegex(out, r'to my-self 1 0 +ok')

    def test_cpu_icache_properties(self):
        # The UltraSPARC IIi has a 16 KB I-cache with 32-byte lines; the
        # stock firmware gave the E-cache values there
        self.boot_to_prompt()
        props = self.forth('dev /SUNW,UltraSPARC-IIi .properties device-end')
        size = re.search(r'^icache-size\s+([0-9a-f]+)', props, re.M)
        line = re.search(r'^icache-line-size\s+([0-9a-f]+)', props, re.M)
        self.assertIsNotNone(size, props)
        self.assertIsNotNone(line, props)
        self.assertEqual(int(size.group(1), 16), 16 * 1024)
        self.assertEqual(int(line.group(1), 16), 32)

    def test_virtual_memory_available(self):
        # "available" covers the whole 64-bit space like OBP's, except the
        # firmware's range up to 4 GB and the UltraSPARC I/II VA hole
        self.boot_to_prompt()
        props = self.forth('dev /virtual-memory .properties device-end')
        m = re.search(r'^available((?:\s+[0-9a-f]{8})+)', props, re.M)
        self.assertIsNotNone(m, props)
        cells = [int(c, 16) for c in m.group(1).split()]
        self.assertEqual(len(cells) % 4, 0, props)
        ranges = []
        for i in range(0, len(cells), 4):
            start = cells[i] << 32 | cells[i + 1]
            size = cells[i + 2] << 32 | cells[i + 3]
            ranges.append((start, start + size))
        self.assertTrue(any(start >= 1 << 32 for start, end in ranges),
                        f'nothing available above 4 GB: {ranges}')
        for start, end in ranges:
            self.assertFalse(start < 1 << 32 and end > 0xff000000,
                             f'firmware range listed: {start:x}-{end:x}')
            self.assertFalse(start < 0xfffff80000000000 and
                             end > 0x0000080000000000,
                             f'VA hole listed: {start:x}-{end:x}')

    def test_no_active_package(self):
        # No active package at the prompt, as on OBP. The stock firmware
        # left /chosen active, and Solaris's Forth words went into it
        self.boot_to_prompt()
        out = self.forth('active-package .')
        self.assertRegex(out, r'active-package \. 0 +ok')

    def test_forth_vocabulary(self):
        # "forth" is the vocabulary word, not a constant 11 that leaves a
        # cell on the stack
        self.boot_to_prompt()
        out = self.forth('only forth depth .')
        self.assertRegex(out, r'depth \. 0 +ok')

    def test_fcode_instance(self):
        # An FCode program that uses "instance" before b(value) leaves the
        # flag clear for the next Forth defining word. The program is
        #   fcode-version2 instance 0 value x fcode-end
        # as toke makes it: f1 08 02 da 00 00 00 0f c0 a5 b5 08 00 b8 00
        self.boot_to_prompt()
        self.forth('10 alloc-mem value fc')
        self.forth('f10802da fc l! f fc 4 + l!')
        self.forth('c0a5b508 fc 8 + l! b80000 fc c + l!')
        self.forth('fc 1 byte-load')
        out = self.forth('#instance @ .')
        self.assertRegex(out, r'@ \. 0 +ok')


    def test_8g_ram(self):
        # The firmware's heap sits at the top of RAM. With more than 4 GB
        # its physical address lost its upper bits, and the stock firmware
        # stopped before its banner
        self.boot_to_prompt('8192')
        props = self.forth('dev /memory .properties device-end')
        self.assertRegex(props, r'reg\s+00000000 00000000\s+00000002 00000000')

    def test_translate_whole_phys(self):
        # translate gives phys.lo phys.hi mode true; phys.lo holds the
        # whole address, as 64-bit clients read phys.lo alone. With 6 GB
        # the firmware's heap is above 4 GB
        self.boot_to_prompt('6144')
        self.forth('" mmu" " /chosen" find-package drop get-package-property')
        self.forth('drop decode-int nip nip value mmu')
        out = self.forth('here " translate" mmu $call-method .s')
        m = re.search(r'<4> ([0-9a-f]+) ([0-9a-f]+) [0-9a-f]+ -1', out)
        self.assertIsNotNone(m, out)
        lo, hi = int(m.group(1), 16), int(m.group(2), 16)
        self.assertGreaterEqual(lo, 1 << 32, out)
        self.assertEqual(lo >> 32, hi, out)

    def test_fcode_64bit_tokens(self):
        # xlsplit (token 0x251) of the 64-bit FCode extension. The stock
        # table ran the word two places further down for the tokens from
        # 0x24a on. The program is
        #   fcode-version2
        #     h# 1abcdef0 h# 12345678 lxjoin xlsplit
        #     " r1 l! r2 l!" evaluate
        #   fcode-end
        # as toke makes it. byte-load drops what the program leaves on the
        # stack, so it stores the two halves itself
        self.boot_to_prompt()
        self.forth('40 alloc-mem value fc')
        self.forth('variable r1 variable r2')
        self.forth('f108081b fc l! 25 fc 4 + l! 101abcde fc 8 + l!')
        self.forth('f0101234 fc c + l! 56780243 fc 10 + l!')
        self.forth('0251120b fc 14 + l! 7231206c fc 18 + l!')
        self.forth('21207232 fc 1c + l! 206c21cd fc 20 + l! 0 fc 24 + l!')
        self.forth('fc 1 byte-load')
        out = self.forth('r1 l@ . r2 l@ .')
        self.assertRegex(out, r'l@ \. 12345678 1abcdef0 +ok')


if __name__ == '__main__':
    QemuSystemTest.main()
