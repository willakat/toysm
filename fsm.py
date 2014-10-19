# TODO:
# - python2 issues:
#   - sched.run doesn't support the non-blocking variant
# - graph
# - debug
#   1.one state instance
#   2.one state class
#   3.the entire fsm
#   for 1 & 2, a decorator/function to be applied to class/instance much
#   like the Trace used in the test classes.
# - threaded state
# - history states
# x s1>'x'>s2 doesn't work because it translates to s1 > 'x' and 'x'>s2...
#   whereas (s1 > 'x') > s2 works and so does s1 > ('x' > s2) !!!!
#   => resolved by using r/lshift operators
# - multi-intance FSM: 
#   - a function is used to determine a key based on Events posted
#     to event queue, each unknown key yields a new FSM, and those
#     that yield a known key are processed by their specific FSM.
# x replace on_entry by _on_entry and have the latter callback into an
#   optional user defined on_enty. Same for on_exit/_on_exit.
# - Allow State constructor to receive substates, e.g. 
#   State('s1', sub=[State('s2'), ...])
#   => Builder idea
# x Transition metaclass to register subclasses and associated
#   compatible ctor arguments
# - on_entry and on_exit should /also/ be called for toplevel state in FSM
# ? 'else' type guard
# - on_entry/on_exit should be called on root level State of the StateMachine
# ? get_*_transitions methods could _yield_ their result

import collections
try:
    import queue
except ImportError:
    # python2
    import Queue as queue
import sched
import time
from inspect import isclass
from threading import Thread

import logging

from six import with_metaclass

LOG = logging.getLogger(__name__)

class State(object):
    def __init__(self, name=None, parent=None, initial=False):
        self.transitions = set()
        self.dflt_transition = None
        self.name = name
        self.initial = None # Initial substate (if any)
        self.children = set()
        self.active_substate = None
        self.entry_hooks = []
        self.exit_hooks = []
        if parent:
            parent.add_state(self, initial=initial)
        else:
            self.parent = None

    def get_enabled_transitions(self, evt):
        '''Return transitions from the state for the given event, or None
           for states that are never the source of transition (e.g.
           TerminateState and FinalState).'''
        LOG.debug("%s - get_enabled_transitions for %r", self, evt)
        # children transitions have a higher priority
        if self.active_substate:
            substate_transitions = self.active_substate.get_enabled_transitions(evt)
            if substate_transitions:
                return substate_transitions
        # No enabled children transitions, try those defined for this state.
        return self._get_local_enabled_transitions(evt)

    def _get_local_enabled_transitions(self, evt):
        '''Return transitions for event with this state as source.'''
        for t in self.transitions:
            if t.is_triggered(evt):
                LOG.debug('%s - transition triggered by event %r: %s',
                          self, evt, t)
                transitions = [t]
                if isinstance(t.target, PseudoState):
                    compound_transition = t.target.get_enabled_transitions(None)
                    if compound_transition:
                        transitions += compound_transition
                    elif compound_transition is not None:
                       # no transitions for Event from PseudoState
                       # the compound transition is _not_ enabled.
                        continue
                    # else compound_transition is None: State with no
                    # egress transitions.
                return transitions
        else:
            LOG.debug("%s - no transitions found for %r", self, evt)
            return []

    def get_entry_transitions(self):
        if self.children:
            if self.initial:
                return [Transition(source=self, target=self.initial, type=Transition._ENTRY)]
            else:
                raise "Ill-Formed: no Initial state identified for %s"%tgt
        else:
            return []

    def child_completed(self, sm, child):
        pass

    def on_entry(self, sm): pass

    def _enter(self, sm):
        '''Called when a state is entered.
           Not intended to be overriden, subclass specific behavior
           should be implemented in _enter_actions.
        '''
        LOG.debug("%s - Entering state", self)
        for hook in self.entry_hooks:
            h, args, kargs = hook
            h(sm, self, *args, **kargs)
        self.on_entry(sm)
        self._enter_actions(sm)

    def _enter_actions(self, sm):
        if not self.children:
            sm.post_completion(self)

    def on_exit(self, sm): pass

    def _exit(self, sm):
        self._exit_actions(sm)
        self.on_exit(sm)
        for hook in self.exit_hooks:
            h, args, kargs = hook
            h(sm, self, *args, **kargs)
        LOG.debug("%s - Exiting state", self)

    def _exit_actions(self,sm):
        if self.active_substate:
            self.active_substate._exit(sm)
            self.active_substate = None

    def add_transition(self, t):
        '''Sets this state as the source of Transition t.'''
        if t.source:
            t.source.transitions.discard(t)
        t.source = self
        self.transitions.add(t)

    def accept_transition(self, t):
        '''Called when a transition designates the state as its target.'''
        t.target = self

    def add_state(self, state, initial=False):
        '''Add a substate to this state, if initial is True then the substate
           will be considered the initial substate.'''
        self.children.add(state)
        state.parent = self
        if isinstance(state, IntialState) or initial:
            self.initial = state

    def add_entry_hook(self, hook, *args, **kargs):
        self.entry_hooks.append((hook, args, kargs))

    def add_exit_hook(self, hook, *args, **kargs):
        self.exit_hooks.insert(0, (hook, args, kargs))

    def __str__(self):
        return "{%s%s}"%(self.__class__.__name__, 
                         '-%s'%self.name if self.name else '')

    def __rshift__(self, other):
    #def __gt__(self, other):
        if isinstance(other, State):
            # Completion transition
            Transition(source=self, target=other)
        else:
            other = Transition.make_transition(other)
            self.add_transition(other)
        return other

    def __lshift__(self, other):
    #def __lt__(self, other):
        if isinstance(other, State):
            # Completion transition
            Transition(source=other, target=self)
        else:
            other = Transition.make_transition(other)
            self.accept_transition(other)
        return other


