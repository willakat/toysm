# pylint: disable=unexpected-keyword-arg, no-value-for-parameter,star-args

try:
    # python3
    import queue
except ImportError:
    # python2
    # pylint: disable=import-error
    import Queue as queue
import sched
import time
import subprocess
from inspect import isclass
from threading import Thread
import sys

import logging

from six import with_metaclass

LOG = logging.getLogger(__name__)
DOT = 'dot'
XDOT = 'xdot'

def _bytes(string, enc='utf-8'):
    '''Returns bytes of the string argument. Compatible w/ Python 2
       and 3.'''
    if sys.version_info.major < 3:
        return string
    else:
        return bytes(string, enc)

class DotMixin(object):
    '''Helper for objects that can be represented with Graphviz dot.'''
    def __init__(self):
        super(DotMixin, self).__init__()
        self.dot = self.dot.copy()  # instance specific copy of dot dict

    def dot_attrs(self, **overrides):
        if overrides:
            d = self.dot.copy()
            d.update(overrides)
        else:
            d = self.dot
        def resolve(item):
            k, v = item
            if callable(v):
                v = v(self)
            v = str(v)
            if not(v.startswith('<') and v.endswith('>')):
                v = '"%s"'%v.replace('"', r'\"')
            return k, v
        return ';'.join('%s=%s'%(k, v) for (k, v) in (resolve(i) for i in d.items()))

class State(DotMixin):
    dot = {
        'style': 'rounded',
        'shape': 'rect',
        #'label': lambda s: '<<table border="0" cellborder="1" sides="LR"><tr><td>%s</td></tr></table>>'%s.name or ''
        'label': lambda s: s.name or ''
    }

    def __init__(self, name=None, parent=None, initial=False):
        super(State, self).__init__()
        self.transitions = set()
        self.dflt_transition = None
        self.name = name
        self.initial = None # Initial substate (if any)
        self.children = set()
        self.active_substate = None
        self.hooks = {
            'pre_entry': [],
            'post_entry': [],
            'pre_exit': [],
            'post_exit': [], }
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
        LOG.debug("%s - no transitions found for %r", self, evt)
        return []

    def get_entry_transitions(self):
        if self.children:
            if self.initial:
                # pylint: disable=protected-access
                return [Transition(source=self, target=self.initial,
                                   kind=Transition._ENTRY)]
            else:
                raise "Ill-Formed: no Initial state identified for %s"%self
        else:
            return []

    def child_completed(self, sm, child):
        pass

    def call_hooks(self, sm, kind):
        for hook in self.hooks[kind]:
            h, args, kargs = hook
            h(sm, self, *args, **kargs)

    def on_entry(self, sm):
        pass

    def _enter(self, sm):
        '''Called when a state is entered.
           Not intended to be overriden, subclass specific behavior
           should be implemented in _enter_actions.
        '''
        LOG.debug("%s - Entering state", self)
        self.call_hooks(sm, 'pre_entry')
        self.on_entry(sm)
        self._enter_actions(sm)
        self.call_hooks(sm, 'post_entry')

    def _enter_actions(self, sm):
        if not self.children:
            sm.post_completion(self)

    def on_exit(self, sm):
        pass

    def _exit(self, sm):
        self.call_hooks(sm, 'pre_exit')
        self._exit_actions(sm)
        self.on_exit(sm)
        self.call_hooks(sm, 'post_exit')
        LOG.debug("%s - Exiting state", self)

    def _exit_actions(self, sm):
        if self.active_substate:
            self.active_substate._exit(sm)  # pylint: disable=protected-access
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

    def add_hook(self, kind, hook, *args, **kargs):
        kind = {'entry': 'pre_entry',
                'enter': 'pre_entry',
                'exit' : 'post_exit',}.get(kind, kind)
        self.hooks[kind].append((hook, args, kargs))

    def __str__(self):
        return "{%s%s}"%(self.__class__.__name__,
                         '-%s'%self.name if self.name else '')

    def __rshift__(self, other):
        if isinstance(other, State):
            # Completion transition
            Transition(source=self, target=other)
        else:
            other = Transition.make_transition(other)
            self.add_transition(other)
        return other

    def __lshift__(self, other):
        if isinstance(other, State):
            # Completion transition
            Transition(source=other, target=self)
        else:
            other = Transition.make_transition(other)
            self.accept_transition(other)
        return other


