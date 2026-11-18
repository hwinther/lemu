#!/usr/bin/env python3
#
# Functional test that boots the NetBSD/sparc64 install CD on sun4u
# from the built-in IDE controller (cmd646) and checks that the
# installer starts, with 512 MB, 4 GB and 8 GB of RAM
#
# SPDX-License-Identifier: GPL-2.0-or-later

from qemu_test import QemuSystemTest, Asset
from qemu_test import wait_for_console_pattern


class NetBSDSun4u(QemuSystemTest):

    ASSET_CD = Asset(
        ('https://cdn.netbsd.org/pub/NetBSD/NetBSD-11.1/images/'
         'NetBSD-11.1-sparc64.iso'),
        'a782b26be57325c8419fdb02030ea4e686a6ccf097baad2dae0a1a0c39e96f4e')

    def boot_installer(self, ram):
        self.set_machine('sun4u')
        cdrom_path = self.ASSET_CD.fetch()

        # The CD-ROM is the secondary master of the cmd646, where
        # OpenBIOS's cdrom alias points; it boots it with -boot d
        self.vm.set_console()
        self.vm.add_args('-m', ram,
                         '-prom-env', 'input-device=ttya',
                         '-prom-env', 'output-device=ttya',
                         '-drive', f'file={cdrom_path},if=none,id=cd,'
                                   'media=cdrom,readonly=on,format=raw',
                         '-device', 'ide-cd,bus=ide.1,unit=0,drive=cd',
                         '-boot', 'd',
                         '-no-reboot')
        self.vm.launch()

        wait_for_console_pattern(self, 'Welcome to OpenBIOS',
                                 'Unhandled Exception')
        wait_for_console_pattern(self, 'NetBSD 11.1 (', 'panic:')
        # The root file system on the CD is mounted and sysinst's
        # start script asks for the terminal type
        wait_for_console_pattern(self, 'Terminal type (just hit ENTER',
                                 'panic:')

    def test_netbsd_111_installer(self):
        self.boot_installer('512')

    def test_netbsd_111_installer_4g(self):
        # With 4 GB the firmware's free memory ends inside its own virtual
        # range, and NetBSD's first claim failed ("Can't claim two pages of
        # memory.") with the stock OpenBIOS
        self.boot_installer('4096')

    def test_netbsd_111_installer_8g(self):
        # The stock OpenBIOS stopped before its banner with 8 GB
        self.boot_installer('8192')

if __name__ == '__main__':
    QemuSystemTest.main()
