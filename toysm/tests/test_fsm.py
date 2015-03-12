################################################################################
#
# Copyright 2014-2015 William Barsse 
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
# along with Foobar.  If not, see <http://www.gnu.org/licenses/>.
#
################################################################################

import unittest
import time
from collections import defaultdict

import logging

LOG_LEVEL = logging.INFO
#LOG_LEVEL = logging.DEBUG

logging.basicConfig(level=LOG_LEVEL)

from toysm import *

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
                print ('Did not find item (%s, %r)'%(e[0], e[1]))
                cls.show(pos=i, key=key)
            return False

    @classmethod
    def clear(cls):
        cls.evt_log = defaultdict(list)

    @classmethod
    def show(cls, key=None, pos=None):
        evt_log = cls.evt_log[key]
        print ('Event log content%s:' % ('' if key is None else ' for key %r' % key))
        for i, e in enumerate(evt_log):
            print ('%s%i: %s - %r'%('* ' if pos == i else '  ', i, e[0], e[1]))
        

def trace(elt, transitions=True):
    if not elt:
        return None
    if not hasattr(elt, '__iter__'):
        elt = [elt]

    def h(sm, elt, msg=None):
        Trace.add( elt, msg, key=sm.key)

    for e in elt:
        if isinstance(e, State):
            e.add_hook('entry', h, msg='entry')
            e.add_hook('exit', h, msg='exit')
            if transitions and isinstance(e, State):
                trace(tuple(e.transitions), transitions=False)
        else:
            e.add_hook(lambda sm,t,evt: Trace.add( t, 'action', key=sm.key))
    return elt if len(elt) > 1 else elt[0]

