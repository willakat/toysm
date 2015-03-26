################################################################################
#
# Copyright 2014-2015 William Barsse 
#
################################################################################
#
# This file is part of ToySM.
# 
# ToySM Extensions is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# ToySM Extensions is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public License
# along with ToySM.  If not, see <http://www.gnu.org/licenses/>.
#
################################################################################

import unittest
import time
from threading import Thread
try:
    from queue import Empty
except ImportError:
    from Queue import Empty

from toysm.event_queue import EventQueue
from toysm.fsm import COMPLETION_EVENT, STD_EVENT, INIT_EVENT

class TestEventQueue(unittest.TestCase):
    def test_ordering(self):
        q = EventQueue()
        l_in = [ 5, 4, 3, 2, 1]
        for e in l_in:
            q.put(e)
        l_out = [q.get()[1] for x in range(len(l_in))]
        self.assertEqual(l_in, l_out)

    def test_priorities(self):
        q = EventQueue()
        l_in = [ (STD_EVENT, 1), (STD_EVENT, 2),
                 (INIT_EVENT, 3),
                 (COMPLETION_EVENT, 4), (STD_EVENT, 5),
                 (COMPLETION_EVENT, 6) ]
        for (p, e) in l_in:
            q.put(e, p)
        l_out = [q.get() for x in range(len(l_in))]
        self.assertEqual(l_out, 
                         [e for e in l_in if e[0] == COMPLETION_EVENT] +
                         [e for e in l_in if e[0] == INIT_EVENT] +
                         [e for e in l_in if e[0] == STD_EVENT])

    def test_get_wait_fail(self):
        q = EventQueue()
        delay = .5
        t0 = time.time()
        with self.assertRaises(Empty):
            q.get(delay)
        self.assertTrue(time.time() >= t0 + delay)
        
    def test_get_wait(self):
        q = EventQueue()
        def produce_evt():
            time.sleep(.5)
            q.put('event')
        Thread(target=produce_evt).start()
        self.assertEqual('event', q.get()[1])

    def test_settle(self):
        q = EventQueue()
        q.put('event')
        def consume_evt():
            time.sleep(.5)
            q.get()
            try:
                q.get(.1)
            except Empty:
                pass
        self.assertFalse(q.settle(0))
        Thread(target=consume_evt).start()
        self.assertTrue(q.settle())

    def test_settle_fail(self):
        q = EventQueue()
        q.put('event')
        q.get() # Queue will only settle at the next "get"
        self.assertFalse(q.settle(0))

    def test_settle2(self):
        q = EventQueue()
        self.assertFalse(q.settle(0))
        def consume_evt():
            try:
                q.get(.2)
            except Empty: pass
        Thread(target=consume_evt).start()
        self.assertTrue(q.settle(.1))

if __name__ == '__main__':
    unittest.main()

# vim:expandtab:sw=4:sts=4
