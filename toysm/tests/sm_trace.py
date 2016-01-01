################################################################################
#
# Copyright 2015 William Barsse
#
################################################################################
#
# This file is part of ToySM.
#
# ToySM is free software: you can redistribute it and/or modify
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

"""
This module contains a helper to trace StateMachine executions in order
to simplify writing (some) unit tests.
"""

from collections import defaultdict

from toysm import State


class Trace:
    evt_log = defaultdict(list)

    @classmethod
    def add(cls, elt, kind=None, key=None):
        evt_log = cls.evt_log[key]
        evt_log.append((elt, kind))

    @classmethod
    def contains(cls, seq, strict=False, show_on_fail=True, key=None):
        evt_log = cls.evt_log[key]
        try:
            i = 0
            j = i + 1 if strict else len(evt_log)
            for e in seq:
                i = evt_log.index(e, i, j) + 1
                if strict:
                    j = i + 1
            return True
        except ValueError:
            if show_on_fail:
                print ('Did not find item (%s, %r)' % (e[0], e[1]))
                cls.show(pos=i, key=key)
            return False

    @classmethod
    def clear(cls):
        cls.evt_log = defaultdict(list)

    @classmethod
    def show(cls, key=None, pos=None):
        evt_log = cls.evt_log[key]
        print ('Event log content%s:' %
               ('' if key is None else ' for key %r' % key))
        for i, e in enumerate(evt_log):
            print ('%s%i: %s - %r' %
                   ('* ' if pos == i else '  ', i, e[0], e[1]))


def trace(elt, transitions=True):
    if not elt:
        return None
    if not hasattr(elt, '__iter__'):
        elt = [elt]

    def h(sm, elt, msg=None):
        #print "trace hook"
        Trace.add(elt, msg, key=sm.key)

    for e in elt:
        if isinstance(e, State):
            e.add_hook('entry', h, msg='entry')
            e.add_hook('exit', h, msg='exit')
            if transitions and isinstance(e, State):
                trace(tuple(e.transitions), transitions=False)
        else:
            e.add_hook(lambda sm, t, evt: Trace.add(t, 'action', key=sm.key))
    return elt if len(elt) > 1 else elt[0]
