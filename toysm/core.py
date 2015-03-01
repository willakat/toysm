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

# pylint: disable=unexpected-keyword-arg, no-value-for-parameter,star-args
# pylint: disable=invalid-name

from threading import Thread, Event
from inspect import isclass
from six import with_metaclass
from toysm.public import public
import logging
LOG = logging.getLogger(__name__)

@public
class IllFormedException(Exception):
    '''Exception raised when a statemachine violates well-formedness rules.

       Ideally the Exception's message should give additional details
       on the nature of the problem...
    '''
    pass

class _StateDescriptor(object):
    '''Holder for the dynamic components of a State.'''
    def __init__(self, copy=None):
        self.active_substate = None
        self.do_thread = None
        self.exit_required = None
        self.activity_complete = True
        if copy:
            self.active_substate = copy.active_substate

@public
class State(object):
    '''State in a StateMachine.'''
    dot = {
        'style': 'rounded',
        'shape': 'rect',
        #'label': lambda s: '<<table border="0" cellborder="1" sides="LR">'
        #                   '<tr><td>%s</td></tr></table>>'%s.name or ''
        'label': lambda s: s.name or ''
    }

    # Factory method that yields a holder for the dynamic part of the State.
    _descriptor_type = _StateDescriptor

    def __init__(self, name=None, sexp=None, parent=None, initial=False,
                 on_enter=None, on_exit=None, do=None):
        '''
        Parameters:
        name      A name for the state

        sexp      A State expression. All the states present in the expression
                  will be added as childred of this State. The first state
                  in the expression will be considered the initial state.

        parent    Parent of this state.

        initial   when parent is also used, then this State will be
                  the initial state of the parent.

        on_enter  function called whenever the state is entered. The
                  the following arguments (sm, state) where sm is the
                  current StateMachine and state is the State being
                  entered.

        on_exit   function called whenever the state is exited. The same
                  arguments are passed into the function as with on_enter.

        do        function representing the do-activity of this state,
                  it will be run on deidicated thread. the function is called
                  with the following arguments (sm, state, event),
                  where sm and state are as in on_enter. The event argument
                  is an Event object that will be set if the StateMachine needs
                  to exit the state. It can therefore be used to wait on
                  in the function without blocking the StateMachine.
                  The function should return a 'True' value if it needs
                  to be called repetitively (loop). As soon as any 'False'
                  value is returned, the do-activity is considered complete.
        '''
        super(State, self).__init__()
        self.transitions = []
        self.name = name
        self.initial = None # Initial substate (if any)
        self.children = set()
        self.hooks = {
            'pre_entry': [],
            'post_entry': [],
            'pre_exit': [],
            'post_exit': [], }
        self.parent = None
        if parent:
            self.set_parent(parent, initial=initial)
        if sexp:
            sexp.set_parent(self, initial=True)
        if on_enter:
            self.add_hook('pre_entry', on_enter)
        if on_exit:
            self.add_hook('post_exit', on_exit)
        self.do_activity = do
        if do:
            self.add_hook('post_entry', self.start_do_activity)
            self.add_hook('pre_exit', self.stop_do_activity)

    def get_enabled_transitions(self, sm, evt):
        '''Return transitions from the state for the given event, or None
           for states that are never the source of transition (e.g.
           TerminateState and FinalState).'''
        LOG.debug("%s - get_enabled_transitions for %r", self, evt)
        # children transitions have a higher priority
        if evt:
            active_substate = sm.retrieve_state(self).active_substate
            if active_substate:
                substate_transitions = \
                    active_substate.get_enabled_transitions(sm, evt)
                if substate_transitions:
                    return substate_transitions

        # No enabled children transitions, try those defined for this state.
        return self._get_local_enabled_transitions(sm, evt)

    def _get_local_enabled_transitions(self, sm, evt):
        '''Return transitions for event with this state as source.'''
        transitions = []
        for t in self.transitions:
            if t._is_triggered(sm, evt):  #pylint: disable=protected-access
                LOG.debug('%s - transition triggered by event %r: %s',
                          self, evt, t)
                transitions = [t]
                if t.kind is Transition.INTERNAL:
                    break
                tgt = t.target or self
                allowed, entry_transitions = tgt.get_entry_transitions(sm)
                if allowed:
                    transitions += entry_transitions
                    break
        else:
            LOG.debug("%s - no transitions found for %r", self, evt)
        return transitions


    def get_entry_transitions(self, sm):
        '''Return a list of transitions triggered by enterring this state.'''
        if self.children:
            if self.initial:
                # pylint: disable=protected-access
                _, transitions = self.initial.get_entry_transitions(sm)
                return True, [Transition(source=self, target=self.initial,
                                         kind=Transition._ENTRY)] + transitions
            else:
                raise IllFormedException("No Initial state identified for %s"
                                         % self)
        else:
            return True, []

    def child_completed(self, sm, child):
        '''Called when this state's active substate (if any) completes.'''
        pass

    def _call_hooks(self, sm, kind):
        '''Calls the hooks registered for 'kind'.'''
        if LOG.isEnabledFor(logging.DEBUG) and self.hooks[kind]:
            LOG.debug("%s - calling %s hooks", self, kind)
        for hook in self.hooks[kind]:
            LOG.debug(hook)
            h, args, kargs = hook
            h(sm, self, *args, **kargs)

    def on_entry(self, sm):
        '''Called when the state is entered.
           This method is designed to be overriden to provide entry
           customizaiton.
        '''
        pass

    def _enter(self, sm):
        '''Called when a state is entered.
           Not intended to be overriden, subclass specific behavior
           should be implemented in _enter_actions.
        '''
        LOG.debug("%s - Entering state", self)
        self._call_hooks(sm, 'pre_entry')
        self.on_entry(sm)
        self._enter_actions(sm)
        self._call_hooks(sm, 'post_entry')

    def _enter_actions(self, sm):
        '''Performs class specific actions on state entry.
           Called by the _enter method.
           This method is intended to be overriden for state
           specificities.
        '''
        if not (self.children or self.do_activity):
            self._check_completion(sm)

    def _check_completion(self, sm):
        '''Posts a completion event if the State is considered
           to have completed, i.e. if a do-activity is defined
           then it has completed.'''
        if sm.retrieve_state(self).activity_complete:
            sm.post_completion(self)

    def on_exit(self, sm):
        '''Called when the state is exited.
           This method is designed to be overriden to provide exit
           customization.
        '''
        pass

    def _exit(self, sm):
        '''Called when the StateMachine leaves this state.
           Not intended to be overriden, subclass specific
           behavior should be implemented in _exit_actions.
        '''
        self._call_hooks(sm, 'pre_exit')
        self._exit_actions(sm)
        self.on_exit(sm)
        self._call_hooks(sm, 'post_exit')
        LOG.debug("%s - Exiting state", self)

    def _exit_actions(self, sm):
        '''Perform custom actions for a state when the
           StateMachine moves out of this state.
        '''
        desc = sm.retrieve_state(self)
        active_substate = desc.active_substate
        if active_substate:
            active_substate._exit(sm)  # pylint: disable=protected-access

    def start_do_activity(self, sm, _):
        '''Start the State's do-activity thread.'''
        do_activity = self.do_activity
        desc = sm.retrieve_state(self)
        desc.activity_complete = False
        exit_required = desc.exit_required = Event()
        def do():
            '''target for the do-activity Thread.'''
            while not exit_required.is_set():
                if not do_activity(sm, self, exit_required):
                    desc.activity_complete = True
                    self._check_completion(sm)
                    break
            desc.do_thread = None
        desc.do_thread = Thread(target=do)
        LOG.debug("%s - Starting do-activity", self)
        desc.do_thread.start()

    def stop_do_activity(self, sm, _):
        '''Stop the State's do-activity thread.'''
        desc = sm.retrieve_state(self)
        do_thread = desc.do_thread
        if do_thread:
            LOG.debug("%s - Waiting for do-activity to exit", self)
            desc.exit_required.set()
            do_thread.join()

    def add_transition(self, t):
        '''Sets this state as the source of Transition t.'''
        if t.source is not None:
            raise IllFormedException('Transition %s cannot be added to %s '
                                     'because it already has a source'
                                     % (t, self))
        t.source = self
        self.transitions.append(t)

    def accept_transition(self, t):
        '''Called when a transition designates the state as its target.'''
        t.target = self

    def accept_parent(self, parent, initial):
        '''Called when this state's parent is set.'''
        pass

    def accept_substate(self, state, initial):
        '''Called when a substate is added to the state.'''
        pass

    def add_state(self, sexp, initial=False):
        '''Adds a substate or state expression to the state.

           If initial is True, the substate will be considered
           the initial state of the composite state. This is equivalent
           to adding an InitialState with a transition to the substate.
        '''
        sexp.set_parent(self, initial=initial)

    def set_parent(self, state, initial=False):
        '''Set this state's parent.'''
        self._connect_substate(state, self, initial=initial)

    @staticmethod
    def _connect_substate(parent, substate, initial=False):
        '''Connects a parent state to a substate.'''
        if not (substate.parent is None or substate.parent is parent):
            raise IllFormedException('State %s already has a parent' % substate)

        parent.accept_substate(substate, initial=initial)
        substate.accept_parent(parent, initial=initial)

        parent.children.add(substate)
        substate.parent = parent
        if isinstance(substate, InitialState) or initial:
            if not (parent.initial is None or parent.initial is substate):
                raise IllFormedException('State %s already has an initial state'
                                         % parent)
            parent.initial = substate

    def add_hook(self, kind, hook, *args, **kargs):
        '''Add a hook that will be called whenever <kind> action occurs for
           this state. <kind> can be one of 'entry, enter, exit' or
           one of 'pre_entry, post_entry, pre_exit, post_exit' for more
           specific requirements.
        '''
        kind = {'entry': 'pre_entry',
                'enter': 'pre_entry',
                'exit' : 'post_exit',}.get(kind, kind)
        self.hooks[kind].append((hook, args, kargs))

    def set_active_substate(self, sm, state):
        '''Set this state's active substate.'''
        assert not isinstance(state, PseudoState), \
            'PseudoStates cannot be active substates'
        sm.retrieve_state(self).active_substate = state

    def get_active_states(self, sm):
        '''Return an iterator over the active substates of the State
           the method is called on. The result will include the State
           itself.
        '''
        desc = sm.retrieve_state(self)
        yield (self, self._descriptor_type(desc))
        if desc.active_substate:
            for i in desc.active_substate.get_active_states(sm):
                yield i

    def restore_state(self, sm, saved):
        '''Restore the State to a previously saved condition.
           This saved condition can be obtained by a call
           to State.get_active_states.
        '''
        sm.store_state(self, saved)

    def __str__(self):
        return "{%s%s}" % (self.__class__.__name__,
                           '-%s' % self.name if self.name else '')

    def __rshift__(self, other):
        return _StateExpression(self) >> other

    def __lshift__(self, other):
        return _StateExpression(self) << other