class TestFSM(unittest.TestCase):
    def setUp(self):
        Trace.clear()

    def test_lca(self):
        '''
            s1
           /  \
          s2  s3
        '''
        s1 = State()
        s2 = State(parent=s1, initial=True)
        s3 = State(parent=s1)
        sm = StateMachine(s1)
        sm._assign_depth()

        self.assertEqual(([s1],[s1, s3]), sm._lca(s1, s3))
        self.assertEqual(([s2, s1],[s1]), sm._lca(s2, s1))
        self.assertEqual(([s2, s1],[s1, s3]), sm._lca(s2, s3))
        self.assertEqual(([s2],[s2]), sm._lca(s2, s2))

    def test_lca2(self):
        '''
            s1
           /  \
          s2   s5
         / \   / \
        s3 s4 s6 s8 
              /
             s7
        '''
        s1 = State()
        
        s2 = State(parent=s1, initial=True)
        s3 = State(parent=s2, initial=True)
        s4 = State(parent=s2)

        s5 = State(parent=s1)
        s6 = State(parent=s5, initial=True)
        s7 = State(parent=s6, initial=True)
        s8 = State(parent=s5)

        sm = StateMachine(s1)
        sm._assign_depth()

        self.assertEqual(([s3,s2,s1],[s1, s5, s6, s7]), sm._lca(s3, s7))
        self.assertEqual(([s3,s2],[s2, s4]), sm._lca(s3, s4))
        self.assertEqual(([s4,s2,s1],[s1,s5,s8]), sm._lca(s4,s8))


    def test_simple(self):
        s1 = State('s1')
        s2 = State('s2')
        fs = FinalState()
        
        sm = StateMachine(s1, s2, fs)

        s1 >> 'a' >> s2 >> 'b'>> fs

        trace((s1,s2,fs))

        sm.start()
        sm.post('a')
        sm.post('b')
        self.assertTrue(sm.join(1))

        self.assertTrue(Trace.contains(
            [(s1, 'entry'), 
            (s1, 'exit'), 
            (s2, 'entry'), 
            (s2, 'exit'),
            (fs, 'entry')]))

    def test_transition_to_substate(self):
        '''
            s1
           /  \
         s2    s5
        / \     \
      s3   s4    s6
        '''

        s1 = State('s1')
        s2 = State('s2', parent=s1, initial=True)
        s3 = State('s3', parent=s2, initial=True)
        s4 = State('s4', parent=s2)

        s3 >> 'a' >> s4

        s5 = State('s5', parent=s1)
        s6 = State('s6', parent=s5)

        s4 >> 'b' >> s6 >> 'c' >> FinalState(parent=s5)
        s5 >> FinalState(parent=s1)

        sm = StateMachine(s1)

        trace((s1, s2, s3, s4, s5, s6))

        sm.start()
        sm.post('a', 'b', 'c')
        self.assertTrue(sm.join(1))

        self.assertTrue(Trace.contains(
            [ (s2, 'entry'),
              (s3, 'entry'),
              (s3, 'exit'),
              (s4, 'entry'),
              (s4, 'exit'),
              (s2, 'exit'),
              (s5, 'entry'),
              (s6, 'entry'),
              (s6, 'exit'),
              (s5, 'exit'),]))

    def test_transition_from_superstate(self):
        '''
            s1
           /  \
         s2    s5
        / \     \
      s3   s4    s6

        s3->s4
        s2->s6
        '''
        s1 = State('s1')
        s2 = State('s2', parent=s1, initial=True)
        s3 = State('s3', parent=s2, initial=True)
        s4 = State('s4', parent=s2)

        s3 >> 'a' >> s4

        s5 = State('s5', parent=s1)
        s6 = State('s6', parent=s5, initial=True)

        s2 >> 'b' >> s5
        s5 >> 'c' >> FinalState(parent=s1)

        sm = StateMachine(s1)

        trace((s1, s2, s3, s4, s5, s6))

        sm.start()
        sm.post('a', 'b', 'c')
        self.assertTrue(sm.join(1))

        self.assertTrue(Trace.contains(
            [ (s2, 'entry'),
              (s3, 'entry'),
              (s3, 'exit'),
              (s4, 'entry'),
              (s4, 'exit'),
              (s2, 'exit'),
              (s5, 'entry'),
              (s6, 'entry'),
              (s6, 'exit'),
              (s5, 'exit'),]))


    def test_transition_to_pseudostate(self):
        value = [0]

        class MyTransition(Transition):
            def __init__(self, value):
                super(MyTransition, self).__init__()
                self.value = value
            def is_triggered(self, sm, evt):
                return value[0] == self.value
            def do_action(self, sm, evt):
                value[0] += 1

        s1 = State('s1')
        s1 >> EqualsTransition('0', kind=Transition.EXTERNAL)
        s2 = State('s2', parent=s1, initial=True)
        j = Junction(parent=s1)
        s3 = State('s3', parent=s1)
        s4 = State('s4', parent=s1)

        s2 >> 'a' >> j >> MyTransition(0) >> s3
        j >> MyTransition(1) >> s4
        j >> MyTransition(2) >> FinalState(parent=s1)

        trace((s1, s2, s3, s4, j))

        sm = StateMachine(s1)

        sm.start()
        sm.post('a', '0', 'a', '0', 'a')
        self.assertTrue(sm.join(1))

        self.assertTrue(Trace.contains(
            [ (s2, 'entry'),
              (s2, 'exit'),
              (j,  'entry'),
              (j,  'exit'),
              (s3, 'entry'),
              (s3, 'exit'),
              (s1, 'exit'),
              (s1, 'entry'),
              (s2, 'entry'),
              (s2, 'exit'),
              (j,  'entry'),
              (j,  'exit'),
              (s4, 'entry'),
              (s4, 'exit'),
              (s1, 'exit'),
              (s1, 'entry'),
              (s2, 'entry'),
              (s2, 'exit'),
              (j,  'entry'),
              (j,  'exit'),
              ]))


    def test_timeout(self):
        s1 = State('s1')
        s2 = State('s2')
        fs = FinalState()

        s1 >> Timeout(1) >> s2 >> Timeout(1) >> fs
        sm = StateMachine(s1, s2, fs)

        trace((s1, s2, fs))

        sm.start()

        self.assertFalse(Trace.contains([(s2, 'entry')], show_on_fail=False))
        time.sleep(1.1)
        self.assertTrue(Trace.contains([(s2, 'entry')]))
        self.assertFalse(Trace.contains([(fs, 'entry')], show_on_fail=False))

        sm.join(1.1)
        self.assertTrue(Trace.contains([(fs, 'entry')]))


    def test_timeout_cancel(self):
        s1 = State('s1')
        s2 = State('s2')
        fs = FinalState()

        s1 >> Timeout(1) >> s2 >> Timeout(1) >> fs
        s1 >> 'a' >> fs

        sm = StateMachine(s1, s2, fs)

        trace((s1, s2, fs))

        sm.start()
        self.assertFalse(Trace.contains([(s2, 'entry')], show_on_fail=False))
        time.sleep(.5)
        sm.post('a')
        
        self.assertTrue(sm.join(1))
        self.assertFalse(Trace.contains([(s2, 'entry')], show_on_fail=False))
        self.assertTrue(Trace.contains([(s1, 'exit'), (fs, 'entry')]))

    def test_parallel_state(self):
        p = ParallelState()
        s1 = State('s1', parent=p) # first region
        s2 = State('s2', parent=p)

        s11 = State('s11', parent=s1, initial=True)
        s12 = State('s12', parent=s1)
        s11 >> 'a' >> s12 >> 'b' >> FinalState(parent=s1)

        s21 = State('s21', parent=s2, initial=True)
        s21 >> 'a' >> FinalState(parent=s2)

        trace((p, s1, s11, s12, s2, s21))

        sm = StateMachine(p)
        #sm.graph()
        sm.start()

        sm.post('a')
        self.assertTrue(sm.settle(.1))
        self.assertTrue(Trace.contains([
            (p, 'entry'), 
            (s1, 'entry'), 
            (s11, 'entry'), 
            (s11, 'exit'), 
            (s12, 'entry')]))
        self.assertTrue(Trace.contains([
            (p, 'entry'), 
            (s2, 'entry'),
            (s21, 'entry'),
            (s21, 'exit'),
            ]))
        self.assertFalse(Trace.contains([(s1, 'exit')], show_on_fail=False))
        #self.assertTrue(Trace.contains([(s2, 'exit')]))

        sm.post('b')
        self.assertTrue(sm.join(1))
        self.assertTrue(Trace.contains([(s12, 'exit'), (s1, 'exit')]))
        self.assertTrue(Trace.contains([(s1, 'exit')]))
        self.assertTrue(Trace.contains([(s2, 'exit')]))

    def test_history_state(self):
        '''Check basic history state recovery when parent state is entered.
           Also show that transition to 'uninitialized' history state follows
           standard state entry (to initial substate).'''
        s1 = State('s1') 
        s2 = State('s2')
        h = HistoryState(parent=s1)
        s11 = State('s11', parent=s1, initial=True)
        s12 = State('s12', parent=s1)
        s13 = State('s13', parent=s1)
        fs = FinalState()

        s2 >> 'a' >> h
        s11 >> 'b' >> s12 >> 'c' >> s13 >> 'd' >> s11
        s1 >> 'e' >> s2
        s2 >> 'f' >> fs

        trace((s1, s2, s11, s12, s13, fs))
        sm = StateMachine(s2, s1, fs)
        sm.start()

        sm.post('a', 'b', 'c', 'd', 'b', 'e', 'a', 'e', 'f')

        self.assertTrue(sm.join(1))
        
        self.assertTrue(Trace.contains(
            [ (s2, 'entry'),
              (s2, 'exit'),     #a
              (s11, 'entry'),
              (s11, 'exit'),    #b
              (s12, 'entry'),
              (s12, 'exit'),    #c
              (s13, 'entry'),
              (s13, 'exit'),    #d
              (s11, 'entry'),
              (s11, 'exit'),    #b
              (s12, 'entry'),
              (s12, 'exit'),    #e
              (s2, 'entry'),
              (s2, 'exit'),     #a
              (s12, 'entry'),
              (s12, 'exit'),    #e
              (s2, 'entry'),
              (s2, 'exit'),     #f
              (fs, 'entry') ]))

    def test_history_state_w_transition(self):
        '''Check entry transition for an unitialized history state when
           it has a transition defined.
        '''

        s1 = State('s1') 
        s2 = State('s2')
        h = HistoryState(parent=s1)
        s11 = State('s11', parent=s1, initial=True)
        s12 = State('s12', parent=s1)
        fs = FinalState()

        h >> s12
        s2 >> 'a' >> h
        s1 >> 'b' >> s2 >> 'c' >> fs

        trace((s1, s2, s11, s12, fs))
        sm = StateMachine(s2, s1, fs)
        sm.start()

        sm.post('a', 'b', 'c')

        self.assertTrue(sm.join(1))

        self.assertTrue(Trace.contains(
            [ (s2, 'entry'),
              (s2, 'exit'),     #a
              (s12, 'entry'),
              (s12, 'exit'),    #b
              (s2, 'entry'),
              (s2, 'exit'),    #c
              (fs, 'entry') ]))

        self.assertFalse(Trace.contains([ (s11, 'entry') ], show_on_fail=False ))

    def test_internal_transition(self):
        '''Check behavior of INTERNAL transitions.'''

        s1 = State('s1')
        s2 = State('s2', parent=s1, initial=True)
        s3 = State('s3', parent=s1)

        s2 >> 'a' >> s3 >> 'b' >> s2
        t = EqualsTransition('c', kind=Transition.INTERNAL, source=s1)
        s1 >> 'd' >> FinalState(parent=s1)

        trace((s1, s2, s3, t))

        sm = StateMachine(s1)

        sm.start()

        sm.post('c', 'a', 'c', 'b', 'd')

        self.assertTrue(sm.join(1))

        self.assertTrue(Trace.contains(
            [ (s2, 'entry'),
              (t,  'action'),   #c
              (s2, 'exit'),     #a
              (s3, 'entry'),
              (t,  'action'),   #c
              (s3, 'exit'),     #b
              (s2, 'entry'),    
              (s1, 'exit'),]))  #d

    def test_terminate_state(self):
        '''Check behavior of transition to TerminateState.'''

        s1 = State('s1', initial=True)
        s2 = State('s2', parent=s1, initial=True)
        s3 = State('s3')
        fs = FinalState()
        ts = TerminateState(parent=s1)

        s1 >> 'a' >> s3 >> 'b' >> fs
        s2 >> 'c' >> ts

        trace((s1, s2, s3, fs, ts))
        sm = StateMachine(s1, s3, fs)

        sm.start()
        sm.post('c', 'a', 'b')
        self.assertTrue(sm.join(1))

        self.assertTrue(Trace.contains(
            [ (s1, 'entry'),
              (s2, 'entry'),
              (s2, 'exit'),     #c
              (ts, 'entry'), ]))

        self.assertFalse(Trace.contains(
            [ (s1, 'exit'), ], show_on_fail=False))

        self.assertFalse(Trace.contains(
            [ (fs, 'entry'), ], show_on_fail=False))


    def test_builder(self):
        r = State('root', 
                      State('s1') >> 'a' 
                      >> State('s2', State('s21') >> 'b' 
                                         >> State('s22')) 
                      >> 'c' >> FinalState('fs'))
        sm = StateMachine(r)
        self.assertEqual({'s1', 's2', 'fs'}, {s.name for s in sm._cstate.children})
        self.assertEqual({'s21', 's22'}, {s.name for s2 in sm._cstate.children if s2.name == 's2' for s in s2.children})

    def test_builder2(self):
        sm = StateMachine(
            State('s1') >> State('s2') >> FinalState('fs'))
        self.assertEqual({'s1', 's2', 'fs'}, {s.name for s in sm._cstate.children})

    def test_builder3(self):
        s1 = State('s1')
        b1 = State('s2') << s1 << InitialState()

        s3 = State('s3')
        b2 = State('s4') >> s3

        s1 >> s3

        sm = StateMachine(b2 >> b1)

    def test_get_active_states(self):
        s0 = ParallelState('root')
        s11 = State('s11', State('s111') >> 'c' >> State('s112'))
        s12 = State('s12')
        s21 = State('s21', State('s211') >> 'c' >> State('s212'))
        s22 = State('s22')
        s1 = State('s1', 
                       s11 >> 'a' >> s12 >> 'b' >> s11 >> 'd' >> FinalState(),
                       parent=s0) 
        s2 = State('s2',
                       s21 >> 'a' >> s22 >> 'b' >> s21 >> 'd' >> FinalState(),
                       parent=s0) 

        sm = StateMachine(s0)

        sm.start()
        sm.post('a')
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'s12', 's22', 's1', 'root', 's2'},
                         {s.name for (s,_) in s0.get_active_states(sm._sm_state)})
        sm.post('b')
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'s11', 's21', 's111', 's211', 's1', 'root', 's2'},
                         {s.name for (s,_) in s0.get_active_states(sm._sm_state)})
        sm.post('c')
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'s11', 's21', 's112', 's212', 's1', 'root', 's2'},
                         {s.name for (s,_) in s0.get_active_states(sm._sm_state)})
        sm.post('d')
        self.assertTrue(sm.join(1))

    def test_deep_history(self):
        '''Check deep history state directly inside Parallel State.'''
        p0 = ParallelState('p0')
        s1 = State('s1')
        s2 = State('s2')
        p0.add_state(State('', s1 >> '1' >> s2 >> '2' >> s1))
        s3 = State('s3')
        s4 = State('s4')
        p0.add_state(State('', s3 >> '1' >> s4 >> '2' >> s3))
        h0 = DeepHistoryState(parent=p0)

        r0 = State('r0')
        r01 = ParallelState('r01', parent=r0, initial=True)
        s5 = State('s5')
        s6 = State('s6')
        r01.add_state(State('', s5 >> '1' >> s6 >> '2' >> s5))
        s7 = State('s7')
        s8 = State('s8')
        r01.add_state(State('', s7 >> '1' >> s8 >> '2' >> s7))
        r02 = State('r02', parent=r0)
        r01 >> '3' >> r02 >> '4' >> r01
        h1 = DeepHistoryState(parent=r0)

        r0 >> 'p' >> h0 
        p0 >> 'r' >> h1

        j = Junction()
        r0 >> 'e' >> j << 'e' << p0

        sm = StateMachine(p0, r0, j >> FinalState())
        #sm.graph(prg='cat')
        #sm.graph(prg='tee out.dot | xdot -')
        sm.start()
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'p0', 's1', 's3'},
                         {s.name for (s,_) in sm._cstate.get_active_states(sm._sm_state) if s.name})
        sm.post('r')
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'r0', 'r01', 's7', 's5'},
                         {s.name for (s,_) in sm._cstate.get_active_states(sm._sm_state) if s.name})

        sm.post('1')
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'r0', 'r01', 's6', 's8'},
                         {s.name for (s,_) in sm._cstate.get_active_states(sm._sm_state) if s.name})
        
        sm.post('p')
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'p0', 's1', 's3'},
                         {s.name for (s,_) in sm._cstate.get_active_states(sm._sm_state) if s.name})

        sm.post('1')
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'p0', 's2', 's4'},
                         {s.name for (s,_) in sm._cstate.get_active_states(sm._sm_state) if s.name})

        sm.post('r')
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'r0', 'r01', 's6', 's8'},
                         {s.name for (s,_) in sm._cstate.get_active_states(sm._sm_state) if s.name})

        sm.post('3')
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'r0', 'r02'},
                         {s.name for (s,_) in sm._cstate.get_active_states(sm._sm_state) if s.name})

        sm.post('p')
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'p0', 's2', 's4'},
                         {s.name for (s,_) in sm._cstate.get_active_states(sm._sm_state) if s.name})

        sm.post('r')
        self.assertTrue(sm.settle(.1))
        self.assertEqual({'r0', 'r02'},
                         {s.name for (s,_) in sm._cstate.get_active_states(sm._sm_state) if s.name})

        sm.post('e')
        self.assertTrue(sm.join(1))

        self.assertTrue(sm._terminated)

    def test_deep_history2(self):
        '''Test State Entry/Exit when context is restored by a deep history state.'''
        s1 = State('s1')
        s11 = State('s11', parent=s1, initial=True)
        s111 = State('s111', parent=s11, initial=True)
        s112 = State('s112', parent=s11)
        s12 = State('s12', parent=s1)
        s121 = State('s121', parent=s12, initial=True)
        s122 = State('s122', parent=s12)
        s111 >> 'a' >> s112 >> 'b' >> s121 >> 'c' >> s122 >> 'd' >> s111

        s2 = State('s2')
        h = DeepHistoryState(parent=s1)
        s2 >> '1' >> h
        s1 >> '2' >> s2

        fs = FinalState()
        s1 >> 'e' >> fs << 'e' << s2

        trace((s1,s11,s111,s112,s12,s121,s122,s2), transitions=False)

        sm = StateMachine(s1, s2, fs)
        sm.start()

        sm.post('a', '2', '1', 'b', '2', '1', 'e')
        self.assertTrue(sm.join(1))
        self.assertTrue(Trace.contains(
            [ (s1,  'entry'),
              (s11, 'entry'),
              (s111,'entry'),
              (s111,'exit'),    #a
              (s112,'entry'),
              (s112,'exit'),    #2
              (s11, 'exit'),
              (s1,  'exit'),
              (s2,  'entry'),
              (s2,  'exit'),    #1
              (s1,  'entry'),
              (s11, 'entry'),
              (s112,'entry'),
              (s112,'exit'),    #b
              (s11, 'exit'),
              (s12, 'entry'),
              (s121,'entry'),
              (s121,'exit'),    #2
              (s12, 'exit'),
              (s1,  'exit'),
              (s2,  'entry'),
              (s2,  'exit'),    #1
              (s1,  'entry'),
              (s12, 'entry'),
              (s121,'entry'),
              (s121,'exit'),    #e
              (s12, 'exit'),
              (s1,  'exit'),
              ], strict=True))

    def test_basic_transition(self):
        s0 = State('s0')
        s1 = State('s1', parent=s0, initial=True)
        s2 = State('s2', parent=s0)
        def transition_trigger_check(sm, evt):
            Trace.add('my_transition', 'check')
            return True
        def transition_action(sm, evt):
            Trace.add('my_transition', 'action')
        s1 >> Transition(trigger=transition_trigger_check,
                         action=transition_action) >> s2
        s2 >> FinalState(parent=s0)

        sm = StateMachine(s0)
        sm.start()
        sm.post('x')

        sm.settle(.1)
        self.assertTrue(Trace.contains(
            [ ('my_transition',  'check'),
              ('my_transition', 'action'), ]))
        self.assertTrue(sm.join(1))

    def test_guarded_completion(self):
        s0 = State('s0')
        s1 = State('s1', parent=s0, initial=True)
        s2 = State('s2', parent=s0)
        s3 = State('s3', parent=s0)
        def transition_trigger_check1(sm, evt):
            Trace.add('my_transition1', 'check')
            return False
        def transition_trigger_check2(sm, evt):
            Trace.add('my_transition2', 'check')
            return True
        def transition_action1(sm, evt):
            self.assertIsNone(evt)
            Trace.add('my_transition1', 'action')
        def transition_action2(sm, evt):
            self.assertIsNone(evt)
            Trace.add('my_transition2', 'action')
        s1 >> CompletionTransition(trigger=transition_trigger_check1,
                         action=transition_action1) >> s2
        s1 >> CompletionTransition(trigger=transition_trigger_check2,
                         action=transition_action2) >> s3
        s2 >> FinalState(parent=s0) << s3

        sm = StateMachine(s0)
        sm.start()

        sm.settle(.1)
        self.assertTrue(Trace.contains(
            [ ('my_transition2',  'check'),
              ('my_transition2', 'action'), ]))
        self.assertTrue(Trace.contains(
            [ ('my_transition1',  'check'), ]))
        self.assertFalse(Trace.contains(
            [ ('my_transition1',  'action'), ], show_on_fail=False))
        self.assertTrue(sm.join(1))

