#!/usr/bin/env python3
#
# Functional test that stops OpenBIOS at its prompt on a SPARCstation 5
# and checks the SCSI devices and aliases it found and the codec's
# interrupt properties
#
# SPDX-License-Identifier: GPL-2.0-or-later

from qemu_test import QemuSystemTest
from qemu_test import exec_command_and_wait_for_pattern
from qemu_test import wait_for_console_pattern


class OpenBIOSSun4m(QemuSystemTest):

    timeout = 60

    def boot_to_prompt(self, *args):
        self.set_machine('SS-5')
        self.vm.set_console()
        self.vm.add_args('-m', '256',
                         '-prom-env', 'auto-boot?=false',
                         '-prom-env', 'input-device=ttya',
                         '-prom-env', 'output-device=ttya',
                         *args)
        self.vm.launch()
        wait_for_console_pattern(self, "Type 'help' for detailed information")
        wait_for_console_pattern(self, '0 > ')

    def forth(self, cmd):
        # OpenBIOS ends the output of each line with " ok"
        out = exec_command_and_wait_for_pattern(self, cmd, ' ok')
        return out.decode(errors='replace').replace('\r', '')

    def test_empty_scsi_targets(self):
        # A disk on target 3, where the SPARCstation 5 has it, and nothing
        # on the other targets. The stock firmware took every empty target
        # for a device of unknown type, and the disk got only disk3, so
        # the default boot-device "disk:a disk" found no disk
        self.boot_to_prompt('-drive', 'driver=null-co,size=64M,'
                                      'read-zeroes=on,if=none,id=hd',
                            '-device', 'scsi-hd,scsi-id=3,drive=hd')
        devs = self.forth('show-devs')
        self.assertIn('/esp@5,8800000/sd@3,0 (block)', devs)
        for target in (0, 1, 2, 4, 5, 6, 7):
            self.assertNotIn(f'/sd@{target},0 ', devs)
        aliases = self.forth('dev /aliases .properties device-end')
        self.assertNotIn('UNKNOWN', aliases)
        self.assertRegex(aliases, r'(?m)^disk +"[^"]*/sd@3,0"$')

    def test_cs4231_intr(self):
        # The SS-5's codec is at SBus level 5 ("interrupts" 5), which is
        # processor level 9 on sun4m: "intr" must say 9, as on the real
        # machine's PROM. SunOS 4 takes "intr", Solaris "interrupts"
        self.boot_to_prompt()
        props = self.forth('dev /iommu/sbus/SUNW,CS4231 .properties '
                           'device-end')
        self.assertRegex(props, r'(?m)^interrupts +5 *$')
        self.assertRegex(props, r'(?m)^intr +-- 8 : 00 00 00 09 00 00 00 00')


if __name__ == '__main__':
    QemuSystemTest.main()
