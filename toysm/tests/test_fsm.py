import unittest
import time

import logging

LOG_LEVEL = logging.INFO
#LOG_LEVEL = logging.DEBUG

logging.basicConfig(level=LOG_LEVEL)

from toysm import *
import toysm as fsm

class Trace:
    evt_log = []

    @classmethod
    def add(cls, elt, kind=None):
       cls.evt_log.append((elt, kind))

    @classmethod
    def contains(cls, seq, strict=False, show_on_fail=True):
        try:
            i = 0
            j = i + 1 if strict else len(cls.evt_log)
            for e in seq:
                i = cls.evt_log.index(e, i, j) + 1
                if strict:
                    j = i + 1
            return True
        except ValueError:
            if show_on_fail:
                print ('Did not find item (%s, %r)'%(e[0], e[1]))
                cls.show()
            return False

    @classmethod
    def clear(cls):
        #cls.evt_log.clear()
        cls.evt_log = []

    @classmethod
    def show(cls):
        print ('Event log content:')
        for i, e in enumerate(cls.evt_log):
            print ('%i: %s - %r'%(i, e[0], e[1]))
        

def trace(elt, transitions=True):
    if not elt:
        return None
    if not hasattr(elt, '__iter__'):
        elt = [elt]

    def h(sm, elt, msg=None):
        Trace.add(elt, msg)

    for e in elt:
        if isinstance(e, fsm.State):
            e.add_hook('entry', h, msg='entry')
            e.add_hook('exit', h, msg='exit')
            if transitions and isinstance(e, fsm.State):
                trace(tuple(e.transitions), transitions=False)
        else:
            e.add_hook(lambda sm,t,evt: Trace.add(t, 'action'))
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
        s1 = fsm.State()
        s2 = fsm.State(parent=s1, initial=True)
        s3 = fsm.State(parent=s1)
        sm = fsm.StateMachine(s1)
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
        s1 = fsm.State()
        
        s2 = fsm.State(parent=s1, initial=True)
        s3 = fsm.State(parent=s2, initial=True)
        s4 = fsm.State(parent=s2)

        s5 = fsm.State(parent=s1)
        s6 = fsm.State(parent=s5, initial=True)
        s7 = fsm.State(parent=s6, initial=True)
        s8 = fsm.State(parent=s5)

        sm = fsm.StateMachine(s1)
        sm._assign_depth()

        self.assertEqual(([s3,s2,s1],[s1, s5, s6, s7]), sm._lca(s3, s7))
        self.assertEqual(([s3,s2],[s2, s4]), sm._lca(s3, s4))
        self.assertEqual(([s4,s2,s1],[s1,s5,s8]), sm._lca(s4,s8))


    def test_simple(self):
        s1 = fsm.State('s1')
        s2 = fsm.State('s2')
        fs = fsm.FinalState()
        
        sm = fsm.StateMachine(s1, s2, fs)

        s1 >> 'a' >> s2 >> 'b'>> fs

        trace((s1,s2,fs))

        sm.start()
        sm.post('a')
        sm.post('b')
        sm.join(1)

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

        s1 = fsm.State('s1')
        s2 = fsm.State('s2', parent=s1, initial=True)
        s3 = fsm.State('s3', parent=s2, initial=True)
        s4 = fsm.State('s4', parent=s2)

        s3 >> 'a' >> s4

        s5 = fsm.State('s5', parent=s1)
        s6 = fsm.State('s6', parent=s5)

        s4 >> 'b' >> s6 >> 'c' >> fsm.FinalState(parent=s5)
        s5 >> fsm.FinalState(parent=s1)

        sm = fsm.StateMachine(s1)

        trace((s1, s2, s3, s4, s5, s6))

        sm.start()
        sm.post('a', 'b', 'c')
        sm.join(1)

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
        s1 = fsm.State('s1')
        s2 = fsm.State('s2', parent=s1, initial=True)
        s3 = fsm.State('s3', parent=s2, initial=True)
        s4 = fsm.State('s4', parent=s2)

        s3 >> 'a' >> s4

        s5 = fsm.State('s5', parent=s1)
        s6 = fsm.State('s6', parent=s5, initial=True)

        s2 >> 'b' >> s5
        s5 >> 'c' >> fsm.FinalState(parent=s1)

        sm = fsm.StateMachine(s1)

        trace((s1, s2, s3, s4, s5, s6))

        sm.start()
        sm.post('a', 'b', 'c')
        sm.join(1)

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

        class MyTransition(fsm.Transition):
            def __init__(self, value):
                super(MyTransition, self).__init__()
                self.value = value
            def is_triggered(self, evt):
                return value[0] == self.value
            def do_action(self, sm, evt):
                value[0] += 1

        s1 = fsm.State('s1')
        s1 >> fsm.EqualsTransition('0', kind=fsm.Transition.EXTERNAL)
        s2 = fsm.State('s2', parent=s1, initial=True)
        j = fsm.Junction(parent=s1)
        s3 = fsm.State('s3', parent=s1)
        s4 = fsm.State('s4', parent=s1)

        s2 >> 'a' >> j >> MyTransition(0) >> s3
        j >> MyTransition(1) >> s4
        j >> MyTransition(2) >> fsm.FinalState(parent=s1)

        trace((s1, s2, s3, s4, j))

        sm = fsm.StateMachine(s1)

        sm.start()
        sm.post('a', '0', 'a', '0', 'a')
        sm.join(1)

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
        s1 = fsm.State('s1')
        s2 = fsm.State('s2')
        fs = fsm.FinalState()

        s1 >> fsm.Timeout(1) >> s2 >> fsm.Timeout(1) >> fs
        sm = fsm.StateMachine(s1, s2, fs)

        trace((s1, s2, fs))

        sm.start()

        self.assertFalse(Trace.contains([(s2, 'entry')], show_on_fail=False))
        time.sleep(1.1)
        self.assertTrue(Trace.contains([(s2, 'entry')]))
        self.assertFalse(Trace.contains([(fs, 'entry')], show_on_fail=False))

        sm.join(1.1)
        self.assertTrue(Trace.contains([(fs, 'entry')]))


    def test_timeout_cancel(self):
        s1 = fsm.State('s1')
        s2 = fsm.State('s2')
        fs = fsm.FinalState()

        s1 >> fsm.Timeout(1) >> s2 >> fsm.Timeout(1) >> fs
        s1 >> 'a' >> fs

        sm = fsm.StateMachine(s1, s2, fs)

        trace((s1, s2, fs))

        sm.start()
        self.assertFalse(Trace.contains([(s2, 'entry')], show_on_fail=False))
        time.sleep(.5)
        sm.post('a')
        
        sm.join(1)
        self.assertFalse(Trace.contains([(s2, 'entry')], show_on_fail=False))
        self.assertTrue(Trace.contains([(s1, 'exit'), (fs, 'entry')]))

    def test_parallel_state(self):
        p = fsm.ParallelState()
        s1 = fsm.State('s1', parent=p) # first region
        s2 = fsm.State('s2', parent=p)

        s11 = fsm.State('s11', parent=s1, initial=True)
        s12 = fsm.State('s12', parent=s1)
        s11 >> 'a' >> s12 >> 'b' >> fsm.FinalState(parent=s1)

        s21 = fsm.State('s21', parent=s2, initial=True)
        s21 >> 'a' >> fsm.FinalState(parent=s2)

        trace((p, s1, s11, s12, s2, s21))

        sm = fsm.StateMachine(p)
        sm.start()

        sm.post('a')
        sm.join(.1)
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
        self.assertFalse(Trace.contains([(s2, 'exit')], show_on_fail=False))

        sm.post('b')
        sm.join(1)
        self.assertTrue(Trace.contains([(s12, 'exit'), (s1, 'exit')]))
        self.assertTrue(Trace.contains([(s2, 'exit')]))

    def test_history_state(self):
        '''Check basic history state recovery when parent state is entered.
           Also show that transition to 'unitialized' history state follows
           standard state entry (to initial substate).'''
        s1 = fsm.State('s1') 
        s2 = fsm.State('s2')
        h = fsm.HistoryState(parent=s1)
        s11 = fsm.State('s11', parent=s1, initial=True)
        s12 = fsm.State('s12', parent=s1)
        s13 = fsm.State('s13', parent=s1)
        fs = fsm.FinalState()

        s2 >> 'a' >> h
        s11 >> 'b' >> s12 >> 'c' >> s13 >> 'd' >> s11
        s1 >> 'e' >> s2
        s2 >> 'f' >> fs

        trace((s1, s2, s11, s12, s13, fs))
        sm = fsm.StateMachine(s2, s1, fs)
        sm.start()

        sm.post('a', 'b', 'c', 'd', 'b', 'e', 'a', 'e', 'f')

        sm.join(1)
        
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

        s1 = fsm.State('s1') 
        s2 = fsm.State('s2')
        h = fsm.HistoryState(parent=s1)
        s11 = fsm.State('s11', parent=s1, initial=True)
        s12 = fsm.State('s12', parent=s1)
        fs = fsm.FinalState()

        h >> s12
        s2 >> 'a' >> h
        s1 >> 'b' >> s2 >> 'c' >> fs

        trace((s1, s2, s11, s12, fs))
        sm = fsm.StateMachine(s2, s1, fs)
        sm.start()

        sm.post('a', 'b', 'c')

        sm.join(1)

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

        s1 = fsm.State('s1')
        s2 = fsm.State('s2', parent=s1, initial=True)
        s3 = fsm.State('s3', parent=s1)

        s2 >> 'a' >> s3 >> 'b' >> s2
        t = fsm.EqualsTransition('c', kind=fsm.Transition.INTERNAL, source=s1)
        s1 >> 'd' >> fsm.FinalState(parent=s1)

        trace((s1, s2, s3, t))

        sm = fsm.StateMachine(s1)

        sm.start()

        sm.post('c', 'a', 'c', 'b', 'd')

        sm.join(1)

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

        s1 = fsm.State('s1', initial=True)
        s2 = fsm.State('s2', parent=s1, initial=True)
        s3 = fsm.State('s3')
        fs = fsm.FinalState()
        ts = fsm.TerminateState(parent=s1)

        s1 >> 'a' >> s3 >> 'b' >> fs
        s2 >> 'c' >> ts

        trace((s1, s2, s3, fs, ts))
        sm = fsm.StateMachine(s1, s3, fs)

        sm.start()
        sm.post('c', 'a', 'b')
        sm.join(1)

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
        r = fsm.State('root', 
                      fsm.State('s1') >> 'a' 
                      >> fsm.State('s2', fsm.State('s21') >> 'b' 
                                         >> fsm.State('s22')) 
                      >> 'c' >> fsm.FinalState('fs'))
        sm = fsm.StateMachine(r)
        self.assertEqual({'s1', 's2', 'fs'}, {s.name for s in sm._cstate.children})
        self.assertEqual({'s21', 's22'}, {s.name for s2 in sm._cstate.children if s2.name == 's2' for s in s2.children})

    def test_builder2(self):
        sm = fsm.StateMachine(
            fsm.State('s1') >> fsm.State('s2') >> fsm.FinalState('fs'))
        self.assertEqual({'s1', 's2', 'fs'}, {s.name for s in sm._cstate.children})

    def test_builder3(self):
        s1 = fsm.State('s1')
        b1 = fsm.State('s2') << s1 << fsm.InitialState()

        s3 = fsm.State('s3')
        b2 = fsm.State('s4') >> s3

        s1 >> s3

        sm = fsm.StateMachine(b2 >> b1)

    def test_get_active_states(self):
        s0 = fsm.ParallelState('root')
        s11 = fsm.State('s11', fsm.State('s111') >> 'c' >> fsm.State('s112'))
        s12 = fsm.State('s12')
        s21 = fsm.State('s21', fsm.State('s211') >> 'c' >> fsm.State('s212'))
        s22 = fsm.State('s22')
        s1 = fsm.State('s1', 
                       s11 >> 'a' >> s12 >> 'b' >> s11 >> 'd' >> fsm.FinalState(),
                       parent=s0) 
        s2 = fsm.State('s2',
                       s21 >> 'a' >> s22 >> 'b' >> s21 >> 'd' >> fsm.FinalState(),
                       parent=s0) 

        sm = fsm.StateMachine(s0)

        sm.start()
        sm.post('a')
        sm.join(.1)
        self.assertEqual({'s12', 's22', 's1', 'root', 's2'},
                         {s.name for (s,_) in s0.get_active_states()})
        sm.post('b')
        sm.join(.1)
        self.assertEqual({'s11', 's21', 's111', 's211', 's1', 'root', 's2'},
                         {s.name for (s,_) in s0.get_active_states()})
        sm.post('c')
        sm.join(.1)
        self.assertEqual({'s11', 's21', 's112', 's212', 's1', 'root', 's2'},
                         {s.name for (s,_) in s0.get_active_states()})
        sm.post('d')
        sm.join(1)

    def test_deep_history(self):
        '''Check deep history state directly inside Parallel State.'''
        p0 = fsm.ParallelState('p0')
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

        sm = fsm.StateMachine(p0, r0, j >> FinalState())
        sm.start()
        sm.join(.1)
        self.assertEqual({'p0', 's1', 's3'},
                         {s.name for (s,_) in sm._cstate.get_active_states() if s.name})
        sm.post('r')
        sm.join(.1)
        self.assertEqual({'r0', 'r01', 's7', 's5'},
                         {s.name for (s,_) in sm._cstate.get_active_states() if s.name})

        sm.post('1')
        sm.join(.1)
        self.assertEqual({'r0', 'r01', 's6', 's8'},
                         {s.name for (s,_) in sm._cstate.get_active_states() if s.name})
        
        sm.post('p')
        sm.join(.1)
        self.assertEqual({'p0', 's1', 's3'},
                         {s.name for (s,_) in sm._cstate.get_active_states() if s.name})

        sm.post('1')
        sm.join(.1)
        self.assertEqual({'p0', 's2', 's4'},
                         {s.name for (s,_) in sm._cstate.get_active_states() if s.name})

        sm.post('r')
        sm.join(.1)
        self.assertEqual({'r0', 'r01', 's6', 's8'},
                         {s.name for (s,_) in sm._cstate.get_active_states() if s.name})

        sm.post('3')
        sm.join(.1)
        self.assertEqual({'r0', 'r02'},
                         {s.name for (s,_) in sm._cstate.get_active_states() if s.name})

        sm.post('p')
        sm.join(.1)
        self.assertEqual({'p0', 's2', 's4'},
                         {s.name for (s,_) in sm._cstate.get_active_states() if s.name})

        sm.post('r')
        sm.join(.1)
        self.assertEqual({'r0', 'r02'},
                         {s.name for (s,_) in sm._cstate.get_active_states() if s.name})

        sm.post('e')
        sm.join(1)

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

        sm = fsm.StateMachine(s1, s2, fs)
        sm.start()

        sm.post('a', '2', '1', 'b', '2', '1', 'e')
        sm.join(1)
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

# vim:expandtab:sw=4:sts=4