class TestDemux(unittest.TestCase):
    def setUp(self):
        Trace.clear()

    def test_demux(self):
        '''Demux two simple StateMachines'''
        s1 = State('s1')
        s2 = State('s2')
        fs = FinalState()

        sm = StateMachine(s1 >> 'a' >> s2 >> 'b' >> fs, 
                          demux=lambda event: (event[0], event[1]))

        trace((s1,s2,fs), transitions=False)

        sm.start()
        # At this stage no SMStates have been created

        sm.post((1, 'a'))   # will move instance '1' to s2
        self.assertTrue(sm.settle(.1))
        self.assertTrue(Trace.contains(
            [ (s1, 'entry'), 
              (s2, 'entry'), ], key=1))
        self.assertFalse(Trace.contains(
            [ (s2, 'entry') ], key=2, show_on_fail=False))

        sm.post((1, 'a'))   # ignored by instance '1'
        self.assertTrue(sm.settle(.1))
        self.assertFalse(Trace.contains(
            [ (s2, 'entry') ], key=2, show_on_fail=False))

        sm.post((2, 'a'))   # will create instance '2'
        self.assertTrue(sm.settle(.1))
        self.assertTrue(Trace.contains(
            [ (s1, 'entry'), 
              (s2, 'entry'), ], key=2))

        sm.post((2, 'b'))   # will cause '2' to finish
        self.assertFalse(sm.join(2 * StateMachine.MAX_STOP_WAIT))

        sm.post((1, 'b'))   # will cause '1' to finish
        # The SM will _not_ terminate (it will wait for new events to be posted)
        self.assertFalse(sm.join(2 * StateMachine.MAX_STOP_WAIT))

        sm.post((1, 'a'))   # A new '1' instance is created
        self.assertTrue(sm.settle(.1))
        self.assertTrue(Trace.contains(
            [ (s2, 'entry'), 
              (s2, 'entry'), ], key=1))

        # When sm.stop() is called, it is effective regardless of whether there 
        # are any active SMStates.
        sm.stop()
        self.assertTrue(sm.join(2 * StateMachine.MAX_STOP_WAIT))

    def test_demux_timeout(self):
        '''SM multi-instances have independent timeouts.'''
        s0 = State('s0')
        s1 = State('s1')
        s2 = State('s2')
        fs = FinalState()

        sm = StateMachine(s0 >> 'a' >> s1 >> Timeout(.1) >> s2 >> Timeout(.1) >> fs, 
                          demux=lambda event: (event[0], event[1]))

        trace((s1,s2,fs), transitions=False)

        sm.start()

        sm.post((1, 'a'))   # Starts first SM
        sm.settle(.1)
        time.sleep(.11)

        # instance '1' will have reached s2
        self.assertTrue(Trace.contains(
            [ (s2, 'entry') ], key=1 ))
        self.assertFalse(Trace.contains(
            [ (s2, 'entry'),], key=2, show_on_fail=False ))

        sm.post((2, 'a'))   # Start 2nd SM
        sm.settle(.1)
        time.sleep(.11)

        # instance '1' should be complete, and '2' should have reached s2
        self.assertTrue(Trace.contains(
            [ (s2, 'entry'), (fs, 'entry') ], key=1))
        self.assertTrue(Trace.contains(
            [ (s2, 'entry'),], key=2 ))
        self.assertFalse(Trace.contains(
            [ (fs, 'entry')], key=2, show_on_fail=False ))
        
        time.sleep(.1)
        self.assertTrue(Trace.contains(
            [ (fs, 'entry')], key=2 ))

        sm.stop()
        self.assertTrue(sm.join(2 * StateMachine.MAX_STOP_WAIT))

    def test_history(self):
        '''Test history State with Muxed StateMachine'''
        s1 = State('s1') 
        s2 = State('s2')
        h = HistoryState(parent=s1)
        s11 = State('s11', parent=s1, initial=True)
        s111 = State('s111', parent=s11, initial=True)
        s112 = State('s112', parent=s11)

        s12 = State('s12', parent=s1)
        s13 = State('s13', parent=s1)
        fs = FinalState()

        s2 >> 'a' >> h
        s11 >> 'b' >> s12 >> 'c' >> s13 >> 'd' >> s11
        s1 >> 'e' >> s2
        s2 >> 'f' >> fs
        
        s111 >> 'g' >> s112

        trace((s1, s2, s11, s111, s112, s12, s13, fs))
        sm = StateMachine(s2, s1, fs,
                          demux=lambda event: (event[0], event[1]))
        #sm.graph()
        sm.start()

        sm.post((1,'a'), (2,'a'),
                (1,'b'), (2,'g'),
                (1,'c'), (2,'e'),
                (1,'d'), (2,'a'),
                (1,'b'), (2,'b'),
                (1,'e'), (2,'e'),
                (1,'a'), (2,'f'),
                (1,'e'),
                (1,'f'),)

        sm.settle(.1)

        self.assertTrue(Trace.contains(
            [ (s2, 'entry'),
              (s2, 'exit'),     #a
              (s11, 'entry'),
              (s11, 'exit'),    #b
              (s12, 'entry'),
              (s12, 'exit'),    #c
              (s13, 'entry'),
              (s13, 'exit'),    #d
              (s11, 'entry'),
              (s11, 'exit'),    #b
              (s12, 'entry'),
              (s12, 'exit'),    #e
              (s2, 'entry'),
              (s2, 'exit'),     #a
              (s12, 'entry'),
              (s12, 'exit'),    #e
              (s2, 'entry'),
              (s2, 'exit'),     #f
              (fs, 'entry') ], key=1))

        self.assertTrue(Trace.contains(
            [ (s2, 'entry'),
              (s2, 'exit'),     #a
              (s11, 'entry'),
              (s111, 'entry'),
              (s111, 'exit'),   #g
              (s112, 'entry'),
              (s112, 'exit'),    #e
              (s11,  'exit'),
              (s1,   'exit'),
              (s2,   'entry'),
              (s2,   'exit'),   #a
              (s1,   'entry'),
              (s11,   'entry'),
              (s111,   'entry'),
              (s111,   'exit'), #b
              (s11,   'exit'),
              (s12, 'entry'),
              (s12, 'exit'),    #e
              (s2, 'entry'),
              (s2, 'exit'),     #f
              (fs, 'entry') ], key=2))

    def test_deep_history(self):
        '''Test deep history State with Muxed StateMachine'''
        s1 = State('s1') 
        s2 = State('s2')
        h = DeepHistoryState(parent=s1)
        s11 = State('s11', parent=s1, initial=True)
        s111 = State('s111', parent=s11, initial=True)
        s112 = State('s112', parent=s11)

        s12 = State('s12', parent=s1)
        s13 = State('s13', parent=s1)
        fs = FinalState()

        s2 >> 'a' >> h
        s11 >> 'b' >> s12 >> 'c' >> s13 >> 'd' >> s11
        s1 >> 'e' >> s2
        s2 >> 'f' >> fs
        
        s111 >> 'g' >> s112

        trace((s1, s2, s11, s111, s112, s12, s13, fs))
        sm = StateMachine(s2, s1, fs,
                          demux=lambda event: (event[0], event[1]))
        #sm.graph()
        sm.start()

        sm.post((1,'a'), (2,'a'),
                (1,'b'), (2,'g'),
                (1,'c'), (2,'e'),
                (1,'d'), (2,'a'),
                         (2,'b'),
                (1,'e'), (2,'e'),
                (1,'a'), (2,'f'),
                (1,'e'),
                (1,'f'),)

        sm.settle(.1)
        self.assertTrue(Trace.contains(
            [ (s2, 'entry'),
              (s2, 'exit'),     #a
              (s11, 'entry'),
              (s11, 'exit'),    #b
              (s12, 'entry'),
              (s12, 'exit'),    #c
              (s13, 'entry'),
              (s13, 'exit'),    #d
              (s11, 'entry'),
              (s111, 'entry'),
              (s111, 'exit'),   #e
              (s11, 'exit'),
              (s1, 'exit'),
              (s2, 'entry'),
              (s2, 'exit'),     #a
              (s1, 'entry'),
              (s11, 'entry'),
              (s111, 'entry'),
              (s111, 'exit'),    #e
              (s2, 'entry'),
              (s2, 'exit'),     #f
              (fs, 'entry') ], key=1))

        self.assertTrue(Trace.contains(
            [ (s2, 'entry'),
              (s2, 'exit'),     #a
              (s11, 'entry'),
              (s111, 'entry'),
              (s111, 'exit'),   #g
              (s112, 'entry'),
              (s112, 'exit'),    #e
              (s11,  'exit'),
              (s1,   'exit'),
              (s2,   'entry'),
              (s2,   'exit'),   #a
              (s1,   'entry'),
              (s11,   'entry'),
              (s112,   'entry'),
              (s112,   'exit'), #b
              (s11,   'exit'),
              (s12, 'entry'),
              (s12, 'exit'),    #e
              (s2, 'entry'),
              (s2, 'exit'),     #f
              (fs, 'entry') ], key=2))
        sm.stop()

    def test_terminate(self):
        '''Terminate State independence.'''
        s1 = State('s1') 
        s2 = State('s2') 
        ts = TerminateState()

        trace((s1, s2, ts))
        sm = StateMachine(s1 >> 'a' >> s2 >> 'b' >> ts,
                          demux=lambda event: (event[0], event[1]))
        sm.start()

        sm.post((1, 'a'), (2, 'a'), (1, 'b'))

        sm.settle(.1)

        self.assertTrue(Trace.contains(
            [ (ts, 'entry') ], key=1))
        self.assertFalse(Trace.contains(
            [ (ts, 'exit') ], key=1, show_on_fail=False))
        self.assertTrue(Trace.contains(
            [ (s2, 'entry') ], key=2))
        self.assertFalse(Trace.contains(
            [ (ts, 'entry') ], key=2, show_on_fail=False))
        
        self.assertFalse(sm.join(.1))

        sm.post((2, 'b'))
        sm.settle(.1)
        self.assertTrue(Trace.contains(
            [ (ts, 'entry') ], key=1))
        self.assertFalse(Trace.contains(
            [ (ts, 'exit') ], key=1, show_on_fail=False))

        self.assertFalse(sm.join(2 * StateMachine.MAX_STOP_WAIT))

        sm.stop()
        self.assertTrue(sm.join(2 * StateMachine.MAX_STOP_WAIT))
        
