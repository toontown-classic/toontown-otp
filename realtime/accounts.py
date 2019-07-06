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
import time
import semidbm

from panda3d.core import *
from panda3d.direct import *

from direct.fsm.FSM import FSM

from realtime import io
from realtime import types
from realtime.notifier import notify
from realtime import util

from game.NameGenerator import NameGenerator


class ClientOperation(FSM):
    notify = notify.new_category('ClientOperation')

    def __init__(self, manager, client, callback):
        FSM.__init__(self, self.__class__.__name__)

        self._manager = manager
        self._client = client
        self._callback = callback

    @property
    def manager(self):
        return self._manager

    @property
    def client(self):
        return self._client

    @property
    def callback(self):
        return self._callback

    @callback.setter
    def callback(self, callback):
        self._callback = callback

    def enterOff(self):
        pass

    def exitOff(self):
        pass

    def defaultFilter(self, request, *args):
        return FSM.defaultFilter(self, request, *args)

    def cleanup(self, success, *args, **kwargs):
        self.ignoreAll()
        self.manager.stop_operation(self.client)
        self.demand('Off')

        # only initiate callback if the cleanup was successful...
        if self._callback and success:
            self._callback(*args, **kwargs)

class ClientOperationManager(object):
    notify = notify.new_category('ClientOperationManager')

    def __init__(self, network):
        self._network = network
        self._channel2fsm = {}

    @property
    def network(self):
        return self._network

    @property
    def channel2fsm(self):
        return self._channel2fsm

    def has_fsm(self, channel):
        return channel in self._channel2fsm

    def add_fsm(self, channel, fsm):
        if self.has_fsm(channel):
            return

        self._channel2fsm[channel] = fsm

    def remove_fsm(self, channel):
        if not self.has_fsm(channel):
            return

        del self._channel2fsm[channel]

    def get_fsm(self, channel):
        return self._channel2fsm.get(channel)

    def run_operation(self, fsm, client, callback, *args, **kwargs):
        if self.has_fsm(client.allocated_channel):
            self.notify.warning('Cannot run operation: %s for channel %d, operation already running: %s!' % (
                fsm.__name__, client.allocated_channel, self.get_fsm(client.allocated_channel).__class__.__name__))

            return None

        operation = fsm(self, client, callback, *args, **kwargs)
        self.add_fsm(client.allocated_channel, operation)
        return operation

    def stop_operation(self, client):
        if not self.has_fsm(client.allocated_channel):
            self.notify.warning('Cannot stop operation for channel %d, unknown operation!' % (
                client.channel))

            return

        operation = self.get_fsm(client.allocated_channel)
        operation.demand('Off')

        self.remove_fsm(client.allocated_channel)

class LoadAccountFSM(ClientOperation):
    notify = notify.new_category('LoadAccountFSM')

    def __init__(self, manager, client, callback, play_token):
        ClientOperation.__init__(self, manager, client, callback)

        self._play_token = play_token
        self._account_id = None

    def enterStart(self):
        if self._play_token not in self.manager.dbm:
            self.demand('Create')
            return

        self._account_id = int(self.manager.dbm[self._play_token])
        self.manager.network.database_interface.query_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._account_id,
            self.__account_loaded,
            self.manager.network.dc_loader.dclasses_by_name['Account'])

    def __account_loaded(self, dclass, fields):
        if not dclass and not fields:
            self.notify.warning('Failed to load account: %d for channel: %d playtoken: %s!' % (
                self._account_id, self._client.channel, self._play_token))

            return

        self.request('SetAccount')

    def exitStart(self):
        pass

    def enterCreate(self):
        fields = {
            'ACCOUNT_AV_SET': ([0] * 6,),
            'BIRTH_DATE': ('',),
            'BLAST_NAME': (self._play_token,),
            'CREATED': (time.ctime(),),
            'FIRST_NAME': ('',),
            'LAST_LOGIN': ('',),
            'LAST_NAME': ('',),
            'PLAYED_MINUTES': ('',),
            'PLAYED_MINUTES_PERIOD': ('',),
            'HOUSE_ID_SET': ([0] * 6,),
            'ESTATE_ID': (0,)
        }

        self.manager.network.database_interface.create_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self.manager.network.dc_loader.dclasses_by_name['Account'],
            fields=fields,
            callback=self.__account_created)

    def __account_created(self, account_id):
        self._account_id = account_id
        if not self._account_id:
            self.notify.warning('Failed to create account for channel: %d playtoken: %s!' % (
                self._client.channel, self._play_token))

            self.cleanup(False)
            return

        self.manager.dbm[self._play_token] = str(self._account_id)
        self.manager.dbm.sync()

        self.request('SetAccount')

    def exitCreate(self):
        pass

    def enterSetAccount(self):
        # the server says our login request was successful,
        # it is now ok to mark the client as authenticated...
        self._client.authenticated = True

        # add this connection to the account channel
        channel = self.client.get_account_connection_channel(self._account_id)
        self.client.register_for_channel(channel)

        # add them to the account channel
        channel = self._account_id << 32
        self.client.handle_set_channel_id(channel)

        # we're all done.
        self.cleanup(True)

    def exitSetAccount(self):
        pass