class _ParallelStateDescriptor(_StateDescriptor):
    '''Holder for the dynamic components of a State.'''
    def __init__(self, copy=None):
        super(_ParallelStateDescriptor, self).__init__()
        del self.active_substate
        if copy:
            self.still_running_children = copy.still_running_children.copy()

@public
class ParallelState(State):
    '''State containing several "parallel" regions that execute
       independently.
    '''

    _descriptor_type = _ParallelStateDescriptor

    def __init__(self, *args, **kargs):
        super(ParallelState, self).__init__(*args, **kargs)
        self._history = set()

    def accept_substate(self, state, initial):
        if initial:
            raise IllFormedException("When adding to a ParallelState, no "
                                     "region can be an 'initial' state")
        if isinstance(state, PseudoState):
            if isinstance(state, DeepHistoryState):
                self._history.add(state)
            else:
                raise IllFormedException("PseudoStates cannot be added to a "
                                         "ParallelState")

    def get_enabled_transitions(self, sm, evt):
        substate_transitions = []
        still_running_children = sm.retrieve_state(self).still_running_children
        for c in still_running_children:
            substate_transitions += c.get_enabled_transitions(sm, evt)
        if substate_transitions:
            return substate_transitions
        else:
            return self._get_local_enabled_transitions(sm, evt)

    def get_entry_transitions(self, sm):
        '''Returns the list of transitions triggered by entering this state.'''
        #pylint: disable=protected-access
        transitions = []
        for c in self.children - self._history:
            transitions.append(Transition(source=self, target=c,
                                          kind=Transition._ENTRY))
            _, entry_transitions = c.get_entry_transitions(sm)
            transitions.extend(entry_transitions)
        return True, transitions

    def child_completed(self, sm, child):
        sm.retrieve_state(self).still_running_children.remove(child)
        self._check_completion(sm)

    def _check_completion(self, sm):
        # All children states/regions have completed
        if not sm.retrieve_state(self).still_running_children:
            super(ParallelState, self)._check_completion(sm)

    def _enter_actions(self, sm):
        sm.retrieve_state(self).still_running_children = \
            self.children - self._history

    def _exit_actions(self, sm):
        for c in self.children - self._history:
            c._exit(sm)         #pylint: disable=protected-access

    def get_active_states(self, sm):
        desc = sm.retrieve_state(self)
        still_running_children = desc.still_running_children
        yield (self, self._descriptor_type(desc))
        for i in still_running_children:
            for j in i.get_active_states(sm):
                yield j

    def set_active_substate(self, sm, state):
        pass
        #assert False, "Internal error: can't set active substate on Parallel state"