class ParallelState(State):
    def __init__(self, *args, **kargs):
        super(ParallelState, self).__init__(*args, **kargs)
        self._still_running_children = None

    def add_state(self, state, initial=False):
        '''Adds a substate to the state.

           If initial is True, the substate will be considered
           the initial state of the composite state. This is equivalent
           to adding an InitialState with a transition to the substate.
        '''
        if initial:
            raise Exception("When adding to a ParallelState, no region "
                            "can be an 'initial' state")
        if isinstance(state, PseudoState):
            raise Exception("PseudoStates cannot be added to a ParallelState")
        super(ParallelState, self).add_state(state, initial=False)

    def get_enabled_transitions(self, evt):
        '''Returns the list of transitions enable for a given event on
           this state.
        '''
        substate_transitions = []
        for c in self.children:
            substate_transitions += c.get_enabled_transitions(evt)
        if substate_transitions:
            return substate_transitions
        else:
            return self._get_local_enabled_transitions(evt)

    def get_entry_transitions(self):
        '''Returns the list of transitions triggered by entering this state.'''
        #pylint: disable=protected-access 
        return [Transition(source=self, target=c, kind=Transition._ENTRY)
                for c in self.children]

    def child_completed(self, sm, child):
        self._still_running_children.remove(child)
        if not self._still_running_children:
            # All children states/regions have completed
            sm.post_completion(self)

    def _enter_actions(self, sm):
        LOG.debug('pstate children %s', self.children)
        self._still_running_children = set(self.children)

    def _exit_actions(self, sm):
        for c in self.children:
            c._exit(sm)         #pylint: disable=protected-access 

class PseudoState(State):
    def __init__(self, initial=False, **kargs):
        super(PseudoState, self).__init__(initial=False, **kargs)

    def _enter_actions(self, sm):
        # overloading _enter_actions will prevent completion events
        # from being generated for PseudoStates
        pass

class IntialState(PseudoState):
    dot = {
        'label': '',
        'shape': 'circle',
        'style': 'filled',
        'fillcolor': 'black',
        'height': .15,
        'width': .15,
        'margin': 0,
    }
    def add_transition(self, t):
        if t.transitions:
            raise Exception('Initial state must have only one transition')
        super(IntialState, self).add_transition(t)

    def accept_transition(self, t):
        raise Exception('Initial state cannot be the target of a transition')

    #def get_entry_transitions(self):
    #    transitions = self.get_enabled_transitions(None)
    #    if not transitions:
    #        raise "Ill-formed: no suitable transition from initial state of %s"%state
    #    return transitions

class Junction(PseudoState):
    pass

class HistoryState(PseudoState):
    dot = {
        'label': 'H',
        'shape': 'circle',
        'fontsize': 8,
        'height': 0,
        'width': 0,
        'margin': 0,
    }

    def __init__(self, initial=None, **args):
        self._parent = None
        super(HistoryState, self).__init__(initial=False, **args)
        self._saved_state = None

    def add_transition(self, t):
        if self.transitions:
            raise Exception('History state only supports one egress transition')
        super(HistoryState, self).add_transition(t)

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, parent):
        assert self._parent is None
        assert not isinstance(parent, ParallelState)
        self._parent = parent
        parent.add_hook('pre_exit', self.save_state)

    def save_state(self, *_):
        self._saved_state = self._parent.active_substate

    def get_enabled_transitions(self, evt):
        LOG.debug('Enterring history state of %s', self._parent)
        if self._saved_state:
            LOG.debug('Following transition to saved sate %s', self._saved_state)
            #pylint: disable=protected-access 
            return [Transition(source=self, target=self._saved_state,
                               kind=Transition._ENTRY)]
        if self.transitions:
            LOG.debug('Following default transition')
            return list(self.transitions)
        LOG.debug('Using default entry for %s', self._parent)
        return self._parent.get_entry_transitions()


class _SinkState(PseudoState):
    def add_transition(self, t):
        raise Exception("%s is a sink, it can't be the source of a transition"%
                        self.__class__.__name__)

    def get_enabled_transitions(self, evt):
        return None


