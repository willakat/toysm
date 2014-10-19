import unittest
import time

import logging

LOG_LEVEL = logging.INFO
LOG_LEVEL = logging.DEBUG

logging.basicConfig(level=LOG_LEVEL)

import fsm

class Trace:
    evt_log = []

    @classmethod
    def add(cls, elt, type=None):
       cls.evt_log.append((elt, type))

    @classmethod
    def contains(cls, seq, strict=False, show_on_fail=True):
        try:
            i = 0
            j = i + 1 if strict else len(cls.evt_log)
            for e in seq:
                i = cls.evt_log.index(e, i)
                if strict:
                    j = i + 1
            return True
        except ValueError:
            if show_on_fail:
                print ('Did not find e (%s, %r)'%(e[0], e[1]))
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
        

class TraceDecorator(object):
    _decorated = {}
    def _enter(self, sm):
        Trace.add(self, 'entry')
        super(TraceDecorator, self)._enter(sm)

    def _exit(self, sm):
        super(TraceDecorator, self)._exit(sm)
        Trace.add(self, 'exit')

    def do_action(self, sm, evt):
        super(TraceDecorator, self).do_action(sm, evt)
        Trace.add(self, 'action')
        
#class State(TraceMixin, fsm.State): pass
#fsm.State = State
#
#class Transition(TraceMixin, fsm.Transition): pass
#fsm.Transition = Transition

def trace(elt, transitions=True):
    if not elt:
        return None
    if not hasattr(elt, '__iter__'):
        elt = [elt]
    for e in elt:
        eclass = e.__class__
        dclass = TraceDecorator._decorated.get(eclass, None)
        if dclass is None:
            class dclass(TraceDecorator, eclass): pass
            dclass.__name__ = eclass.__name__
            TraceDecorator._decorated[eclass] = dclass
        e.__class__ = dclass
        if transitions and isinstance(e, fsm.State):
            trace(tuple(e.transitions), transitions=False)
    return elt if len(elt) > 1 else elt[0]

def trace(elt, transitions=True):
    if not elt:
        return None
    if not hasattr(elt, '__iter__'):
        elt = [elt]

    def h(sm, elt, *args, msg=None):
        Trace.add(elt, msg)

    for e in elt:
        if isinstance(e, fsm.State):
            e.add_entry_hook(h, msg='entry')
            e.add_exit_hook(h, msg='exit')
            if transitions and isinstance(e, fsm.State):
                trace(tuple(e.transitions), transitions=False)
        else:
            e.add_hook(h, msg='action')
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
        sm.assign_depth()

        self.assertEqual(([s1],[s1, s3]), sm.lca(s1, s3))
        self.assertEqual(([s2, s1],[s1]), sm.lca(s2, s1))
        self.assertEqual(([s2, s1],[s1, s3]), sm.lca(s2, s3))
        self.assertEqual(([s2],[s2]), sm.lca(s2, s2))

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
        sm.assign_depth()

        self.assertEqual(([s3,s2,s1],[s1, s5, s6, s7]), sm.lca(s3, s7))
        self.assertEqual(([s3,s2],[s2, s4]), sm.lca(s3, s4))
        self.assertEqual(([s4,s2,s1],[s1,s5,s8]), sm.lca(s4,s8))


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
        sm.join()

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
        sm.join()

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
        sm.join()

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
        s1 >> fsm.EqualsTransition('0', type=fsm.Transition.EXTERNAL)
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


# vim:expandtab:sw=4:sts=4