@public
class PseudoState(State):
    '''Superclass of all PseudoStates.'''

    dot = {
        'label': '',
        'shape': 'circle',
        'style': 'filled',
        'fillcolor': 'black',
        'height': .15,
        'width': .15,
        'margin': 0,
    }

    # Mask _descriptor_type from State (no do-activities or substates)
    _descriptor_type = None

    #specifies whether the PseudoState is allowed to be the terminal
    #node in a (potentially compound) transition.
    transition_terminal = False

    def __init__(self, name=None, initial=False, **kargs):
        if 'do' in kargs:
            raise IllFormedException('PseudoStates may not have a "do" action.')
        super(PseudoState, self).__init__(name=name, initial=False, **kargs)

    def _enter_actions(self, sm):
        # overloading _enter_actions will prevent completion events
        # from being generated for PseudoStates
        pass

    def _exit_actions(self, sm):
        pass

    def get_enabled_transitions(self, sm, evt):
        assert False, "PseudoStates cannot have transitions with " \
               "trigger conditions"

    def get_entry_transitions(self, sm):
        allowed, transitions = self.transition_terminal, []
        for t in self.transitions:
            if t._is_triggered(sm, None):  #pylint: disable=protected-access
                allowed, compound_transition = \
                    t.target.get_entry_transitions(sm)
                if allowed:
                    transitions.append(t)
                    transitions += compound_transition
                    break
        return allowed, transitions

    def set_active_substate(self, sm, state):
        assert False, "set_substate called on PseudoState"