class FinalState(_SinkState):
    dot = {
        'label': '',
        'shape': 'doublecircle',
        'style': 'filled',
        'fillcolor': 'black',
        'height': .1,
        'width': .1,
        'margin': 0,
    }
    def _enter_actions(self, sm):
        sm.post_completion(self.parent)


class TerminateState(_SinkState):
    dot = {
        'label': 'X',
        'shape': 'none',
        'margin': 0,
        'height': 0,
        'width': 0,
    }
    def _enter_actions(self, sm):
        sm.stop()

class EntryState(PseudoState):
    pass

class ExitState(PseudoState):
    pass


class TransitionMeta(type):
    '''Metaclass for Transitions
       This class is informed when a subclass of Transition is created
       and will update the Transition._transition_cls if the new class
       supports a 'ctor_accepts' method. The latter is used to determine
       which Transition subclass to use when Transition.make_transition
       is called.'''
    def __new__(mcs, name, bases, kwds):
        # register the new Transition if it has an ctor_accepts method
        cls = type.__new__(mcs, name, bases, kwds)
        if 'ctor_accepts' in kwds:
            # later additions override previously known Transition classes.
            #pylint: disable=protected-access
            Transition._transition_cls.insert(0, cls)
        return cls

class Transition(with_metaclass(TransitionMeta, DotMixin)):
    INTERNAL = 'internal'
    EXTERNAL = 'external'
    LOCAL = 'local'
    _ENTRY = 'entry'

    _transition_cls = []    # list of known subclasses

    dot = {
        'label': lambda t: t.desc or '',
    }

    def __init__(self, trigger=None, action=None, source=None, target=None,
                 kind=LOCAL, desc=None):
        self.trigger = trigger
        self.action = action
        self.source = source
        self.target = target
        self.kind = kind
        self.desc = desc
        self.hooks = []
        if kind is not self._ENTRY:
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
        if self.action:
            self.action(sm, evt)

    def add_hook(self, hook, *args, **kargs):
        self.hooks.append((hook, args, kargs))

    def __rshift__(self, other):
        other.accept_transition(self)
        return other

    def __lshift__(self, other):
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
        raise Exception("Cannot build a transition using '%r'"%value)

