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
# along with Foobar.  If not, see <http://www.gnu.org/licenses/>.
#
################################################################################

from threading import Condition, Lock
from heapq import heappush, heappop

try:
    # python3
    import queue
except ImportError:
    # python2
    # pylint: disable=import-error
    import Queue as queue

class EventQueue:
    '''Queue to store events posted to a StateMachine.'''

    def __init__(self, dflt_prio=None):
        self._queue = []
        self._counter = 0
        self._lock = lock = Lock()
        self._evt_avail = Condition(lock)
        self._settled = Condition(lock)
        self._consumers = 0
        self.dflt_prio = dflt_prio

    def put(self, evt_data, prio=None):
        '''Adds the Event to the queue.'''
        if prio is None:
            prio = self.dflt_prio
        with self._lock:
            if not self._queue:
                # Notify any thread waiting for a new event
                # as soon as the lock is released
                self._evt_avail.notify()
            # _counter is used to ensure that Events that share
            # the same priority are queued by order of arrival.
            heappush(self._queue, (prio, self._counter, evt_data))
            self._counter += 1

    def get(self, timeout=None):
        '''Returns the next (prio, evt_data) from the queue.'''
        with self._lock:
            if not self._queue:
                # Queue is empty, the StateMachine is settled
                self._counter = 0
                self._consumers += 1
                self._settled.notify()
                self._evt_avail.wait(timeout)
                self._consumers -= 1
                if not self._queue:
                    # Timed out waiting for a new event
                    raise queue.Empty
            prio, _, evt_data = heappop(self._queue)
            return prio, evt_data

    def settle(self, timeout=None):
        '''Returns once the queue is empty and a consumer is waiting for the
           next event, or when timeout has expired.
           returns True if the queue is empty.'''
        with self._lock:
            if self._queue:
                self._settled.wait(timeout)
            return not bool(self._queue) and self._consumers > 0

# vim:expandtab:sw=4:sts=4