@public
class InitialState(PseudoState):
    '''PseudoState that designates the 'initial' substate of a composite
       state.
    '''
    def add_transition(self, t):
        if self.transitions:
            raise IllFormedException('Initial state must have only one '
                                     'transition')
        super(InitialState, self).add_transition(t)

    def accept_transition(self, t):
        raise IllFormedException('Initial state cannot be the target of a '
                                 'transition')

    def get_entry_transitions(self, sm):
        allowed, transitions = \
            super(InitialState, self).get_entry_transitions(sm)
        if not (allowed and transitions):
            raise IllFormedException("No suitable transition from initial "
                                     "state of %s" % self.parent)
        return True, transitions

@public
class Junction(PseudoState):
    '''PseudoState that allows multiple transitions to be stringed together.'''
    pass


@public
class HistoryState(PseudoState):
    '''PseudoState that saves the current substate of a composite state
       and allows it to be directly re-entered.
    '''
    dot = {
        'label': 'H',
        'shape': 'circle',
        'fontsize': 8,
        'height': 0,
        'width': 0,
        'margin': 0,
    }

    def __init__(self, initial=None, **args):
        super(HistoryState, self).__init__(initial=False, **args)

    def add_transition(self, t):
        if self.transitions:
            raise IllFormedException('History state only supports one egress '
                                     'transition')
        super(HistoryState, self).add_transition(t)


    def accept_parent(self, parent, initial):
        if isinstance(parent, ParallelState):
            raise IllFormedException("Shallow History state parent cannot be a "
                                     "ParallelState")
        if initial:
            raise IllFormedException("History state cannot be an initial state")
        parent.add_hook('pre_exit', self.save_state)

    def save_state(self, sm, *_):
        '''Callback when the HistoryState's parent state is exited.'''
        sm.store_state(self, sm.retrieve_state(self.parent).active_substate)

    def get_entry_transitions(self, sm):
        LOG.debug('Entering history state of %s', self.parent)
        saved = sm.retrieve_state(self)
        if saved:
            LOG.debug('%s - Following transition to saved sate %s',
                      self, saved)
            _, saved_state_entry_transitions = saved.get_entry_transitions(sm)
            #pylint: disable=protected-access
            return True, [Transition(source=self, target=saved,
                                     kind=Transition._ENTRY)] \
                         + saved_state_entry_transitions
        if self.transitions:
            LOG.debug('%s - Following default transition', self)
            return True, self.transitions
        LOG.debug('%s - Using default entry for %s', self, self.parent)
        return self.parent.get_entry_transitions(sm)