class ClientAvatarData(object):

    def __init__(self, do_id, name_list, dna, position, name_index):
        self._do_id = do_id
        self._name_list = name_list
        self._dna = dna
        self._position = position
        self._name_index = name_index

    @property
    def do_id(self):
        return self._do_id

    @do_id.setter
    def do_id(self, do_id):
        self._do_id = do_id

    @property
    def name_list(self):
        return self._name_list

    @name_list.setter
    def name_list(self, name_list):
        self._name_list = name_list

    @property
    def dna(self):
        return self._dna

    @dna.setter
    def dna(self, dna):
        self._dna = dna

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, position):
        self._position = position

    @property
    def name_index(self):
        return self._name_index

    @name_index.setter
    def name_index(self, name_index):
        self._name_index = name_index

class RetrieveAvatarsFSM(ClientOperation):
    notify = notify.new_category('RetrieveAvatarsFSM')

    def __init__(self, manager, client, callback, account_id):
        ClientOperation.__init__(self, manager, client, callback)

        self._account_id = account_id
        self._pending_avatars = []
        self._avatar_fields = {}

    def enterStart(self):
        self.manager.network.database_interface.query_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._account_id,
            self.__account_loaded,
            self.manager.network.dc_loader.dclasses_by_name['Account'])

    def exitStart(self):
        pass

    def __account_loaded(self, dclass, fields):
        avatar_list = fields['ACCOUNT_AV_SET'][0]
        for avatar_id in avatar_list:
            if not avatar_id:
                continue

            self._pending_avatars.append(avatar_id)

            def response(dclass, fields, avatar_id=avatar_id):
                self._avatar_fields[avatar_id] = fields
                self._pending_avatars.remove(avatar_id)
                if not self._pending_avatars:
                    self.request('SetAvatars')

            self.manager.network.database_interface.query_object(self.client.channel,
                types.DATABASE_CHANNEL,
                avatar_id,
                response,
                self.manager.network.dc_loader.dclasses_by_name['DistributedToon'])

        if not self._pending_avatars:
            self.request('SetAvatars')

    def enterSetAvatars(self):
        avatar_list = []

        for avatar_id, fields in self._avatar_fields.items():
            avatar_data = ClientAvatarData(avatar_id, [fields['setName'][0], '', '', ''], fields['setDNAString'][0],
                fields['setPosIndex'][0], 0)

            avatar_list.append(avatar_data)

        # we're all done.
        self.cleanup(True, avatar_list)

    def exitSetAvatars(self):
        pass

class CreateAvatarFSM(ClientOperation):
    notify = notify.new_category('CreateAvatarFSM')

    def __init__(self, manager, client, callback, echo_context, account_id, dna_string, index):
        ClientOperation.__init__(self, manager, client, callback)

        self._account_id = account_id
        self._dna_string = dna_string
        self._callback = callback
        self._echo_context = echo_context
        self._index = index

    def enterStart(self):
        fields = {
            'setDNAString': (self._dna_string,),
            'setPosIndex': (self._index,),
            'setName': ('Toon',)
        }

        self.manager.network.database_interface.create_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self.manager.network.dc_loader.dclasses_by_name['DistributedToon'],
            fields=fields,
            callback=lambda avatar_id: self.__avatar_created(avatar_id, self._index))

    def __avatar_created(self, avatar_id, index):
        self.manager.network.database_interface.query_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._account_id,
            lambda dclass, fields: self.__account_loaded(dclass, fields, avatar_id, index),
            self.manager.network.dc_loader.dclasses_by_name['Account'])

    def __account_loaded(self, dclass, fields, avatar_id, index):
        avatar_list = fields['ACCOUNT_AV_SET'][0]
        avatar_list[index] = avatar_id

        new_fields = {
            'ACCOUNT_AV_SET': (avatar_list,)
        }

        self.manager.network.database_interface.update_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._account_id,
            self.manager.network.dc_loader.dclasses_by_name['Account'],
            new_fields)

        # We're all done
        self.cleanup(True, self._echo_context, avatar_id)

    def exitStart(self):
        pass

