################################################################################
#
# Copyright 2014 William Barsse 
#
################################################################################
#
# This file is part of ToySM Extensions.
# 
# ToySM Extensions is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# ToySM Extensions is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Foobar.  If not, see <http://www.gnu.org/licenses/>.
#
################################################################################

import sys
import unittest
import logging

LOG_LEVEL = logging.INFO
#LOG_LEVEL = logging.DEBUG

logging.basicConfig(level=LOG_LEVEL)

SCAPY_COMPAT = sys.version_info.major < 3

if SCAPY_COMPAT:
    from scapy.all import *
    from toysm.ext.scapy import *

@unittest.skipIf(not SCAPY_COMPAT,
                 'Scapy is Python2 only, for now at least')
class TestPacketTransition(unittest.TestCase):
    def test_match_packet_class_tmpl(self):
        self.assertTrue(
            match_packet(IP, IP(str(IP()))))

    def test_match_packet_field_match(self):
        self.assertTrue(
            match_packet(IP(), IP(str(IP()))))
        self.assertFalse(
            match_packet(IP(src='1.2.3.4'), 
                         IP(str(IP(src='2.3.4.5')))))
        self.assertFalse(
            match_packet(IP(src='1.2.3.4'), 
                         IP(str(IP(dst='1.2.3.4')))))

    def test_match_packet_find_layer(self):
        self.assertTrue(
            match_packet(IP(src='1.2.3.4'), 
                         Ether(str(Ether()/IP(src='1.2.3.4')/UDP()))))

    def test_match_packet_skip_layer(self):
        self.assertTrue(
            match_packet(IP(src='1.2.3.4')/DNS(id=1), 
                         Ether(str(Ether()/IP(src='1.2.3.4')/UDP()/DNS(id=1)))))
        self.assertFalse(
            match_packet(IP(src='4.5.6.7')/DNS(id=1), 
                         Ether(str(Ether()/IP(src='1.2.3.4')/UDP()/DNS(id=1)))))
        self.assertFalse(
            match_packet(IP(src='1.2.3.4')/DNS(id=2), 
                         Ether(str(Ether()/IP(src='1.2.3.4')/UDP()/DNS(id=1)))))

    def test_match_forbid_pld(self):
        self.assertTrue(
            match_packet(IP(src='1.2.3.4')/ForbidPayload(), 
                         Ether(str(Ether()/IP(src='1.2.3.4')))))
        self.assertFalse(
            match_packet(IP(src='1.2.3.4')/ForbidPayload(), 
                         Ether(str(Ether()/IP(src='1.2.3.4')/UDP()))))

    def test_match_missing_pld(self):
        self.assertFalse(
            match_packet(IP()/UDP()/DNS(),
                         Ether()/IP()))

    def test_match_list(self):
        self.assertTrue(
            match_packet(IP(src='1.2.3.4/30'), 
                         Ether(str(Ether()/IP(src='1.2.3.4')))))
        self.assertTrue(
            match_packet(IP(src='1.2.3.4/30'), 
                         Ether(str(Ether()/IP(src='1.2.3.5')))))

# vim:expandtab:sw=4:sts=4