class EqualsTransition(Transition):
    dot = {
        'label': lambda t: t.value,
    }

    @classmethod
    def ctor_accepts(cls, value, **_):
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
    dot = {
        'label': lambda t: 'after (%ss)'%t.delay,
    }

    def __init__(self, delay, **kargs):
        super(Timeout, self).__init__(kind=Transition.EXTERNAL, **kargs)
        self.delay = delay
        self._sched_id = None
        self._source = None

    @property
    def source(self):
        return self._source

    @source.setter
    def source(self, src):
        if src is None:
            return
        if isinstance(src, PseudoState):
            raise Exception("Cannot apply timeout to pseudostate")
        self._source = src
        src.add_hook('entry', self.schedule)
        src.add_hook('exit', self.cancel)

    def schedule(self, sm, _):
        self._sched_id = \
            sm._sched.enter(                    # pylint: disable = W0212
                self.delay, 10, self.timeout, [sm])  

    def cancel(self, sm, _):
        if self._sched_id:
            sm._sched.cancel(self._sched_id)    # pylint: disable = W0212
            self._sched_id = None

    def timeout(self, sm):
        sm.post(self)
        self._sched_id = None

    def is_triggered(self, evt):
        LOG.debug('timeout triggered: %s, %r %r', self, evt, self._sched_id)
        return self is evt


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
        if sys.version_info.major < 3:
            self._sched = sched.scheduler(time.time, self._sched_wait)
            self._v3sched = False
        else:
            self._sched = sched.scheduler()
            self._v3sched = True
        self._terminated = False
        self._thread = None

    def start(self):
        '''Starts the StateMachine.'''
        if self._thread:
            raise Exception('State Machine already started')
        self._terminated = False
        #self._thread = Thread(target=self._loop, daemon=True)
        self._thread = Thread(target=self._loop)
        self._thread.daemon = True
        self._thread.start()

    def join(self, *args):
        '''Joins the StateMachine internal thread.
           The method will return once the StateMachine has terminated.
        '''
        t = self._thread
        if t is not None:
            t.join(*args)

    def pause(self):
        '''Request the StateMachine to pause.'''
        pass

    def stop(self):
        '''Stops the State Machine.'''
        LOG.debug("%s - Stopping state machine", self)
        self._terminated = True

    def post(self, *evts):
        '''Adds an event to the State Machine's input processing queue.'''
        for e in evts:
            self._event_queue.put(e)

    def post_completion(self, state):
        '''Indicates to the SM that the state has completed.'''
        if state is None:
            self._terminated = True
        else:
            LOG.debug('%s - state completed', state)
            self._completed.add(state)

    def _assign_depth(self, state=None, depth=0):
        '''Assign _depth attribute to states used by the StateMachine.
           Depth is 0 for the root of the graph and each level of
           ancestor between a state and the root adds 1 to its depth.
        '''
        state = state or self._cstate
        state._depth = depth        # pylint: disable = W0212
        for c in state.children:
            self._assign_depth(c, depth + 1)

    def _lca(self, a, b):
        '''Returns paths to least common ancestor of states a and b.'''
        if a is b:
            return [a], [b] # LCA found
        if a._depth < b._depth:     # pylint: disable = W0212
            a_path, b_path = self._lca(a, b.parent)
            return a_path, b_path + [b]
        elif b._depth < a._depth:   # pylint: disable = W0212
            a_path, b_path = self._lca(a.parent, b)
            return [a] + a_path, b_path
        else:
            a_path, b_path = self._lca(a.parent, b.parent)
            return [a] + a_path, b_path + [b]

    def _sched_wait(self, delay):
        '''Waits for next scheduled event all the while processing
           potential external events posted to the SM.

           This method is used with the python2 scheduler that
           doesn't support the non-blocking call to run().'''
        t_wakeup = time.time() + delay
        while not self._terminated:
            t = time.time()
            if t >= t_wakeup:
                break
            # resolve all completion events in priority
            self._process_completion_events()
            self._process_next_event(t_wakeup)

    def _process_completion_events(self):
        '''Processes all available completion events.'''
        while not self._terminated and self._completed:
            state = self._completed.pop()
            LOG.debug('%s - handling completion of %s', self, state)
            self._step(evt=None, transitions=state.get_enabled_transitions(None))
            if state.parent:
                state.parent.child_completed(self, state)
            else:
                state._exit(self)   #pylint: disable=protected-access
                self.stop() # top level region completed.

    def _process_next_event(self, t_max=None):
        '''Process events posted to the SM until a specified time.'''
        while not self._terminated:
            try:
                if t_max:
                    t = time.time()
                    if t >= t_max:
                        break
                    else:
                        delay = min(t_max - t, self.MAX_STOP_WAIT)
                else:
                    delay = self.MAX_STOP_WAIT
                evt = self._event_queue.get(True, delay)
                self._step(evt)
                break
            except queue.Empty:
                continue

    def _loop(self):
        # assign dept to each state (to assist LCA calculation)
        self._assign_depth()

        # perform entry into the root region/state
        self._cstate._enter(self)       # pylint: disable = W0212
        entry_transitions = self._cstate.get_entry_transitions()
        self._step(evt=None, transitions=entry_transitions)

        # loop should:
        # - exit when _terminated is True
        # - sleep for MAX_STOP_WAIT at a time
        # - wakeup when an event is queued
        # - wakeup when a scheduled task needs to be performed
        LOG.debug('%s - beginning event loop', self)
        while not self._terminated:
            # resolve all completion events in priority
            self._process_completion_events()
            if self._v3sched:
                tm_next_sched = self._sched.run(blocking=False)
                if tm_next_sched:
                    tm_next_sched += time.time()
                self._process_next_event(tm_next_sched)
            else:
                if not self._sched.empty():
                    self._sched.run()
                else:
                    self._process_next_event()
            LOG.debug('%s - end of loop, remaining events %r',
                      self, self._event_queue.queue)
        self._thread = None

    def _step(self, evt, transitions=None):
        LOG.debug('%s - processing event %r', self, evt)
        if transitions is None:
            transitions = self._cstate.get_enabled_transitions(evt)
        while transitions:
            #pylint: disable=protected-access
            #t, *transitions = transitions   # 'pop' a transition
            t, transitions = transitions[0], transitions[1:]
            LOG.debug("%s - following transition %s", self, t)
            if t.kind is Transition.INTERNAL:
                t._action(self, evt)    # pylint: disable = W0212
                continue
            src = t.source
            tgt = t.target or t.source # if no target is defined, target is self
            s_path, t_path = self._lca(src, tgt)
            if src is not tgt \
                and t.kind is not Transition._ENTRY \
                and isinstance(s_path[-1], ParallelState):
                raise Exception("Error: transition from %s to %s isn't allowed "
                                "because source and target states are in "
                                "orthogonal regions." %
                                (src, tgt))
            if t.kind is Transition.EXTERNAL \
                and (len(s_path) == 1 or len(t_path) == 1):
                s_path[-1]._exit(self)
                t_path.insert(0, None)
            elif len(s_path) > 1:
                s_path[-2]._exit(self)

            LOG.debug('%s - performing transition behavior for %s', self, t)
            t._action(self, evt)

            for a, b in [(t_path[i], t_path[i+1]) for i in range(len(t_path) - 1)]:
                if a is not None:
                    a.active_substate = b
                b._enter(self)

            transitions = tgt.get_entry_transitions() + transitions
        LOG.debug("%s - step complete for %r", self, evt)

    def graph(self, fname=None, fmt=None, prg=None):
        '''Generates a graph of the State Machine.'''

        def write_node(stream, state, transitions=None):
            transitions.extend(state.transitions)
            if state.parent and isinstance(state.parent, ParallelState):
                attrs = state.dot_attrs(shape='box', style='dashed')
            else:
                attrs = state.dot_attrs()
            if state.children:
                stream.write(_bytes('subgraph cluster_%s {\n'%id(state)))
                stream.write(_bytes(attrs + "\n"))
                if state.initial and not isinstance(state.initial, IntialState):
                    i = IntialState()
                    write_node(stream, i, transitions)
                    # pylint: disable = protected-access
                    transitions.append(Transition(source=i, target=state.initial,
                                                  kind=Transition._ENTRY))

                for c in state.children:
                    write_node(stream, c, transitions)
                stream.write(b'}\n')
            else:
                stream.write(_bytes('%s [%s]\n'% (id(state), attrs)))

        def find_endpoint_for(node):
            if node.children:
                if node.initial:
                    node = node.initial
                else:
                    node = list(node.children)[0]
                return find_endpoint_for(node)
            else:
                return id(node)

        if fname:
            cmd = "%s -T%s > %s"%(prg or DOT, fmt or 'svg', fname)
        else:
            cmd = prg or XDOT

        # Go through all states and generate dot to create the graph
        #with subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE) as proc:
        proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE)
        try:
            f = proc.stdin
            transitions = []
            f.write(b"digraph { compound=true\n")
            write_node(f, self._cstate, transitions=transitions)
            for t in transitions:
                src, tgt = t.source, t.target or t.source
                attrs = {}
                if src.children:
                    attrs['ltail'] = "cluster_%s"%id(src)
                src = find_endpoint_for(src)
                if tgt.children:
                    attrs['lhead'] = "cluster_%s"%id(tgt)
                tgt = find_endpoint_for(tgt)
                f.write(_bytes('%s -> %s [%s]\n'%(src, tgt, t.dot_attrs(**attrs))))
            f.write(b"}")
            f.close()
        finally:
            proc.wait()


if __name__ == "__main__":
    #s = State()
    #s1 = State('s1', parent=s, initial=True)
    #s2 = State('s2', parent=s)
    #f = FinalState(parent=s)

    #s1 > s2 > Transition(lambda e:True, lambda sm,e:None) > f

    state_s1 = State('s1')
    state_s2 = ParallelState('s2')
    state_fs = FinalState()

    state_s21 = State('s21', parent=state_s2)
    state_s22 = State('s22', parent=state_s2)

    state_s211 = State('s211', parent=state_s21, initial=True)
    state_s221 = State('s221', parent=state_s22, initial=True)

    state_s0 = State('s0')
    state_h = HistoryState(parent=state_s0)
    state_s0.add_state(state_s1, initial=True)
    state_s0.add_state(state_s2)
    state_s0.add_state(state_fs)
    state_machine = StateMachine(state_s0)
    #sm = fsm.StateMachine(s1, s2, fs)


    state_s1 >> 'a' >> state_s2 >> 'b' >> state_fs

    state_s1 >> Timeout(10) >> state_fs

    state_machine.graph()
# vim:expandtab:sw=4:sts=4