class LoadAvatarFSM(ClientOperation):
    notify = notify.new_category('LoadAvatarFSM')

    def __init__(self, manager, client, callback, account_id, avatar_id):
        ClientOperation.__init__(self, manager, client, callback)

        self._account_id = account_id
        self._avatar_id = avatar_id

        self._dc_class = None
        self._fields = {}

    def enterStart(self):

        def response(dclass, fields):
            self._dc_class = dclass
            self._fields = fields
            self.request('Activate')

        self.manager.network.database_interface.query_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._avatar_id,
            response,
            self.manager.network.dc_loader.dclasses_by_name['DistributedToon'])

    def exitStart(self):
        pass
        
    def _handle_activate_avatar(self, task):	
        # setup a post remove message that will delete the	
        # client's toon object when they disconnect...	
        post_remove = io.NetworkDatagram()	
        post_remove.add_header(self._avatar_id, self.client.channel,	
            types.STATESERVER_OBJECT_DELETE_RAM)	

        post_remove.add_uint32(self._avatar_id)	

        datagram = io.NetworkDatagram()	
        datagram.add_control_header(self.client.allocated_channel,	
            types.CONTROL_ADD_POST_REMOVE)	

        datagram.append_data(post_remove.get_message())	
        self.manager.network.handle_send_connection_datagram(datagram)	

        # grant ownership over the distributed object...	
        datagram = io.NetworkDatagram()	
        datagram.add_header(self._avatar_id, self.client.channel,	
            types.STATESERVER_OBJECT_SET_OWNER)	

        datagram.add_uint64(self.client.channel)	
        self.manager.network.handle_send_connection_datagram(datagram)	

        # we're all done.	
        self.cleanup(True, self._avatar_id)	
        return task.done

    def enterActivate(self):
        # add them to the avatar channel
        channel = self.client.get_puppet_connection_channel(self._avatar_id)
        self.client.register_for_channel(channel)

        # set their sender channel to represent their account affiliation
        channel = self._account_id << 32 | self._avatar_id
        self.client.handle_set_channel_id(channel)

        datagram = io.NetworkDatagram()
        datagram.add_header(types.STATESERVER_CHANNEL, channel,
            types.STATESERVER_OBJECT_GENERATE_WITH_REQUIRED_OTHER)

        datagram.add_uint32(self._avatar_id)
        datagram.add_uint32(0)
        datagram.add_uint32(0)
        datagram.add_uint16(self._dc_class.get_number())

        sorted_fields = {}
        for field_name, field_args in self._fields.items():
            field = self._dc_class.get_field_by_name(field_name)

            if not field:
                self.notify.warning('Failed to pack fields for object %d, '
                    'unknown field: %s!' % (self._avatar_id, field_name))
                return

            sorted_fields[field.get_number()] = field_args

        sorted_fields = collections.OrderedDict(sorted(
            sorted_fields.items()))

        field_packer = DCPacker()
        for field_index, field_args in sorted_fields.items():
            field = self._dc_class.get_field_by_index(field_index)

            if not field:
                self.notify.error('Failed to pack required field: %d for object %d, '
                    'unknown field!' % (field_index, self._avatar_id))

            field_packer.begin_pack(field)
            field.pack_args(field_packer, field_args)
            field_packer.end_pack()

        datagram.append_data(field_packer.get_string())

        other_fields = {
            'setCommonChatFlags': (self._fields.get('setCommonChatFlags', 0),),
            'setTrophyScore': (self._fields.get('setTrophyScore', 0),),
        }

        field_packer = DCPacker()
        for field_name, field_args in other_fields.items():
            field = self._dc_class.get_field_by_name(field_name)

            if not field:
                self.notify.error('Failed to pack other field: %s for object %d, '
                    'unknown field!' % (field_name, self._avatar_id))

            field_packer.raw_pack_uint16(field.get_number())
            field_packer.begin_pack(field)
            field.pack_args(field_packer, field_args)
            field_packer.end_pack()

        datagram.add_uint16(len(other_fields))
        datagram.append_data(field_packer.get_string())
        self.manager.network.handle_send_connection_datagram(datagram)

        taskMgr.doMethodLater(0.2, self._handle_activate_avatar, 'activate-avatar-%d-task' % self._avatar_id)

    def exitActivate(self):
        pass