class ParallelState(State):
    def add_state(self, state):
        if isinstance(state, PseudoState):
            raise Exception("PseudoStates cannot be added to a ParallelState")
        super(State, self).add_state(state)

    def add_state(self, state):
        super(ParallelState, self).add_state(state, initial=False)

    def get_enabled_transitions(self, evt):
        substate_transitions = []
        for c in self.children:
            substate_transitions += self.active_substate.get_enabled_transitions(evt)
        if substate_transitions:
            return substate_transitions
        else:
            return self._get_local_enabled_transitions(evt)

    def get_entry_transitions(self):
        return [Transition(source=self, target=c, type=Transition._ENTRY)
                for c in self.children]

    def child_completed(self, sm, child):
        self._still_running_children.remove(child)
        if not self._still_running_children: # All children states/regions have completed
            sm.post_completion(self)

    def _enter_actions(self, sm):
        LOG.debug('pstate children %s', self.children)
        self._still_running_children = set(self.children)

    def _exit_actions(self, sm):
        for c in self.children:
            c._exit(sm)

class PseudoState(State):
    def __init__(self, initial=False, **kargs):
        super(PseudoState, self).__init__(initial=False, **kargs)

    def _enter_actions(self, sm):
        # overloading _enter_actions will prevent completion events
        # from being generated for PseudoStates
        pass

class IntialState(PseudoState):
    def add_transition(self, t):
        if t.transitions:
            raise Exception('Initial state must have only one transition')
        super(IntialState, self).add_transition(t)

    def accept_transition(self, t):
        raise Exception('Initial state cannot be the target of a transition')

    def get_entry_transitions(self):
        transitions = self.get_enabled_transitions(None)
        if not transitions:
            raise "Ill-formed: no suitable transition from initial state of %s"%state
        return transitions

class Junction(PseudoState):
    pass

class HistoryState(PseudoState):
    pass

class _SinkState(PseudoState):
    def add_transition(self, t):
        raise Exception("%s is a sink, it can't be the source of a transition"%
                        self.__class__.__name__)

    def get_enabled_transitions(self, evt):
        return None
    

class FinalState(_SinkState):
    def _enter_actions(self, sm):
        sm.post_completion(self.parent)
        

class TerminateState(_SinkState):
    def _enter_actions(self, sm):
        sm.stop()

class EntryState(PseudoState):
    pass

class ExitState(PseudoState):
    pass


