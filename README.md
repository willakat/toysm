ToySM is a small pure Python implementation of [UML2-like] [1] statemachine
semantics .

List of features supported in ToySM
-----------------------------------
* UML2 features:
  - Hierarchical states
  - enter/exit/do activities
  - Orthogonal regions (ParallelStates)
  - Transitions and Compound Transitions
  - Pseudostates
  	- InitialStates
	- FinalStates
	- TerminateStates
	- Junction
	- Shallow and Deep History states
  - Timeouts (akin to TimeEvents)

* Graphic representation

* Simple syntax to assemble States and Transition into a StateMachine

* Compatible with Python2 and Python3

* Integration with [Scapy] [2]
  - PacketTransition to use Scapy packets as transition
    trigger events.
  - SMBox for use with Scapy Pipes (requires Scapy 2.2.0-dev)


What's still missing
--------------------
* UML2
  - Choice PseudoState
  - Representation of Exit/Enter PseudoStates
  - Fork and Join PseudoStates
  - Event deferral

* Better graphing for Hierarchical states

* StateMachine Pause function

* Documentation :-)


Dependencies
------------
- [Graphviz] [3]: to produce visual representations of StateMachines
- [xdot] [4]: direct graph rendering instead of rendering to file
- [six] [5]: Python 2/3 compatibility

[1]: http://www.omg.org/spec/UML/2.4.1/Superstructure/PDF "UML2"
[2]: http://www.secdev.org/projects/scapy/ "Scapy"
[3]: http://graphviz.org/ "Graphviz"
[4]: http://github.com/jrfonseca/xdot.py "xdot"
[5]: http://pythonhosted.org/six/ "six"

(Beginings of a) Tutorial
-------------------------
### Introduction
First things first, there's a good description of what a StateMachine
is on [Wikipedia]. What ToySM allows you to do is give a fairly
concise description of a StateMachine and have it run for you based
on inputs you *post* to the StateMachine.

1) A basic StateMachine
The following bit of code gives an example of a very simple StateMachine
that we'll use to walk through some of ToySM features.

    # Section 1 - Declare the States we'll need
    from toysm import State, FinalState, EqualsTransition, StateMachine
    from __future__ import print_function # python2 compat
    state_1 = State('state_1')
    state_2 = State('state_2')
    final = FinalState()
    
    # Section 2 - Connect the states using Transitions
    state_1 >> 'a' >> state_2
    state_2 >> 'b' >> state_1
    state_2 >> EqualsTransition('c', action=lambda sm,e: print('done')) >> final
    
    # Section 3 - We have our states, create the StateMachine and start it
    sm = StateMachine(state_1, state_2, final)
    sm.start()
    
    # Section 4 - Our StateMachine is ready to process inbound input events
    sm.post('a')	# This will transition the StateMachine from state_1
    		# to state_2

So let's have a look at what's going on here.
In section 1, we declare the states we are going to need in our future
StateMachine. Furthermore we gave (some) States a name. Naming states can come
in handy when:
- trying to debug a StateMachine, something we'll look at later, and
- identifying the state when we graph the StateMachine.

We also declared a FinalState, these are used to indicate that some
part of the StateMachine has completed. In our very simple case, it
will be used to tell the StateMachine that we've reached the end of our
processing.

Section 2, is used to string our states together with Transitions. They
describe what Events will cause our StateMachine to change from one
State to another. Here's a more visual version of what we've just
programatically described:

![StateMachine representation](images/simple_sm.png)

State_1 and State_2 are connected with "EqualsTransitions", as the
name implies this type of Transition checks if the incoming event
is Equal to the value declared when the Transition was declared.
In case of a match the Transition if followed.

The "state_1 >> 'a' >> state_2" notation is a convenient shorthand for 
"state_1 >> EqualsTransition('a') >> state_2".

You may have noticed that something slightly different is happening
between state_2 and the FinalState. Here the EqualsTransition is 
created explicitly in order to pass in an "action" argument.
This action is simply a reference to function that will be called
whenever the StateMachine follows this Transition.

So what we've accomplished here is to describe a StateMachine
that will follow sequences of 'a' input events followed by
'c' input events. If at any point we get a 'b' event, we go 
back to waiting for an 'a' event before a 'c' eventually allows
us to reach the final state and end the StateMachine.

Section 3 is where the StateMachine object is actually created. To
do this we call the StateMachine constructor and pass in the States
that will be participating in our StateMachine. Once that done, we're
good to go and can "start" the StateMachine. Behind the scene this
will create a Thread that will wait for events to be posted to the
StateMachine and make its state evolve accordingly.

In Section 4 we actually get around to 'posting' events to the StateMachine
in order to make its internal state evolve. 

TODO
----
### Hierarchy
### State Expressions
It turns out we already bumped into some of these ealier in this
tutorial. For instance the following is a State expression:

	state_1 >> EqualsTransition('a') >> state_2

We didn't delve into any detail, but these expressions can be real
time savors when describing a state machine. We've already seen
how they allow you to connect states, but it turns out you can
use them directly in State or StateMachine initializers.

	s1 = State('s1')
	s2 = State('s2')
	s3 = State('s3', s1 >> 'a' >> s2)

This will fairly concisely achieve the following: declare 3 states,
two of which are substates of the last, connect the two substates
using and EqualsTransition and declare s1 as the *initial* state
of s3. Not bad eh?

Of course you could just as well have written it this way:

	s3 = State('s3')
	s1 = State('s1', parent=s3, initial=True)
	s2 = State('s2', parent=s3)
	s1 >> 'a' >> s2

State Expressions can also be used when initializing a StateMachine, for
instance:

	sm = StateMachine(s1 >> 'a' >> s2)

### Transitions
#### Guards and Saving context
#### Actions
#### Timeouts
### Graphing
### Debugging
### Parallel States
### Layered StateMachines
### (Scapy)

[Wikipedia]: http://en.wikipedia.org/wiki/Finite-state_machine

