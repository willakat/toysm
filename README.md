ToySM is a small pure Python implementation of [UML2-like] [1] statemachine
semantics .

List of features supported in ToySM
-----------------------------------
* UML2 features:
  - Hierarchical states
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
  - 'do' behavior for states (likely implementation will spawn a thread
     when a State with a do behavior is entered).

* Better graphing for Hierarchical states

* StateMachine Pause function


Dependencies
------------
- [Graphviz] [3]: to produce visual representation of a StateMachine
- [xdot] [4]: direct graph rendering instead of rendering to file
- [six] [5]: Python 2/3 compatibility

[1]: http://www.omg.org/spec/UML/2.4.1/Superstructure/PDF "UML2"
[2]: http://www.secdev.org/projects/scapy/ "Scapy"
[3]: http://graphviz.org/ "Graphviz"
[4]: http://github.com/jrfonseca/xdot.py "xdot"
[5]: http://pythonhosted.org/six/ "six"