class TransitionMeta(type):
    def __new__(mcls, name, bases, kwds):
        # register the new Transition if it has an ctor_accepts method
        cls = type.__new__(mcls, name, bases, kwds)
        if 'ctor_accepts' in kwds:
            # later additions override previously known Transition classes.
            Transition._transition_cls.insert(0, cls)
        return cls

class Transition(with_metaclass(TransitionMeta, object)):
    INTERNAL = 'internal'
    EXTERNAL = 'external'
    LOCAL = 'local'
    _ENTRY = 'entry'

    _transition_cls = []    # list of known subclasses

    def __init__(self, trigger=None, action=None, source=None, target=None, 
                 type=LOCAL, desc=None):
        self.trigger = trigger
        self.action = action
        self.source = source
        self.target = target
        self.type = type
        self.desc = desc
        self.hooks = []
        if type is not self._ENTRY:
            if source:
                source.add_transition(self)
            if target:
                target.accept_transition(self)

    def is_triggered(self, evt):
        if self.trigger:
            return self.trigger(evt)
        else:
            return evt is None # Completion event

    def _action(self, sm, evt):
        for hook in self.hooks:
            h, args, kargs = hook
            h(sm, self, evt, *args, **kargs)
        self.do_action(sm, evt)

    def do_action(self, sm, evt):
        self.action and self.action(sm, evt)

    def add_hook(self, hook, *args, **kargs):
        self.hooks.append((hook, args, kargs))

    def __rshift__(self, other):
    #def __gt__(self, other):
        other.accept_transition(self)
        return other

    def __lshift__(self, other):
    #def __lt__(self, other):
        other.add_transition(self)
        return other

    def __str__(self):
        return '%s-%s>%s'%(self.source, 
                           "[%s]-"%self.desc if self.desc else '', 
                           self.target)

    @classmethod
    def make_transition(cls, value, **kargs):
        if isinstance(value, Transition):
            return value
        for cls in cls._transition_cls:
            if cls.ctor_accepts(value, **kargs):
                return cls(value, **kargs)
        else:
            raise Exception("Cannot build a transition using '%r'"%value)

class EqualsTransition(Transition):
    @classmethod
    def ctor_accepts(cls, value, **kargs):
        if not isclass(value):
            return True

    def __init__(self, evt_value, **kargs):
        if 'desc' not in kargs:
            kargs['desc'] = evt_value
        super(EqualsTransition, self).__init__(**kargs)
        self.value = evt_value

    def is_triggered(self, evt):
        return evt is not None and self.value == evt
    

class Timeout(Transition):
    # modify source state to have entry fire a timer, if the timer expires
    # the transition should trigger. Conversely when the state is exited, the
    # timer should be cancelled.
    def __init__(self, delay, **kargs):
        super(Timeout, self).__init(type=Transition.EXTERNAL, **kargs)
        self.delay = delay


