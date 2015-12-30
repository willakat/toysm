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

import copy
import threading
import inspect
from six import with_metaclass

from toysm.public import public
from toysm.fsm import StateMachine
from toysm.core import Transition, State, InitialState, IllFormedException


@public
class BadSMDefinition(Exception):
    """Exception raised when declaring a StateMachine that deviates
       from expected constraints."""
    pass


@public
def create_copy_context():
    """
    Force the creation of a new StateMachine definition context.

    This method should rarely be useful since under most circumstances
    the definition context will be created automatically. However
    if a StateMachine needs to be declared within the scope of another
    StateMachine decleration, the "inner" StateMachine needs to begin
    with a call to create_create_copy_context. For instance:

    class Outer(SomeStateMachine):
        s = State()

        class Inner(SomeOtherStateMachine):
            create_copy_context()
            s = State()

            ...
    """
    _copy_context_stack.new_ctx()


@public
def ignore_states(*states):
    """
    Declare states to be ignored in the context of the current
    StateMachine definition.

    Multiple calls are allowed and their effect is cumulative, however
    a BadSMDefinition exception will be raised if ignore_states are used
    after having accessed states or transitions from superclasses.

    Args:
        states(str): name of attributes designating States
                     in the superclass of the StateMachine being
                     defined.
    """
    if {type(s) for s in states} != {str}:
        raise BadSMDefinition("Ignored states must be referenced by attribute "
                              "name (e.g. a string).")
    ctx = _copy_context_stack.get_ctx()
    if ctx.copy_map:
        raise BadSMDefinition("Ignored states must be declared before they "
                              "are referenced by the StateMachine definition.")
    ctx.ignored_states |= set(states)


@public
def ignore_transitions(*transitions):
    """
    Declare transitions to be ignored in the context of the current
    StateMachine definition.

    Multiple calls are allowed and their effect is cumulative, however
    a BadSMDefinition exception will be raised if ignore_transitions are used
    after having accessed states or transitions from superclasses.

    Args:
        transitions(str): name of attributes designating Transitions
                          in the superclass of the StateMachine being
                          defined.
    """

    if {type(t) for t in transitions} != {str}:
        raise BadSMDefinition("Ignored transitions must be referenced by "
                              "attribute name (e.g. a string).")
    ctx = _copy_context_stack.get_ctx()
    if ctx.copy_map:
        raise BadSMDefinition("Ignored transitions must be declared before they"
                              " are referenced by the StateMachine definition.")
    ctx.ignored_transitions |= set(transitions)


################################################################################
# State and Transition overrides

def _mk_override(item, attr):
    def override(f):
        setattr(item, attr, f)
        return staticmethod(f)

    return override


@public
def on_enter(state):
    return _mk_override(state, '_on_enter')


@public
def on_exit(state):
    return _mk_override(state, '_on_exit')


@public
def do_activity(state):
    return _mk_override(state, 'do_activity')


@public
def trigger(transition):
    return _mk_override(transition, 'trigger')


@public
def action(transition):
    return _mk_override(transition, 'action')


################################################################################
# Copy of State/Transition graphs

def _resolve_symbol(symbol, expected_type=None):
    # Determine callers globals & locals
    this_module = None
    path = symbol.split('.')
    try:
        for frame in [f[0] for f in inspect.stack()]:
            module = inspect.getmodule(frame)
            if this_module is None:
                this_module = module
                continue
            if module != this_module:
                # Go up one frame relative to the definition
                # of the calling class.
                # This is very hackish, the proper way to achieve
                # this would be to do an LEGB lookup from within
                # the StateMachine subclass definition context.
                frame = frame.f_back
                break
        caller_globals, caller_locals = frame.f_globals, frame.f_locals

        # Resolve the symbol in the caller's context
        elt = eval('.'.join(path[:-1]), caller_globals, caller_locals)
        resolved = elt.__dict__[path[-1]]
        if expected_type and type(resolved) != expected_type:
            raise BadSMDefinition("Excpected %s to be an instance of %s",
                                  symbol, expected_type.__name__)
    finally:
        del frame