class LoadFriendsListFSM(ClientOperation):
    notify = notify.new_category('LoadAvatarFSM')

    def __init__(self, manager, client, callback, account_id, avatar_id):
        ClientOperation.__init__(self, manager, client, callback)

        self._account_id = account_id
        self._avatar_id = avatar_id

        self._dc_class = None
        self._fields = {}

        self._friends_list = {}
        self._pending_friends = []

    def enterStart(self):

        def response(dclass, fields):
            self._dc_class = dclass
            self._fields = fields
            self.request('QueryFriends')

        self.manager.network.database_interface.query_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._avatar_id,
            response,
            self.manager.network.dc_loader.dclasses_by_name['DistributedToon'])

    def exitStart(self):
        pass

    def enterQueryFriends(self):
        friends_list, = self._fields['setFriendsList']
        if not friends_list:
            self.cleanup(False)
            return

        self._pending_friends = {friend_id: friend_type for friend_id, friend_type in friends_list}
        for friend_id, friend_type in friends_list:

            def queryFriendCallback(dclass, fields, avatar_id=friend_id):
                self._friends_list[avatar_id] = [dclass, fields]
                del self._pending_friends[avatar_id]

                if not self._pending_friends:
                    self.request('LoadFriends')

            self.manager.network.database_interface.query_object(self.client.channel,
                types.DATABASE_CHANNEL,
                friend_id,
                queryFriendCallback,
                self.manager.network.dc_loader.dclasses_by_name['DistributedToon'])

    def exitQueryFriends(self):
        pass

    def enterLoadFriends(self):
        our_channel = self.client.get_puppet_connection_channel(self._avatar_id)
        for friend_id in self._friends_list:
            friend_channel = self.client.get_puppet_connection_channel(friend_id)
            friend_online = self.manager.network.get_handler_from_channel(friend_channel) is not None

            # tell us if they are online or not...
            datagram = io.NetworkDatagram()

            if friend_online:
                datagram.add_uint16(types.CLIENT_FRIEND_ONLINE)
            else:
                datagram.add_uint16(types.CLIENT_FRIEND_OFFLINE)

            datagram.add_uint32(friend_id)
            self.client.handle_send_datagram(datagram)

            # tell them that we are online if they are online...
            if friend_online:
                datagram = io.NetworkDatagram()
                datagram.add_header(friend_channel, our_channel,
                    types.CLIENTAGENT_FRIEND_ONLINE)

                datagram.add_uint32(self._avatar_id)
                self.manager.network.handle_send_connection_datagram(datagram)

            # setup a post remove that will tell all of our friends
            # that we are offline when we disconnect...
            post_remove = io.NetworkDatagram()
            post_remove.add_header(friend_channel, our_channel,
                types.CLIENTAGENT_FRIEND_OFFLINE)

            post_remove.add_uint32(self._avatar_id)

            datagram = io.NetworkDatagram()
            datagram.add_control_header(self.client.allocated_channel,
                types.CONTROL_ADD_POST_REMOVE)

            datagram.append_data(post_remove.get_message())
            self.manager.network.handle_send_connection_datagram(datagram)

        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_GET_FRIEND_LIST_RESP)
        datagram.add_uint8(0)
        datagram.add_uint16(len(self._friends_list))

        for friend_id in self._friends_list:
            dclass, fields = self._friends_list[friend_id]

            datagram.add_uint32(friend_id)
            datagram.add_string(fields['setName'][0])
            datagram.add_string(fields['setDNAString'][0])

        self.client.handle_send_datagram(datagram)

        # we're all done.
        self.cleanup(True)

    def exitLoadFriends(self):
        pass

