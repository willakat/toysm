################################################################################
#
# Copyright 2014-2015 William Barsse
#
################################################################################
#
# This file is part of ToySM Extensions.
#
# ToySM Extensions is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ToySM Extensions is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ToySM.  If not, see <http://www.gnu.org/licenses/>.
#
################################################################################

# pylint: disable=invalid-name

"""Classes intended to simplify using ToySM with Scapy:
   - PacketTransition: allows defining transitions between States based
                       on events that are scapy Packet templates.
   - SMBox: A Scapy pipe box that uses the high/low inputs to post
            events to a state machine.
"""

# Avoid attempting to reload the present module when import when
# accessing scapy or one of its submodules
from __future__ import  absolute_import

from inspect import isclass

from scapy.packet import Packet, NoPayload

try:
    from scapy.pipetool import AutoSource
    HAVE_PIPETOOL = True
except ImportError:
    from warnings import warn
    warn('Scapy 2.2.0-dev or better is necessary for Pipetool integration',
         ImportWarning)
    HAVE_PIPETOOL = False

from toysm import StateMachine, Transition, public
from toysm.public import public

@public
class ForbidPayload(Packet):
    """Used in the context of matching a packet template.
       When used as the payload of another packet in a template,
       only packets that don't have a payload will match.
    """
    # pylint: disable=no-init, too-few-public-methods
    pass


@public
def match_packet(template, packet):
    """returns True if a scapy Packet matches a template.
       Matching occurs if:
       - packet is of the same class or a subclass of template
         or if a sublayer of packet meets this criteria.
       - and for each field defined in the template the packet has a field of
         equal value.
       - for template field values that are Packets themselves, the
         corresponding field in packet will be recursively matched using
         match_packet
       - the payloads of template and packet match according to match_packet.
         if template has no payload and the previous criteria are met the
         packet is considered to have matched the template.
    """
    def inner_match_packet(template, packet):
        """Actual matching is done in this function, the outer function
           only ensures iteration over template instances.
        """
        tcls = type(template)
        while True:
            if isinstance(packet, tcls):
                break
            else:
                if isinstance(packet.payload, NoPayload):
                    return False
                else:
                    packet = packet.payload
        for fname, v_template in template.fields.items():
            try:
                v_packet = getattr(packet, fname)
            except AttributeError:
                return False
            if isinstance(v_template, Packet):
                if inner_match_packet(v_template, v_packet):
                    continue
            elif v_packet == v_template:
                continue
            return False
        if isinstance(template.payload, NoPayload):
            return True
        elif isinstance(template.payload, ForbidPayload):
            return isinstance(packet.payload, NoPayload)
        else:
            return inner_match_packet(template.payload, packet.payload)

    if isclass(template):
        template = template()
    for t in template:
        if inner_match_packet(t, packet):
            return True
    return False

@public
class PacketTransition(Transition):
    """Transition that triggers when the event matches a Scapy Packet
       template.

       A PacketTransition is created with a Scapy Packet Template:

       PacketTransition(IP()/UDP(dport=53))
         would create a transition that matches any IP packet (regardless
         of src/dst addresses) contains a UDP layer destined to port 53.

       PacketTransition(IP(dst=['1.2.3.4', '5.6.7.8'])/TCP())
         this transition would trigger on any IP/TCP packet sent to
         either 1.2.3.4 or 5.6.7.8.
         Note: the following packet would also match
               Ether()/IP(dst='1.2.3.4')/TCP()
    """

    dot = {'label': lambda t: t.desc.replace('<', r'\<').replace('>', r'\>')}

    @classmethod
    def ctor_accepts(cls, value, **_):
        """Register constructor as supporting any Packet value."""
        return isinstance(value, Packet)

    def __init__(self, template, desc=None, **kargs):
        desc = repr(template) + ('/%s' % desc if desc else '')
        super(PacketTransition, self).__init__(desc=desc, **kargs)
        self.template = template

    def is_triggered(self, sm, evt):
        return evt is not None and match_packet(self.template, evt)


if HAVE_PIPETOOL:
    @public
    class SMBox(StateMachine, AutoSource):
        def __init__(self, *args, **kargs):
            StateMachine.__init__(self, *args, **kargs)
            AutoSource.__init__(self, name=kargs.get('name'))

        def push(self, msg):
            self.post(self.convert(msg))

        def high_push(self, msg):
            self.post(self.high_convert(msg))

        def convert(self, msg):
            """Converts a message received on the low input into an
               event (to be posted to the SM)."""
            return msg

        def high_convert(self, msg):
            """Converts a message received on the high input into an
               event (to be posted to the SM)."""
            return msg

        def send(self, msg):
            """Publishes a message on the Box's low output."""
            self._gen_data(msg)
            #print('sent', repr(msg))

        def high_send(self, msg):
            """Publishes a message on the Box's high output."""
            self._gen_high_data(msg)

        def stop(self, sm_state=None):
            StateMachine.stop(self, sm_state=sm_state)
            if not self.is_exhausted:
                self.is_exhausted = True
                # Force PipeEngine to wakeup this Source and 'notice'
                # that it is exhausted
                self._wake_up()

# vim:expandtab:sw=4:sts=4