class _SMCopyContextStack(threading.local):
    def __init__(self):
        super(_SMCopyContextStack, self).__init__()
        self._stack = []

    def get_ctx(self):
        if not self._stack:
            return self.new_ctx()
        else:
            return self._stack[-1]

    def new_ctx(self):
        ctx = SMCopyContext()
        self._stack.append(ctx)
        return ctx

    def pop_ctx(self):
        if self._stack:
            return self._stack.pop()
        else:
            # Pop is called when finishing StateMachine class creation,
            # if the stack is empty at that point, this implies that
            # no copies of outside States/Transitions have yet been made.
            return SMCopyContext()


_copy_context_stack = _SMCopyContextStack()


class SMCopyContext:
    def __init__(self):
        self.copy_map = {}
        self.ignored_states = set()
        self.ignored_transitions = set()


def _get_ignored(copy_ctx, cls):
    if cls is None:
        ignored_states = set()
        ignored_transitions = set()
    else:
        ignored_states = {cls._states[s] for s in copy_ctx.ignored_states
                          if s in cls._states}
        ignored_transitions = {cls._transitions[t]
                               for t in copy_ctx.ignored_transitions
                               if t in cls._transitions}
    return ignored_states, ignored_transitions


def _sm_copy(state, copy_ctx, cls=None):
    """
    Return a copy of the State.

    The copy will have the same structure as the original
    State, however all transitions and states it has
    a relation to will also be copies.

    Args:
        copy_ctx: the resulting State/Transition graph
                  will draw on entries from this map when the copy_ctx
                  contains an existing mapping for a copied state.
                  For instance if the State to be copied has
                  a transition to another State that
                  is already present as a key in copy_ctx.copy_map,
                  then the copy returned by sm_copy will
                  have a copy of this transition with
                  a target set to the corresponding value from
                  the copy_map.

                  The relationship between the State sm_copy
                  is added to the copy_map.

                  copy_ctx.{ignore_states,ignore_transitions} will
                  be used to skip any States/Transitions they contain.
                  The resulting State/Transition graph will therefore
                  be a partial copy.
        cls:      Class sm_copy was invoked for (e.g. <Class>.<state attribute>)
                  Will be used to resolve ignored_states and
                  ignored_transitions.
    """
    copy_map = copy_ctx.copy_map
    if state in copy_map:
        return copy_map[state]
    ignored_states, ignored_transitions = _get_ignored(copy_ctx, cls)
    if state in ignored_states:
        return
    copy_map[state] = s_copy = copy.copy(state)
    for trans in state.transitions:
        if trans.target in ignored_states or trans in ignored_transitions:
            continue
        trans_copy = copy_map.get(trans)
        if trans_copy is None:
            trans_copy = copy.copy(trans)
            s_copy.add_transition(trans_copy)
            if trans.target is not None:
                t_copy = _sm_copy(trans.target, copy_ctx, cls)
                t_copy.accept_transition(trans_copy)
            copy_map[trans] = trans_copy

    # Recursively copy children. The parent isn't copied,
    # it is therefore up to a copied parent to connect
    # with the copied children.
    for c in state.children:
        if c in ignored_states:
            continue
        c_copy = _sm_copy(c, copy_ctx, cls)
        c_copy.set_parent(s_copy, initial=c is state.initial)
    return s_copy


################################################################################
# Reachability in a State/Transition Graph

def _find_reachable(states, reachable=None):
    """
    Returns the transitive closure of states using forward/back Transitions.

    Resulting set will contain States that:
    - either are reachable through Transitions from the states given
      as an argument
    - or can reach these states.

    Args:
        states (iterable): The starting set of states to follow Transitions
                           from.
        reachable (set):   The accumulated set of states that have for now
                           been reached (from the starting states).
    """
    if reachable is None:
        reachable = set()
    for s in states:
        if s in reachable:
            continue
        reachable.add(s)
        _find_reachable([t.target for t in s.transitions
                         if t.target is not None], reachable)
        _find_reachable([t.source for t in s.rev_transitions], reachable)
        _find_reachable(s.children, reachable)
        if s.parent is not None:
            _find_reachable([s.parent], reachable)
    return reachable