@public
class DeepHistoryState(HistoryState):
    '''PseudoState that keeps is able to restore its parent state
       to the way it was when it was previously exited. This
       history includes the state of all the recursive substates
       of the parent.
    '''
    dot = HistoryState.dot.copy()
    dot['label'] = 'H*'

    def accept_parent(self, parent, initial):
        if initial:
            raise IllFormedException("History state cannot be an initial state")
        parent.add_hook('pre_exit', self.save_state)

    def save_state(self, sm, *_):
        sm.store_state(self, list(self.parent.get_active_states(sm)))

    def get_entry_transitions(self, sm):
        LOG.debug('Entering deep history state of %s', self.parent)
        saved = sm.retrieve_state(self)
        if saved:
            LOG.debug('%s - Following transition to saved state %s',
                      self, saved)
            return True, []
        if self.transitions:
            LOG.debug('%s - Following default transition', self)
            return True, self.transitions
        LOG.debug('%s - Using default entry for %s', self, self.parent)
        return self.parent.get_entry_transitions(sm)

    def _enter_actions(self, sm):
        #pylint: disable=protected-access
        saved = sm.retrieve_state(self)
        if saved:
            self.parent.restore_state(sm, saved[0][1])
            for (s, _) in saved[1:]:
                # sm already has the saved states, all we need to
                # do here is re-enter all of them.
                #s.restore_state(sm, desc)
                s._enter(sm)


class _SinkState(PseudoState):
    '''PseudoState that forbids adding egress transitions.'''
    transition_terminal = True

    def add_transition(self, t):
        raise IllFormedException(
            "%s is a sink, it can't be the source of a transition" %
            self.__class__.__name__)


@public
class FinalState(_SinkState):
    '''PseudoState that causes its parent state/region to complete.'''
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


@public
class TerminateState(_SinkState):
    '''PseudoState that causes the StateMachine to stop.'''
    dot = {
        'label': 'X',
        'shape': 'none',
        'margin': 0,
        'height': 0,
        'width': 0,
    }
    def _enter_actions(self, sm):
        sm.stop()

@public
class EntryState(Junction):
    pass

@public
class ExitState(Junction):
    pass