class SetNameFSM(ClientOperation):
    notify = notify.new_category('SetNameFSM')

    def __init__(self, manager, client, callback, avatar_id, wish_name):
        self.notify.debug("SetNameFSM.__init__(%s, %s, %s, %s, %s)" % (str(manager), str(client),
            str(callback), str(avatar_id), str(wish_name)))

        ClientOperation.__init__(self, manager, client, callback)

        self._avatar_id = avatar_id
        self._wish_name = wish_name
        self._callback = callback
        self._dc_class = None
        self._fields = {}

    def enterStart(self):
        self.notify.debug("SetNameFSM.enterQuery()")

        def response(dclass, fields):
            self.notify.debug("SetNameFSM.enterQuery.response(%s, %s)" % (str(dclass), str(fields)))
            self._dc_class = dclass
            self._fields = fields
            self.request('SetName')

        self.manager.network.database_interface.query_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._avatar_id,
            response,
            self.manager.network.dc_loader.dclasses_by_name['DistributedToon'])

    def exitStart(self):
        self.notify.debug("SetNameFSM.exitQuery()")

    def enterSetName(self):
        self.notify.debug("SetNameFSM.enterSetName()")

        # TODO: Parse a check the wish-name for bad names and etc.
        new_fields = {
             'setName': (self._wish_name,)
        }

        #self.notify.warning("New fields are \n%s" % (str(self._fields)))

        self.manager.network.database_interface.update_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._avatar_id,
            self.manager.network.dc_loader.dclasses_by_name['DistributedToon'],
            new_fields)

        # We're all done
        self.cleanup(True, self._avatar_id, self._wish_name)

    def exitSetName(self):
        self.notify.debug("SetNameFSM.exitSetName()")
        
class SetNamePatternFSM(ClientOperation):
    notify = notify.new_category('SetNamePatternFSM')

    def __init__(self, manager, client, callback, avatar_id, pattern):
        self.notify.debug("SetNamePatternFSM.__init__(%s, %s, %s, %s, %s)" % (str(manager), str(client),
            str(callback), str(avatar_id), str(pattern)))

        ClientOperation.__init__(self, manager, client, callback)

        self._avatar_id = avatar_id
        self._pattern = pattern
        self._callback = callback
        self._dc_class = None
        self._fields = {}

    def enterStart(self):
        self.notify.debug("SetNamePatternFSM.enterQuery()")

        def response(dclass, fields):
            self.notify.debug("SetNamePatternFSM.enterQuery.response(%s, %s)" % (str(dclass), str(fields)))
            self._dc_class = dclass
            self._fields = fields
            self.request('SetPatternName')

        self.manager.network.database_interface.query_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._avatar_id,
            response,
            self.manager.network.dc_loader.dclasses_by_name['DistributedToon'])

    def exitStart(self):
        self.notify.debug("SetNamePatternFSM.exitQuery()")

    def enterSetPatternName(self):
        self.notify.debug("SetNamePatternFSM.enterSetPatternName()")
        
        nameGenerator = NameGenerator()
        
        # Render the pattern into a string:
        parts = []
        for p, f in self._pattern:
            part = nameGenerator.nameDictionary.get(p, ('', ''))[1]
            if f:
                part = part[:1].upper() + part[1:]
            else:
                part = part.lower()
            parts.append(part)

        parts[2] += parts.pop(3)  # Merge 2&3 (the last name) as there should be no space.
        while '' in parts:
            parts.remove('')
        name = ' '.join(parts)
        
        del nameGenerator

        new_fields = {
             'setName': (name,)
        }

        #self.notify.warning("New fields are \n%s" % (str(self._fields)))

        self.manager.network.database_interface.update_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._avatar_id,
            self.manager.network.dc_loader.dclasses_by_name['DistributedToon'],
            new_fields)

        # We're all done
        self.cleanup(True, self._avatar_id)

    def exitSetPatternName(self):
        self.notify.debug("SetNamePatternFSM.exitSetPatternName()")