################################################################################
# Base classes for StateMachines

class Xmeta(type):
    def __new__(mcs, name, bases, dct):
        # x collect the copy_map in the ThreadLocal if one is defined

        # x move all Transition and State attributes into two specific
        #   dicts: _states, _transitions

        # x copy _states and _transitions from the XStateMachine
        #   classes found in bases.
        #   The copy should check if the State/Transition is already in
        #   the copy_map, if so _state/_map is updated with the value from
        #   copy_map. Otherwise a fresh copy of the State/Transition is
        #   used.
        #   If there is either an ignored_states or
        #   ignored_transitions in dict, then the State/Transition should be
        #   skipped.

        # x perform replacements of overridden SM elements in the corresponding
        #   states by overwriting the corresponding attribute.
        #   => this is actually handled by decorators operating on the State
        #      copies.

        # x pop the copy_map off the stack.

        # x identify the initial state:
        #   + if a _states contains a single state, it becomes the c_state
        #     for StateMachine instances
        #   + if there are several states, only one must be an "Initial" state.

        # x automatically name states after their attribute (if they
        #   haven't been named explicitly)

        # Problems:
        # - if ignored_states is expressed something like: [ SuperSM.s1, ... ]
        #   this will trigger a (useless) copy. => Use quoted names.
        # - when using quoted names, SMContext needs to be convert
        #   to real State/Transition objects.
        # - support for States not bound to a class attribute:
        #   State() >> SomeStateMachine.some_state
        #   options:
        #   1. force State() to be bound to an attribute => meh
        #   2. Change >> operator to record additional info in the
        #      CopyContext
        #   3. modify SomeStateMachine.some_state (which is a copy) to
        #      record inbound transition when accept_transition is called.
        #      Still leaves the problem of
        #       State() >> State () >> XX.some_state
        #   4. State could have back-transition information:
        #      just a matter of following forward and back transitions
        #      to determine closure.

        # 1. Generate states/transitions maps for the new class
        #    by merging those from the superclasses.
        ctx = _copy_context_stack.pop_ctx()
        states = {}
        transitions = {}
        unknown_ignored_states = set(ctx.ignored_states)
        unknown_ignored_transitions = set(ctx.ignored_transitions)
        copied_initial = False
        for b in bases:
            if not (hasattr(b, '_states') or hasattr(b, '_transitions')):
                continue
            # copy the first non-ignored base class initial state
            if not copied_initial:
                if not b._auto_cstate:
                    _sm_copy(b._cstate, ctx, b)
                    copied_initial = True
                elif _sm_copy(b._cstate.initial, ctx, b) is not None:
                    # If the initial state of the b's _cstate is an ignored
                    # state, it is skipped (i.e. Initial state will be provided
                    # in the class being defined or from another one of the
                    # base classes.
                    copied_initial = True
            states.update(
                    {attr: _sm_copy(state, ctx, b)
                     for (attr, state) in b._states.items()
                     if attr not in states and
                     attr not in ctx.ignored_states})
            transitions.update(
                    {attr: ctx.copy_map[trans]
                     for (attr, trans) in b._transitions.items()
                     if attr not in transitions and
                     trans in ctx.copy_map})
            unknown_ignored_states -= set(b._states.keys())
            unknown_ignored_transitions -= set(b._transitions.keys())
        if unknown_ignored_states:
            raise BadSMDefinition("The following ignored states were not "
                                  "defined in any superclass of %s: %s" %
                                  (name, unknown_ignored_states))
        if unknown_ignored_transitions:
            raise BadSMDefinition("The following ignored transitions were not "
                                  "defined in any superclass of %s: %s" %
                                  (name, unknown_ignored_transitions))

        # 2. update the states/transitions with any declarations
        #    from the scope of the new class' definition.
        for (attr, value) in dct.items():
            if isinstance(value, State):
                states[attr] = value
                # Automatically assign a name to states that weren't
                # explicitly provided with one
                if value.name is None:
                    value.name = attr
            elif isinstance(value, Transition):
                transitions[attr] = value
            else:
                continue
            del dct[attr]

        # 3. Figure out what the class's top-level state should be:
        #    - if only one is present in the definition, pick that one
        #    - otherwise generate a new top-level state that includes
        #      all the known ones.
        if states or transitions:
            dct['_states'] = states
            dct['_transitions'] = transitions
            known_states = set(states.values()) | {t.source for t in
                                                   transitions.values()}
            top_lvl_states = {s for s in _find_reachable(known_states)
                              if s.parent is None}
            if len(top_lvl_states) == 1:
                for top in top_lvl_states:
                    break
                dct['_cstate'] = top
                dct['_auto_cstate'] = False
            else:
                initial_candidates = {s for s in top_lvl_states
                                      if isinstance(s, InitialState)}
                if len(initial_candidates) != 1:
                    raise IllFormedException(
                            "StateMachine definition needs exactly"
                            " one top-level initial state.")
                top = dct['_cstate'] = State(name=name)
                dct['_auto_cstate'] = True
                for s in top_lvl_states:
                    top.add_state(s)
        return type.__new__(mcs, name, bases, dct)

    def __getattr__(cls, item):
        state = cls.get_state(item)
        if state is not None:
            return state
        transition = cls.get_transition(item)
        if transition is not None:
            return transition
        raise AttributeError("StateMachine has no '%s' State/Transition" % item)

    def __dir__(cls):
        cls_dir = set(dir(super(XStateMachine, cls)) +
                      cls.__dict__.keys() +
                      cls._states.keys() +
                      cls._transitions.keys())
        return sorted(cls_dir)