class _StateExpression(object):
    '''Class used to simplify stitching together states and transitions.

       A(s1): produces a builder containing a single state
       A << s2, results in a builder with a
    '''

    def __init__(self, state=None):
        states = self.states = set()
        if state:
            states.add(state)
        self.head = self.tail = self.initial = state

    def set_parent(self, state, initial=False):
        '''Set the parent state of all states in the expression.'''
        if isinstance(self.tail, Transition) \
            or isinstance(self.head, Transition):
            raise IllFormedException('State expressions must not begin/end with'
                                     ' a transition.')
        for s in self.states:
            s.set_parent(state, initial=initial and self.initial is s)

    def add_state(self, state):
        '''Add a state to the expression.'''
        if state not in self.states:
            self.states.add(state)
            if isinstance(state, InitialState):
                if isinstance(self.initial, InitialState):
                    raise IllFormedException('Cannot have multiple initial '
                                             'states.')
                self.initial = state

    def connect(self, a, b):
        '''Connects a and b where a or b can be either a State or
           a Transition.
        '''
        def prep(e):
            '''Take appropriate action based on e's type
               for the connection to be performed.
            '''
            if isinstance(e, State):
                self.add_state(e)
            else:
                e = Transition.make_transition(e)
            return e
        a, b = prep(a), prep(b)
        if isinstance(a, State):
            if isinstance(b, State):
                # Completion transition
                CompletionTransition(source=a, target=b)
            else:
                a.add_transition(b)
        elif isinstance(b, State):
            b.accept_transition(a)
        else:
            raise IllFormedException('Cannot connect a transition to another')
        return a, b

    def __rshift__(self, other):
        if isinstance(other, _StateExpression):
            for s in other.states:
                self.add_state(s)
            self.connect(self.tail, other.head)
            self.tail = other.tail
        else:
            _, self.tail = self.connect(self.tail, other)
        return self

    def __lshift__(self, other):
        if isinstance(other, _StateExpression):
            for s in other.states:
                self.add_state(s)
            self.connect(other.head, self.tail)
            self.tail = other.tail
        else:
            self.tail, _ = self.connect(other, self.tail)
        return self

################################################################################
#
## Transitions ##
#
################################################################################

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

@public
class Transition(with_metaclass(TransitionMeta)):
    '''Tranistion in a StateMachine.

       Transitions have the following attributes:
       - source [mandatory]
       - target [optional] (can be None if the transition loops back to the
                source)
       - trigger a callable that returns a boolean indicating whether
                 or not a given event should trigger the transition.
       - action [optional] a callable that is called whenever the transition
                is followed.
       - kind   [optional], defaults to LOCAL.
                INTERNAL transitions do not cause a state change when they
                         are followed
                EXTERNAL always cause the on_entry/on_exit of their
                        targets/sources to be called when the transition is
                        followed,
                LOCAL    default type of transition, on_enter/on_exit are only
                         called when the target/source node isn't a substate/
                         superstate.
    '''
    INTERNAL = 'internal'
    EXTERNAL = 'external'
    LOCAL = 'local'
    _ENTRY = 'entry'

    _transition_cls = []    # list of known subclasses

    dot = {
        'label': lambda t: t.desc
    }

    def __init__(self, trigger=None, action=None, source=None, target=None,
                 kind=LOCAL, desc=''):
        self.trigger = trigger
        self.action = action
        self.kind = kind
        self.desc = desc
        self.hooks = []
        if kind is not self._ENTRY:
            self.source = self.target = None
            if source:
                source.add_transition(self)
            if target:
                target.accept_transition(self)
        else:
            if kind is self.INTERNAL and target is not None:
                raise IllFormedException('INTERNAL Transitions cannot '
                                         'have a target')
            self.source = source
            self.target = target

    def is_triggered(self, sm, evt):
        '''Returns a boolean indicating if the transition should be
           enabled for the evt event.

           This method is intended to be overridden by subclasses.
        '''
        #pylint: disable=unused-argument, no-self-use
        return evt is not None  # Not a completion event (Completion events
                                # are recognized by CompletionTransition.

    def _is_triggered(self, sm, evt):
        '''Called to determine if the transition is enabled for the <evt>
           event.
        '''
        if self.trigger:
            triggered = self.is_triggered(sm, evt) and self.trigger(sm, evt)
        else:
            triggered = self.is_triggered(sm, evt)
        LOG.debug('Evaluating transition %s for event %s: %s',
                  self, evt, triggered)
        return triggered


    def _action(self, sm, evt):
        '''Called when the StateMachine follows this transition.'''
        for hook in self.hooks:
            h, args, kargs = hook
            h(sm, self, evt, *args, **kargs)
        self.do_action(sm, evt)

    def do_action(self, sm, evt):
        '''Called when this transtion is followed.'''
        if self.action:
            self.action(sm, evt)

    def add_hook(self, hook, *args, **kargs):
        '''Add a hook that will be called when this transition is followed.'''
        self.hooks.append((hook, args, kargs))

    def __str__(self):
        return '%s-%s>%s' % (self.source,
                             "[%s]-" % self.desc if self.desc else '',
                             self.target)

    @classmethod
    def make_transition(cls, value, **kargs):
        '''Produce a Transition object based on the <value>.

           kargs will be passed into the constructor of the Transition
           (assuming a constructor needs to be called, e.g. when value
           isn't already a Transition).
        '''
        if isinstance(value, Transition):
            return value
        for cls in cls._transition_cls:
            if cls.ctor_accepts(value, **kargs):
                return cls(value, **kargs)
        raise IllFormedException("Cannot build a transition using '%r'" %
                                 value)

