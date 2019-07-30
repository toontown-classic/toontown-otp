# Copyright (c) 2019, Caleb Marshall.
#
# This file is part of Toontown OTP.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# You should have received a copy of the MIT License
# along with Toontown OTP. If not, see <https://opensource.org/licenses/MIT>.

import collections

from panda3d.core import *

from realtime import io
from realtime import types
from realtime.notifier import notify
from realtime import component


class MessageError(RuntimeError):
    """
    An message director specific runtime error
    """

class MessageHandle(object):

    def __init__(self, channel, sender, message_type, datagram):
        self._channel = channel
        self._sender = sender
        self._message_type = message_type
        self._datagram = datagram

    @property
    def channel(self):
        return self._channel

    @property
    def sender(self):
        return self._sender

    @property
    def message_type(self):
        return self._message_type

    @property
    def datagram(self):
        return self._datagram

    def destroy(self):
        self._channel = None
        self._sender = None
        self._message_type = None
        self._datagram = None

class PostMessageHandle(object):

    def __init__(self, channel, datagram):
        self._channel = channel
        self._datagram = datagram

    @property
    def channel(self):
        return self._channel

    @property
    def datagram(self):
        return self._datagram

    def destroy(self):
        self._channel = None
        self._datagram = None

class MessageInterface(object):
    notify = notify.new_category('MessageInterface')

    def __init__(self, network):
        self._network = network
        self._flush_timeout = config.GetFloat('messagedirector-flush-timeout', 0.001)
        self._messages = collections.deque()
        self._post_messages = {}

    @property
    def messages(self):
        return self._messages

    @property
    def post_messages(self):
        return self._post_messages

    def append_handle(self, channel, sender, message_type, datagram):
        if not channel:
            return

        #if not datagram.get_length():
        #    self.notify.warning('Failed to append messenger handle from sender: '
        #        '%d to channel: %d, invalid datagram!' % (sender, channel))
        #
        #    return

        message_handle = MessageHandle(channel, sender, message_type, datagram)
        self._messages.append(message_handle)

    def remove_handle(self, message_handle):
        if not isinstance(message_handle, MessageHandle):
            raise MessageError('Failed to remove message handle of '
                'invalid type: %r!' % message_handle)

        self._messages.remove(message_handle)

    def append_post_handle(self, channel, datagram):
        message_handle = PostMessageHandle(channel, datagram)
        messages = self._post_messages.setdefault(channel, collections.deque())
        messages.append(message_handle)

    def remove_post_handle(self, message_handle):
        if not isinstance(message_handle, PostMessageHandle):
            raise MessageError('Failed to remove post message handle of '
                'invalid type: %r!' % message_handle)

        messages = self._post_messages.get(message_handle.channel)
        if not messages:
            self.notify.debug('Failed to remove post message handle, '
                'unknown channel: %d!' % channel)

            return

        messages.remove(message_handle)

    def clear_post_handles(self, channel):
        messages = self._post_messages.get(channel)
        if not messages:
            self.notify.debug('Failed to flush post message handles, '
                'unknown channel: %d!' % channel)

            return

        del self._post_messages[channel]

    def setup(self):
        self.__flush_task = task_mgr.doMethodLater(self._flush_timeout, self.__flush,
            self._network.get_unique_name('flush-queue'))

    def route_datagram(self, message_handle, participant):
        assert(message_handle != None)

        datagram = io.NetworkDatagram()
        datagram.add_header(message_handle.channel, message_handle.sender,
            message_handle.message_type)

        other_datagram = message_handle.datagram
        datagram.append_data(other_datagram.get_message())
        participant.handle_send_datagram(datagram)

        # destroy the datagram and message handle objects since they are
        # no longer needed in this scope...
        other_datagram.clear()
        datagram.clear()

        del other_datagram
        del datagram

        message_handle.destroy()
        del message_handle

    def __flush(self, task):
        for _ in xrange(len(self._messages)):
            # pull a message handle object off the top of the queue,
            # then attempt to route it to its appropiate channel...
            message_handle = self._messages.popleft()
            assert(message_handle != None)

            participant = self._network.interface.get_participant(message_handle.channel)
            if not participant:
                #self.notify.warning('Cannot flush message for unknown channel: %d!' %  message_handle.channel)
                continue

            self.route_datagram(message_handle, participant)

        return task.again

    def flush_post_handles(self, channel):
        messages = self._post_messages.get(channel)
        if not messages:
            self.notify.debug('Failed to flush post message handles, '
                'unknown channel: %d!' % channel)

            return

        participant = self._network.interface.get_participant(channel)
        if not participant:
            self.notify.warning('Failed to flush post message handles, '
                'unknown participant with channel: %d!' % channel)

            return

        for _ in xrange(len(messages)):
            message_handle = messages.popleft()

            # in order for us to properly handle post remove messages,
            # we need to unpack and process them like we would normally...
            datagram = message_handle.datagram
            participant.handle_datagram(io.NetworkDatagramIterator(datagram))

            # destroy the datagram and message handle objects since they are
            # no longer needed in this scope...
            datagram.clear()
            del datagram

            message_handle.destroy()
            del message_handle

        # finally clear our channel from the post removes
        # dictionary which held the message handle objects...
        self.clear_post_handles(channel)

    def flush_all_post_handles(self):
        for channel in list(self._post_messages.keys()):
            self.flush_post_handles(channel)

    def shutdown(self):
        if self.__flush_task:
            task_mgr.remove(self.__flush_task)
            self.__flush_task = None