class XStateMachine(with_metaclass(Xmeta, StateMachine)):
    def __init__(self):
        # To be removed at one point...
        super(XStateMachine, self).__init__(self._cstate)
        # super(XStateMachine, self).__init__()

    @classmethod
    def get_state(cls, name):
        """Returns a copy of a named State from a StateMachine.

        Use of this method is only necessary when trying to access a State
        that has a name that overrides one of the StateMachine's
        attribute names."""
        if name in cls._states:
            state = cls._states[name]
            ctx = _copy_context_stack.get_ctx()
            if name in ctx.ignored_states:
                raise BadSMDefinition("Reference to ignored state %s" %
                                      state)
            return _sm_copy(state, ctx, cls)

    @classmethod
    def get_transition(cls, name):
        """Returns a copy of a named Transition from a StateMachine.

        Use of this method is only necessary when trying to access a Transition
        that has a name that overrides one of the StateMachine's
        attribute names."""
        if name in cls._transitions:
            transition = cls._transitions[name]
            ctx = _copy_context_stack.get_ctx()
            if name in ctx.ignored_transitions:
                raise BadSMDefinition("Reference to ignored transition %s" %
                                      transition)
            # force copy of source state (note this will not do anything
            # if the State was already copied)
            _sm_copy(transition.source, ctx, cls)
            return ctx.copy_map[transition]

    @classmethod
    def as_state(cls):
        """"
        Returns a copy of the this StateMachine's top-level state.

        This method provides a simple way to achieve StateMachine
        composition.
        """
        ctx = _copy_context_stack.get_ctx()
        return _sm_copy(cls._cstate, ctx)

# s1 = State()


# class C(XStateMachine):
#     print 't1', id(XStateMachine.s1)
#     print 't2', id(XStateMachine.s1)
#     InitialState() >> XStateMachine.s1
#     print repr(XStateMachine.s1.rev_transitions)
#
#     @on_enter(XStateMachine.s1)
#     def s1_enter(sm, state):
#         print "s1 entered!"

# x = XStateMachine()
# c = C()
# c.graph()

# vim:expandtab:sw=4:sts=4