class TestDoActivity(unittest.TestCase):
    def setUp(self):
        Trace.clear()

    def test_simple(self):
        '''Do activity triggered when state is entered.'''
        def do_trace(sm, state, _):
            Trace.add(state, 'do')
        s1 = State('s1', do=do_trace)

        trace((s1,))
        sm = StateMachine(s1 >> FinalState())

        sm.start()
        sm.join(.1)
        self.assertTrue(Trace.contains([(s1, 'do')]))

        # 'do' should only have been called once
        self.assertFalse(Trace.contains([(s1, 'do')]*2, show_on_fail=False))

    # test wait on exit_required event
    def test_wait_on_exit_required(self):
        '''Exit required event can be used to "sleep" during the
           do-action without blocking the StateMachine'''
        def do_trace(sm, state, ex_req):
            while not ex_req.is_set():
                Trace.add(state, 'do')
                ex_req.wait(1)
            Trace.add(state, 'do-exit')
        s1 = State('s1', do=do_trace)
        trace((s1,))
        sm = StateMachine(s1 >> 'a' >> FinalState())
        sm.start()
        sm.settle(.1)
        self.assertTrue(Trace.contains([(s1, 'entry'), (s1, 'do')]))
        self.assertFalse(Trace.contains([(s1, 'do-exit')], show_on_fail=False))

        # Post 'a' to force exit of the state
        sm.post('a')
        sm.settle(.1)   # here we are settling for a duration shorter than the 
                        # the amount of time the do-activity is "sleeping".
        self.assertTrue(Trace.contains([(s1, 'do-exit'), (s1, 'exit')]))
        sm.join(.1)

    # test return True (for looping)
    def test_loop(self):
        '''Test looping behavior when do-activity fn returns True'''
        def do_trace(sm, state, _):
            Trace.add(state, 'do')
            time.sleep(.01)
            return True
        s1 = State('s1', do=do_trace)
        trace((s1,))
        sm = StateMachine(s1 >> 'a' >> FinalState())
        sm.start()
        time.sleep(.1)
        self.assertTrue(Trace.contains([(s1, 'entry')] + [(s1, 'do')]*2))

        sm.post('a')
        sm.settle(.1)
        self.assertTrue(Trace.contains([(s1, 'exit')]))
        self.assertFalse(Trace.contains([(s1, 'exit'), (s1, 'do')], show_on_fail=False))
        sm.join(.1)

    # State only exits when the thread has been stopped.
    def test_exit_after_activity_stopped(self):
        '''State only exits once the thread running the do-activity has
           stopped.'''
        import time
        delay = .5
        def do_trace(sm, state, _):
            time.sleep(delay)
            Trace.add(state, 'activity_done')

        s1 = State('s1', do=do_trace)
        trace((s1,))
        sm = StateMachine(s1 >> 'a' >> FinalState())
        sm.post('a')
        sm.start()
        self.assertFalse(Trace.contains([(s1, 'activity_done')], show_on_fail=False))
        self.assertFalse(Trace.contains([(s1, 'exit')], show_on_fail=False))
        sm.join(2 * delay)
        self.assertTrue(Trace.contains([(s1, 'activity_done'), (s1, 'exit')]))

    # test completion only after do-activity finishes
    def test_completion_do_then_children(self):
        '''State exits once the activity is complete and children exit.'''
        delay = .5
        def do_trace(sm, state, _):
            Trace.add(state, 'do')
        s11 = State('s11')
        s1 = State('s1', s11 >> Timeout(delay) >> FinalState(), do=do_trace)
        trace((s1, s11))
        sm = StateMachine(s1 >> FinalState())
        sm.start()
        sm.settle(.1)
        self.assertTrue(Trace.contains([(s1, 'do')]))
        self.assertFalse(Trace.contains([(s1, 'exit')], show_on_fail=False))
        sm.join(2*delay)
        self.assertTrue(Trace.contains([(s1, 'do'), (s11, 'exit'), (s1, 'exit')]))

    def test_completion_children_then_do(self):
        '''State exits once the activity is complete and children exit.'''
        import time
        delay = .5
        def do_trace(sm, state, _):
            time.sleep(delay)
            Trace.add(state, 'done do-activity')
        s11 = State('s11')
        s1 = State('s1', s11 >> FinalState(), do=do_trace)
        trace((s1, s11))
        sm = StateMachine(s1 >> FinalState())
        sm.start()
        sm.settle(.1)
        self.assertFalse(Trace.contains([(s1, 'done do-activity')], show_on_fail=False))
        self.assertTrue(Trace.contains([(s11, 'exit')]))
        sm.join(2*delay)
        self.assertTrue(Trace.contains([(s11, 'exit'), (s1, 'done do-activity'), (s1, 'exit')]))

    def test_pstate_completion_do_then_children(self):
        '''Test parallel state completion if do activity completes before
           the children regions.'''
        def do_trace(sm, state, _):
            Trace.add(state, 'do-activity')
        p1 = ParallelState('p1', do=do_trace)
        s11 = State('s11')
        s1 = State('s1', s11 >> FinalState(), parent=p1)
        s21 = State('s21')
        s2 = State('s2', s21 >> 'a' >> FinalState(), parent=p1)
        fs = FinalState()
        trace((p1, s1, s11, s2, s21, fs))
        sm = StateMachine(p1 >> fs)
        sm.start()
        sm.settle(.1)
        self.assertFalse(Trace.contains([(fs, 'entry')], show_on_fail=False))
        self.assertTrue(Trace.contains([(p1, 'do-activity')]))
        sm.post('a')
        sm.settle(.1)
        self.assertTrue(Trace.contains([(fs, 'entry')]))
        sm.join(.1)

    def test_pstate_completion_children_then_do(self):
        '''Test parallel state completion if children finish before
           do activity.'''
        delay = .5
        def do_trace(sm, state, _):
            time.sleep(delay)
            Trace.add(state, 'done do-activity')
        p1 = ParallelState('p1', do=do_trace)
        s11 = State('s11')
        s1 = State('s1', s11 >> FinalState(), parent=p1)
        s21 = State('s21')
        s2 = State('s2', s21 >> FinalState(), parent=p1)
        fs = FinalState()
        trace((p1, s1, s11, s2, s21, fs))
        sm = StateMachine(p1 >> fs)
        sm.start()
        sm.settle(.1)
        self.assertTrue(Trace.contains([(s1, 'entry'), (s11, 'exit')]))
        self.assertTrue(Trace.contains([(s2, 'entry'), (s21, 'exit')]))
        self.assertFalse(Trace.contains([(fs, 'enter')], show_on_fail=False))
        self.assertFalse(Trace.contains([(p1, 'done do-activity')], show_on_fail=False))
        sm.join(delay + .1)
        self.assertTrue(Trace.contains([(fs, 'entry')]))
        self.assertTrue(Trace.contains([(p1, 'done do-activity')]))

if __name__ == '__main__':
    unittest.main()

# vim:expandtab:sw=4:sts=4
