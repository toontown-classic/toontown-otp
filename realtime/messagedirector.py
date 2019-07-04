"""
 * Copyright (C) Caleb Marshall - All Rights Reserved
 * Written by Caleb Marshall <anythingtechpro@gmail.com>, August 17th, 2017
 * Contributed to by Prince Frizzy <theclashingfritz@gmail.com>, June 21st, 2018
 * Licensing information can found in 'LICENSE', which is part of this source code package.
"""

import collections
import time

from panda3d.core import *

from realtime import io
from realtime import types
from realtime.notifier import notify


class MessageError(RuntimeError):
    """
    An message director specific runtime error
    """

class Participant(io.NetworkHandler):
    notify = notify.new_category('Participant')

    def __init__(self, *args, **kwargs):
        io.NetworkHandler.__init__(self, *args, **kwargs)

        self._lo_channel = 0
        self._hi_channel = 0

    @property
    def lo_channel(self):
        return self._lo_channel

    @lo_channel.setter
    def lo_channel(self, lo_channel):
        self._lo_channel = lo_channel

    @property
    def hi_channel(self):
        return self._hi_channel

    @hi_channel.setter
    def hi_channel(self, hi_channel):
        self._hi_channel = hi_channel

    def handle_datagram(self, di):
        channels = di.get_uint8()
        if channels == 1:
            self.handle_control_message(di)

    def handle_control_message(self, di):
        channel = di.get_uint64()
        if channel == types.CONTROL_MESSAGE:
            message_type = di.get_uint16()
            sender = di.get_uint64()

            if message_type == types.CONTROL_SET_CHANNEL:
                if not self.channel:
                    self.channel = sender

                self.network.interface.add_participant(sender, self)
            elif message_type == types.CONTROL_REMOVE_CHANNEL:
                self.network.message_interface.flush_post_handles(sender)
                self.network.interface.remove_participant(sender)
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

    def handle_disconnected(self):
        self.network.message_interface.flush_post_handles(self.channel)
        self.network.interface.remove_participant(self.channel)
        io.NetworkHandler.handle_disconnected(self)

    def shutdown(self):
        self.allocated_channel = 0
        self.channel = 0
        io.NetworkHandler.shutdown(self)

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
            self.notify.debug('Failed to add participant with channel: %d, '
                'participant already exists!' % channel)

            return

        self._participants[channel] = participant

    def remove_participant(self, channel):
        if not self.has_participant(channel):
            self.notify.debug('Failed to remove participant with channel: %d, '
                'participant does not exist!' % channel)

            return

        del self._participants[channel]

    def get_participant(self, channel):
        return self._participants.get(channel)

class MessageHandle(object):

    def __init__(self, channel, sender, message_type, datagram, timestamp):
        self._channel = channel
        self._sender = sender
        self._message_type = message_type
        self._datagram = datagram
        self._timestamp = timestamp

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

    @property
    def timestamp(self):
        return self._timestamp

    def destroy(self):
        self._channel = None
        self._sender = None
        self._message_type = None
        self._datagram = None
        self._timestamp = None

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
        self._message_timeout = config.GetFloat(
            'messagedirector-message-timeout', 15.0)

        self._messages = collections.deque()
        self._post_messages = {}

    @property
    def messages(self):
        return self._messages

    @property
    def post_messages(self):
        return self._post_messages

    def get_timestamp(self):
        return round(time.time(), 2)

    def append_handle(self, channel, sender, message_type, datagram):
        if not channel:
            return

        #if not datagram.get_length():
        #    self.notify.warning('Failed to append messenger handle from sender: '
        #        '%d to channel: %d, invalid datagram!' % (sender, channel))
        #
        #    return

        message_handle = MessageHandle(channel, sender, message_type, datagram, self.get_timestamp())
        self._messages.appendleft(message_handle)

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
        self.__flush_task = task_mgr.doMethodLater(0.001, self.__flush,
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
            self.notify.debug('Failed to flush post message handles, '
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

    def shutdown(self):
        if self.__flush_task:
            task_mgr.remove(self.__flush_task)
            self.__flush_task = None

class MessageDirector(io.NetworkListener):
    notify = notify.new_category('MessageDirector')

    def __init__(self, address, port):
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
        self._message_interface.setup()
        io.NetworkListener.setup(self)

    def shutdown(self):
        self._message_interface.shutdown()
        io.NetworkListener.shutdown(self)
