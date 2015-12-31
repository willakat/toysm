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

import copy
import unittest

from toysm import *
from toysm.base_sm import (ignore_states, ignore_transitions,
                           BadSMDefinition,
                           on_enter, on_exit, trigger, action)
from sm_trace import Trace, trace

import logging
LOG_LEVEL = logging.INFO
# LOG_LEVEL = logging.DEBUG

logging.basicConfig(level=LOG_LEVEL)


class TestInheritance(unittest.TestCase):
    def setUp(self):
        Trace.clear()

    def test_state_copy(self):
        # Define all fields in a State and make a copy
        def f1(a, b): pass
        def f2(a, b): pass
        def f3(a, b): pass
        p = State()
        s = State(name='s', on_enter=f1, on_exit=f2, do=f3, parent=p)
        s.add_hook('post_entry', lambda a,b: None)
        s1 = State(parent=s, initial=True)
        State() >> s >> State()

        s_copy = copy.copy(s)
        self.assertIsNot(s, s_copy)
        self.assertIs(s.name, s_copy.name)
        self.assertIs(s._on_enter, s_copy._on_enter)
        self.assertIs(s._on_exit, s_copy._on_exit)
        self.assertIs(s.do_activity, s_copy.do_activity)
        for h, l in s_copy.hooks.items():
            self.assertListEqual(l, [])
        self.assertListEqual(s_copy.transitions, [])
        self.assertListEqual(s_copy.rev_transitions, [])
        self.assertIsNone(s_copy.parent)
        self.assertIsNone(s_copy.initial)
        self.assertSetEqual(s_copy.children, set())

    def test_transition_copy(self):
        def f1(a, b): pass
        def f2(a, b, c): pass
        t = Transition(trigger=f1, action=f2)
        t.add_hook(f2)
        State() >> t >> State()

        t_copy = copy.copy(t)

        self.assertIsNot(t, t_copy)
        self.assertIs(t.desc, t_copy.desc)
        self.assertIs(t.kind, t_copy.kind)
        self.assertIsNone(t_copy.source)
        self.assertIsNone(t_copy.target)
        self.assertIs(t.trigger, t_copy.trigger)
        self.assertIs(t.action, t_copy.action)
        self.assertListEqual(t_copy.hooks, [])

    def test_smcopy(self): # TODO!!!!
        """
        Confirm that a graph produced by _sm_copy shares all the characteristics
        of the copied graph.
        """
        # def are_sm_equiv(a, b, seen_map):
        #     if a is None and b is None:
        #         return True
        #     if a in seen_map:
        #         return b is seen_map[a]
        #     seen_map[a] = b
        #     return (
        #         type(a) is type(b) and
        #         are_sm_equiv(a.parent, b.parent, seen_map) and
        #         [c in a.children ]
        #     )
        pass

    def test_isolation(self):
        """
        Confirm that manipulating (adding transitions) in a StateMachine
        subclass doesn't alter the original StateMachine.
        """
        pass

    def test_ignore_states(self):
        class C(StateMachine):
            i = InitialState()
            s1 = State()
            s2_1 = State()
            s2_2 = State()
            s3 = State()

            t_s1_a = EqualsTransition('a')
            t_s1_b = EqualsTransition('b')

            i >> s1 >> t_s1_a >> s2_1 >> s3
            s1 >> t_s1_b >> s2_2 >> s3

        class D(C):
            ignore_states('s2_1')

        self.assertEqual(len(C._states) - 1, len(D._states))
        self.assertSetEqual(set(C._states.keys()) - {'s2_1'},
                            set(D._states.keys()))
        self.assertEqual(len(C._transitions) - 1, len(D._transitions))
        self.assertSetEqual({'t_s1_b'}, set(D._transitions.keys()))

    def test_ignore_transitions(self):
        class C(StateMachine):
            i = InitialState()
            s1 = State()
            s2_1 = State()
            s2_2 = State()
            s3 = State()

            t_s1_a = EqualsTransition('a')
            t_s1_b = EqualsTransition('b')

            i >> s1 >> t_s1_a >> s2_1 >> s3
            s1 >> t_s1_b >> s2_2 >> s3

        class D(C):
            ignore_transitions('t_s1_a')

        self.assertEqual(len(C._states), len(D._states))
        self.assertEqual(len(C._transitions) - 1, len(D._transitions))
        self.assertSetEqual({'t_s1_b'}, set(D._transitions.keys()))

    def test_inexistent_ignore(self):
        """Attempts to ignore States/Transitions unknown to at least
           on super class should raise a BadSMDefinition exception."""
        class C(StateMachine):
            s1 = State()
            InitialState() >> s1

        def bad_ignore_state():
            class D(C):
                ignore_states('no_such_state')

        def bad_ignore_transition():
            class D(C):
                ignore_transitions('no_such_transition')

        self.assertRaises(BadSMDefinition, bad_ignore_state)
        self.assertRaises(BadSMDefinition, bad_ignore_transition)

    def test_state_override(self):
        saved_refs = {}

        class C(StateMachine):
            s1 = State()
            InitialState() >> s1
            s1 >> FinalState()
            trace(s1)
            saved_refs["C.s1"] = s1

        class D(C):
            @on_enter(C.s1)
            def s1_enter(sm, state):
                Trace.add(state, 'overload in')

            @on_exit(C.s1)
            def s1_exit(sm, state):
                Trace.add(state, 'overload exit')

            trace(C.s1)     # the traced state will be D's copy of s1
            saved_refs["D.s1"] = C.s1

        c = C()
        c.start()
        c.join(.1)
        self.assertTrue(Trace.contains([(saved_refs["C.s1"], "entry"),
                                        (saved_refs["C.s1"], "exit")]))
        self.assertFalse(Trace.contains([(saved_refs["C.s1"], "overload in")],
                                        show_on_fail=False))
        self.assertFalse(Trace.contains([(saved_refs["C.s1"], "overload exit")],
                                        show_on_fail=False))
        Trace.clear()
        d = D()
        d.start()
        d.join(.1)
        self.assertTrue(Trace.contains([(saved_refs["D.s1"], "entry"),
                                        (saved_refs["D.s1"], "exit")]))
        self.assertTrue(Trace.contains([(saved_refs["D.s1"], "overload in"),
                                        (saved_refs["D.s1"], "overload exit")]))

    def test_transition_override(self):
        saved_refs = {}

        class C(StateMachine):
            t = Transition()
            @trigger(t)
            def a_trigger(sm, evt):
                return 'a' == evt

            @action(t)
            def a_action(sm, evt):
                Trace.add(C._transitions['t'], 'a action')

            InitialState() >> State() >> t >> FinalState()
            saved_refs["C.t"] = t

        class D(C):
            @trigger(C.t)
            def b_trigger(self, evt):
                return 'b' == evt

            @action(C.t)
            def b_action(self, evt):
                Trace.add(D._transitions['t'], 'b action')

            saved_refs["D.t"] = C.t

        c = C()
        c.post('a')
        c.start()
        c.join(.1)
        self.assertTrue(Trace.contains([(saved_refs["C.t"], "a action")]))
        self.assertFalse(Trace.contains([(saved_refs["C.t"], "b action")],
                                        show_on_fail=False))
        Trace.clear()

        d = D()
        d.start()
        d.post('a')
        d.settle(.1)
        self.assertFalse(Trace.contains([(saved_refs["D.t"], "a action")],
                                        show_on_fail=False))
        self.assertFalse(Trace.contains([(saved_refs["D.t"], "b action")],
                                        show_on_fail=False))
        d.post('b')
        d.join(.1)
        self.assertFalse(Trace.contains([(saved_refs["D.t"], "a action")],
                                        show_on_fail=False))
        self.assertTrue(Trace.contains([(saved_refs["D.t"], "b action")]))

    def test_transition_override2(self):
        class C(StateMachine):
            t = Transition()
            @trigger(t)
            def a_trigger(sm, evt):
                return 'a' == evt

            @action(t)
            def a_action(sm, evt):
                Trace.add('t', 'a action')

            InitialState() >> State() >> t >> FinalState()

        class D(C):
            @trigger(C.t)
            def b_trigger(sm, evt):
                return C.a_trigger(sm, evt) or 'b' == evt

        d = D()
        d.post('a')
        d.start()
        d.join(.1)
        self.assertTrue(Trace.contains([('t', "a action")]))

        Trace.clear()

        d = D()
        d.post('b')
        d.start()
        d.join(.1)
        self.assertTrue(Trace.contains([('t', "a action")]))