class GetAvatarDetailsFSM(ClientOperation):
    notify = notify.new_category('GetAvatarDetailsFSM')

    def __init__(self, manager, client, callback, avatar_id):
        ClientOperation.__init__(self, manager, client, callback)

        self._avatar_id = avatar_id
        self._callback = callback
        self._dc_class = None
        self._fields = {}

    def enterStart(self):

        def response(dclass, fields):
            self._dc_class = dclass
            self._fields = fields
            self.request('SendDetails')

        self.manager.network.database_interface.query_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._avatar_id,
            response,
            self.manager.network.dc_loader.dclasses_by_name['DistributedToon'])

    def exitStart(self):
        pass

    def enterSendDetails(self):
        datagram = io.NetworkDatagram()
        datagram.add_uint64(self._avatar_id)
        datagram.add_uint64(0)
        datagram.add_uint32(0)
        datagram.add_uint16(0)

        sorted_fields = {}
        for field_name, field_args in self._fields.items():
            field = self._dc_class.get_field_by_name(field_name)
            if not field:
                self.notify.warning('Failed to pack fields for object %d, unknown field: %s!' % (
                    self._avatar_id, field_name))

                self.cleanup(False)
                return

            sorted_fields[field.get_number()] = field_args

        sorted_fields = collections.OrderedDict(sorted(
            sorted_fields.items()))

        field_packer = DCPacker()
        for field_index, field_args in sorted_fields.items():
            field = self._dc_class.get_field_by_index(field_index)
            if not field:
                self.notify.warning('Failed to pack required field: %d for object %d, unknown field!' % (
                    field_index, self._avatar_id))

                self.cleanup(False)
                return

            field_packer.begin_pack(field)
            field.pack_args(field_packer, field_args)
            field_packer.end_pack()

        datagram.append_data(field_packer.get_string())
        di = io.NetworkDatagramIterator(datagram)

        # We're all done
        self.cleanup(True, False, di)

    def exitSendDetails(self):
        pass

class DeleteAvatarFSM(ClientOperation):
    notify = notify.new_category('DeleteAvatarFSM')

    def __init__(self, manager, client, callback, account_id, avatar_id):
        ClientOperation.__init__(self, manager, client, callback)

        self._account_id = account_id
        self._avatar_id = avatar_id
        self._pending_avatars = []
        self._avatar_fields = {}

    def enterStart(self):
        self.manager.network.database_interface.query_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._account_id,
            self.__account_loaded,
            self.manager.network.dc_loader.dclasses_by_name['Account'])

    def exitStart(self):
        pass

    def __account_loaded(self, dclass, fields):
        self.avatar_list = fields['ACCOUNT_AV_SET'][0]
        for avatar_id in self.avatar_list:
            if not avatar_id or avatar_id == self._avatar_id:
                continue

            self._pending_avatars.append(avatar_id)

            def response(dclass, fields, avatar_id=avatar_id):
                self._avatar_fields[avatar_id] = fields
                self._pending_avatars.remove(avatar_id)
                if not self._pending_avatars:
                    self.request('ApplyAvatars')

            self.manager.network.database_interface.query_object(self.client.channel,
                types.DATABASE_CHANNEL,
                avatar_id,
                response,
                self.manager.network.dc_loader.dclasses_by_name['DistributedToon'])

        if not self._pending_avatars:
            self.request('ApplyAvatars')

    def enterApplyAvatars(self):
        for avatar_id in self.avatar_list:
            if avatar_id == self._avatar_id:
                index = self.avatar_list.index(self._avatar_id)
                self.avatar_list[index] = 0
                break

        new_fields = {
            'ACCOUNT_AV_SET': (self.avatar_list,)
        }

        def update_callback(fields):
            if fields is not None:
                self.cleanup(False)
                return

            self.demand('SetAvatars')

        self.manager.network.database_interface.update_object(self.client.channel,
            types.DATABASE_CHANNEL,
            self._account_id,
            self.manager.network.dc_loader.dclasses_by_name['Account'],
            new_fields,
            callback=update_callback)

        del self.avatar_list

    def exitApplyAvatars(self):
        pass

    def enterSetAvatars(self):
        avatar_list = []
        for avatar_id, fields in self._avatar_fields.items():
            avatar_data = ClientAvatarData(avatar_id, [fields['setName'][0], '', '', ''], fields['setDNAString'][0],
                fields['setPosIndex'][0], 0)

            avatar_list.append(avatar_data)

        # we're all done.
        self.cleanup(True, avatar_list)

    def exitSetAvatars(self):
        pass

class ClientAccountManager(ClientOperationManager):
    notify = notify.new_category('ClientAccountManager')

    def __init__(self, *args, **kwargs):
        ClientOperationManager.__init__(self, *args, **kwargs)

        self._dbm = semidbm.open(config.GetString('clientagent-dbm-filename', 'databases/database.dbm'),
            config.GetString('clientagent-dbm-mode', 'c'))

    @property
    def dbm(self):
        return self._dbm

    def handle_operation(self, operationFSM, client, callback, *args, **kwargs):
        operation = self.run_operation(operationFSM, client, callback, *args, **kwargs)
        if not operation:
            self.notify.warning('Failed to handle unknown operation: %r!' % operationFSM)
            return

        operation.request('Start')