class Participant(io.NetworkHandler):
    notify = notify.new_category('Participant')

    def register_for_channel(self, channel):
        io.NetworkHandler.register_for_channel(self, channel)
        self.network.interface.add_participant(channel, self)

    def unregister_for_channel(self, channel):
        self.network.interface.remove_participant(channel)
        io.NetworkHandler.unregister_for_channel(self, channel)

    def handle_datagram(self, di):
        channels = di.get_uint8()
        channel = di.get_uint64()
        if channels == 1 and channel == types.CONTROL_MESSAGE:
            message_type = di.get_uint16()
            sender = di.get_uint64()
            if message_type == types.CONTROL_SET_CHANNEL:
                self.register_for_channel(sender)
            elif message_type == types.CONTROL_REMOVE_CHANNEL:
                self.unregister_for_channel(sender)
            elif message_type == types.CONTROL_SET_CON_NAME:
                pass
            elif message_type == types.CONTROL_SET_CON_URL:
                pass
            elif message_type == types.CONTROL_ADD_RANGE:
                pass
            elif message_type == types.CONTROL_REMOVE_RANGE:
                pass
            elif message_type == types.CONTROL_ADD_POST_REMOVE:
                self.network.message_interface.append_post_handle(sender, io.NetworkDatagram(
                    Datagram(di.get_remaining_bytes())))
            elif message_type == types.CONTROL_CLEAR_POST_REMOVE:
                self.network.message_interface.clear_post_handles(sender)
            else:
                self.notify.warning('Failed to handle unknown datagram with '
                    'message type: %d!' % message_type)
        else:
            self.network.message_interface.append_handle(channel, di.get_uint64(), di.get_uint16(),
                io.NetworkDatagram(Datagram(di.get_remaining_bytes())))

class ParticipantInterface(object):
    notify = notify.new_category('ParticipantInterface')

    def __init__(self, network):
        self._network = network
        self._participants = {}

    @property
    def participants(self):
        return self._participants

    def has_participant(self, channel):
        return channel in self._participants

    def add_participant(self, channel, participant):
        if self.has_participant(channel):
            self.notify.warning('Failed to add participant with channel: %d, '
                'participant already exists!' % channel)

            return

        self._participants[channel] = participant

    def remove_participant(self, channel):
        if not self.has_participant(channel):
            self.notify.warning('Failed to remove participant with channel: %d, '
                'participant does not exist!' % channel)

            return

        self._network.message_interface.flush_post_handles(channel)
        del self._participants[channel]

    def get_participant(self, channel):
        return self._participants.get(channel)

class MessageDirector(io.NetworkListener, component.Component):
    notify = notify.new_category('MessageDirector')

    def __init__(self):
        address = config.GetString('messagedirector-address', '0.0.0.0')
        port = config.GetInt('messagedirector-port', 7100)

        io.NetworkListener.__init__(self, address, port, Participant)

        self._interface = ParticipantInterface(self)
        self._message_interface = MessageInterface(self)

    @property
    def interface(self):
        return self._interface

    @property
    def message_interface(self):
        return self._message_interface

    def setup(self):
        io.NetworkListener.setup(self)
        self._message_interface.setup()

    def shutdown(self):
        self._message_interface.shutdown()
        io.NetworkListener.shutdown(self)