class StateMachine:
    MAX_STOP_WAIT = .1

    def __init__(self, cstate, *states):
        if states:
            self._cstate = State()
            self._cstate.add_state(cstate, initial=True)
            for s in states:
                self._cstate.add_state(s)
        else:
            self._cstate = cstate
        self._event_queue = queue.Queue()
        self._completed = set() # set of completed states
        self._sched = sched.scheduler(time.time, time.sleep)
        self._terminated = False
        self._thread = None

    def start(self): 
        if self._thread:
            raise Exception('State Machine already started')
        self._terminated = False
        #self._thread = Thread(target=self._loop, daemon=True)
        self._thread = Thread(target=self._loop)
        self._thread.daemon = True
        self._thread.start()

    def join(self, *args):
        t = self._thread
        if t is not None:
            t.join(*args)
        
    def pause(self): pass
    def stop(self): 
        '''Stops the State Machine.'''
        self._terminated = True

    def post(self, *evts):
        '''Adds an event to the State Machine's input processing queue.'''
        for e in evts:
            self._event_queue.put(e)

    def post_completion(self, state):
        if state is None:
            self._terminated = True
        else:
            LOG.debug('%s - state completed', state)
            self._completed.add(state)

    def assign_depth(self, state=None, depth=0):
        state = state or self._cstate
        state._depth = depth
        for c in state.children:
            self.assign_depth(c, depth + 1)

    def lca(self, a, b):
        '''Returns paths to least common ancestor of states a and b.'''
        if a is b:
            return [a], [b] # LCA found
        if a._depth < b._depth:
            a_path, b_path = self.lca(a, b.parent)
            return a_path, b_path + [b]
        elif b._depth < a._depth:
            a_path, b_path = self.lca(a.parent, b)
            return [a] + a_path, b_path
        else:
            a_path, b_path = self.lca(a.parent, b.parent)
            return [a] + a_path, b_path + [b]

    def _loop(self):
        # assign dept to each state (to assist LCA calculation)
        self.assign_depth()

        # perform entry into the root region/state
        entry_transitions = self._cstate.get_entry_transitions()
        self._step(evt=None, transitions=entry_transitions)

        # loop should:
        # - exit when _terminated is True
        # - sleep for MAX_STOP_WAIT as a time
        # - wakeup when an event is queued
        # - wakeup when a scheduled task needs to be performed
        LOG.debug('%s - beginning event loop', self)
        while not self._terminated:
            try:
                # resolve all completion events in priority
                state = self._completed.pop()
                LOG.debug('%s - handling completion of %s', self, state)
                self._step(evt=None, transitions=state.get_enabled_transitions(None))
                if state.parent:
                    state.parent.child_completed(self, state)
                else:
                    self.stop() # top level region completed.
                continue
            except KeyError:
                pass
            tm_next_sched = self._sched.run(blocking=False)
            delay = self.MAX_STOP_WAIT if tm_next_sched is None \
                    else min(tm_next_sched, self.MAX_STOP_WAIT)
            try:
                evt = self._event_queue.get(True, delay)
                self._step(evt)
            except queue.Empty:
                pass
            LOG.debug('%s - end of loop, remaining events %r',
                      self, self._event_queue.queue)
        self._thread = None

    def _step(self, evt, transitions=None):
        LOG.debug('%s - processing event %r', self, evt)
        if transitions is None:
            transitions = self._cstate.get_enabled_transitions(evt)
        while transitions:
            #t, *transitions = transitions   # 'pop' a transition
            t, transitions = transitions[0], transitions[1:]
            LOG.debug("%s - following transition %s", self, t)
            if t.type is Transition.INTERNAL:
                t._action(self, evt)
                continue
            src = t.source
            tgt = t.target or t.source # if no target is defined, target is self
            s_path, t_path = self.lca(src, tgt) 
            if src is not tgt \
                and t.type is not Transition._ENTRY \
                and isinstance(s_path[-1], ParallelState):
                raise Exception("Error: transition from %s to %s isn't allowed "
                                "because source and target states are in "
                                "orthogonal regions." %
                                (src, tgt))
            if t.type is Transition.EXTERNAL \
                and (len(s_path) == 1 or len(t_path) == 1):
                s_path[-1]._exit(self)
                t_path.insert(0, None)
            elif len(s_path) > 1:
                s_path[-2]._exit(self)

            LOG.debug('%s - performing transition behavior for %s', self, t)
            t._action(self, evt)

            for a,b in [(t_path[i], t_path[i+1]) for i in range(len(t_path) - 1)]:
                if a is not None:
                    a.active_substate = b
                b._enter(self)

            transitions = tgt.get_entry_transitions() + transitions
        LOG.debug("%s - step complete for %r", self, evt)
            
if __name__ == "__main__":
    #s = State()
    #s1 = State('s1', parent=s, initial=True)
    #s2 = State('s2', parent=s)
    #f = FinalState(parent=s)

    #s1 > s2 > Transition(lambda e:True, lambda sm,e:None) > f

    s1 = State('s1')
    s2 = State('s2')
    fs = FinalState()
    
    s0 = State('s0')
    s0.add_state(s1, initial=True)
    s0.add_state(s2)
    s0.add_state(fs)
    sm = StateMachine(s0)
    #sm = fsm.StateMachine(s1, s2, fs)

    s1 > 'a' > s2 > 'b' > fs
# vim:expandtab:sw=4:sts=4