class TestComposition(unittest.TestCase):
    def setUp(self):
        Trace.clear()

    def test_simple_composition(self):
        saved_refs = {}

        class A(StateMachine):
            a_0 = InitialState()
            a_1 = State()
            a_2 = FinalState()
            a_0 >> a_1 >> 'b' >> a_2

        class B(StateMachine):
            b_0 = InitialState()
            b_0 >> State() >> 'a' >> A.as_state()
            trace([b_0, A.a_1, A.a_2])
            saved_refs["B.b_0"] = b_0
            saved_refs["A.a_1"] = A.a_1
            saved_refs["A.a_2"] = A.a_2

        b = B()
        b.post('a', 'b')
        b.start()
        b.join(.1)

        self.assertTrue(Trace.contains([(saved_refs["B.b_0"], "entry"),
                                        (saved_refs["B.b_0"], "exit"),
                                        (saved_refs["A.a_1"], "entry"),
                                        (saved_refs["A.a_1"], "exit"),
                                        (saved_refs["A.a_2"], "entry")]))

    def test_multi_composition(self):
        saved_refs = {}

        class A(StateMachine):
            a_0 = InitialState()
            a_1 = State()
            a_2 = FinalState()
            a_0 >> a_1 >> 'a' >> a_2

        class B(StateMachine):
            b_0 = InitialState()
            b_1 = A.as_state()
            b_2 = A.as_state()
            b_0 >> b_1 >> b_2 >> FinalState()
            trace([b_1, b_2])
            saved_refs["B.b_1"] = b_1
            saved_refs["B.b_2"] = b_2

        b = B()
        b.post('a', 'a')
        b.start()
        b.join(.1)

        self.assertIsNot(saved_refs["B.b_1"], saved_refs["B.b_2"])
        self.assertTrue(Trace.contains([(saved_refs["B.b_1"], "entry"),
                                        (saved_refs["B.b_1"], "exit"),
                                        (saved_refs["B.b_2"], "entry"),
                                        (saved_refs["B.b_2"], "exit")]))


if __name__ == '__main__':
    unittest.main()

# vim:expandtab:sw=4:sts=4