@public
class CompletionTransition(Transition):
    '''Special Transition used to indicate that the Transition should
       trigger when its source State completes.
       Note that a Completion can nevertheless have a trigger condition,
       this trigger should however not expect <evt> to be anything else
       than None.
    '''
    def is_triggered(self, sm, evt):
        return evt is None

@public
class EqualsTransition(Transition):
    '''Simple Transition type that checks events against a
       pre-defined value.
    '''
    @classmethod
    def ctor_accepts(cls, value, **_):
        '''Constructor accepts any value as long as it isn't a class.'''
        if not isclass(value):
            return True

    def __init__(self, evt_value, desc=None, **kargs):
        desc = '%s' % evt_value + ('/%s' % desc if desc else '')
        super(EqualsTransition, self).__init__(desc=desc, **kargs)
        self.value = evt_value

    def is_triggered(self, sm, evt):
        return evt is not None and self.value == evt


@public
class Timeout(Transition):
    '''Transition that will trigger if the source state isn't exited
       within a certain delay.
    '''

    def __init__(self, delay, desc=None, **kargs):
        desc = 'after (%ss)' % delay + ('/%s' % desc if desc else '')
        super(Timeout, self).__init__(kind=Transition.EXTERNAL, desc=desc,
                                      **kargs)
        self.delay = delay
        self._sched_id = None
        self._source = None

    @property
    def source(self):
        '''Source of the transition is a property.
           This allows the a hook to be placed on the
           source state when it is set.
        '''
        return self._source

    @source.setter
    def source(self, src):
        '''Adds entry/exit hooks to the source of the transition
           when it is set.
        '''
        if src is None:
            return
        if isinstance(src, PseudoState):
            raise Exception("Cannot apply timeout to pseudostate")
        self._source = src
        src.add_hook('entry', self._schedule)
        src.add_hook('exit', self._cancel)

    def _schedule(self, sm, _):
        '''Enterring the source state causes a call to _timeout
           to be schedule.
        '''
        self._sched_id = \
            sm._sched.enter(                    # pylint: disable = W0212
                self.delay, 10, self._timeout, [sm])

    def _cancel(self, sm, _):
        '''Exiting the source state cancels the timer that was
           started on entry.
        '''
        if self._sched_id:
            sm._sched.cancel(self._sched_id)    # pylint: disable = W0212
            self._sched_id = None

    def _timeout(self, sm):
        '''Called back when the timer expires, an event
           is posted to the StateMachine that will trigger the
           Timeout transition.
        '''
        sm.post(self)
        self._sched_id = None

    def is_triggered(self, sm, evt):
        LOG.debug('timeout triggered: %s, %r %r', self, evt, self._sched_id)
        return self is evt

# vim:expandtab:sw=4:sts=4
