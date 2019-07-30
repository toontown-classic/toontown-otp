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

from realtime import io
from realtime import types
from realtime.notifier import notify
from realtime import util
from realtime import component
from realtime.accounts import *

from game.OtpDoGlobals import *
from game import genDNAFileName, extractGroupName
from game import ZoneUtil
from game.dna.DNAParser import loadDNAFileAI, DNAStorage


class InterestManager(object):

    def __init__(self):
        self._interest_zones = set()

    @property
    def interest_zones(self):
        return self._interest_zones

    def has_interest_zone(self, zone_id):
        return zone_id in self._interest_zones

    def add_interest_zone(self, zone_id):
        if zone_id in self._interest_zones:
            return

        # ensure we always have interest in the quiet zone
        if OTP_ZONE_ID_OLD_QUIET_ZONE not in self._interest_zones:
            self._interest_zones.add(OTP_ZONE_ID_OLD_QUIET_ZONE)

        self._interest_zones.add(zone_id)

    def remove_interest_zone(self, zone_id):
        if zone_id not in self._interest_zones:
            return

        self._interest_zones.remove(zone_id)

    def clear(self):
        self._interest_zones = set()

class Client(io.NetworkHandler):
    notify = notify.new_category('Client')

    def __init__(self, *args, **kwargs):
        io.NetworkHandler.__init__(self, *args, **kwargs)

        self.channel = self.network.channel_allocator.allocate()
        self._authenticated = False

        self._interest_manager = InterestManager()

        self._location_deferred_callback = None

        self.__interest_timeout_task = None
        self._generate_deferred_callback = None

        self._seen_objects = {}
        self._owned_objects = []
        self._pending_objects = []

        self._dna_stores = {}

    @property
    def authenticated(self):
        return self._authenticated

    @authenticated.setter
    def authenticated(self, authenticated):
        self._authenticated = authenticated

    def has_seen_object(self, do_id):
        for zone_id, seen_objects in list(self._seen_objects.items()):
            if do_id in seen_objects:
                return True

        return False

    def remove_seen_object(self, do_id):
        for zone_id, seen_objects in list(self._seen_objects.items()):
            if do_id in seen_objects:
                seen_objects.remove(do_id)

            if len(seen_objects) == 0:
                del self._seen_objects[zone_id]

    def get_seen_object_zone(self, do_id):
        for zone_id, seen_objects in list(self._seen_objects.items()):
            if do_id in seen_objects:
                return zone_id

        return -1

    def startup(self):
        io.NetworkHandler.startup(self)

    def handle_send_disconnect(self, code, reason):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_GO_GET_LOST)
        datagram.add_uint16(code)
        datagram.add_string(reason)

        self.handle_send_datagram(datagram)
        self.handle_disconnect()

    def handle_datagram(self, di):
        try:
            message_type = di.get_uint16()
        except:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_TRUNCATED_DATAGRAM,
                'Received truncated datagram from channel: %d!' % self._channel)

            return

        if message_type == types.CLIENT_HEARTBEAT:
            pass
        elif message_type == types.CLIENT_LOGIN_2:
            self.handle_login(di)
        elif message_type == types.CLIENT_DISCONNECT:
            self.handle_disconnect()
        else:
            if not self._authenticated:
                self.handle_send_disconnect(types.CLIENT_DISCONNECT_ANONYMOUS_VIOLATION,
                    'Cannot send datagram with message type: %d, channel: %d not yet authenticated!' % (message_type, self.channel))

                return
            else:
                self.handle_authenticated_datagram(message_type, di)

    def handle_authenticated_datagram(self, message_type, di):
        if message_type == types.CLIENT_GET_SHARD_LIST:
            self.handle_get_shard_list()
        elif message_type == types.CLIENT_GET_AVATARS:
            self.handle_get_avatars()
        elif message_type == types.CLIENT_GET_AVATAR_DETAILS:
            self.handle_get_avatar_details(di)
        elif message_type == types.CLIENT_CREATE_AVATAR:
            self.handle_create_avatar(di)
        elif message_type == types.CLIENT_SET_AVATAR:
            self.handle_set_avatar(di)
        elif message_type == types.CLIENT_SET_WISHNAME:
            self.handle_set_wishname(di)
        elif message_type == types.CLIENT_SET_NAME_PATTERN:
            self.handle_set_name_pattern(di)
        elif message_type == types.CLIENT_DELETE_AVATAR:
            self.handle_delete_avatar(di)
        elif message_type == types.CLIENT_GET_FRIEND_LIST:
            self.handle_get_friends_list(di)
        elif message_type == types.CLIENT_REMOVE_FRIEND:
            pass
        elif message_type == types.CLIENT_SET_SHARD:
            self.handle_set_shard(di)
        elif message_type == types.CLIENT_SET_ZONE:
            self.handle_set_zone(di)
        elif message_type == types.CLIENT_OBJECT_UPDATE_FIELD:
            self.handle_object_update_field(di)
        else:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_INVALID_MSGTYPE,
                'Unknown datagram: %d from channel: %d!' % (message_type, self.channel))

            return

    def handle_internal_datagram(self, message_type, sender, di):
        if message_type == types.CLIENTAGENT_DISCONNECT:
            self.handle_send_disconnect(di.get_uint16(), di.get_string())
        elif message_type == types.CLIENTAGENT_FRIEND_ONLINE:
            self.handle_friend_online(di)
        elif message_type == types.CLIENTAGENT_FRIEND_OFFLINE:
            self.handle_friend_offline(di)
        elif message_type == types.STATESERVER_GET_SHARD_ALL_RESP:
            self.handle_get_shard_list_resp(di)
        elif message_type == types.STATESERVER_OBJECT_LOCATION_ACK:
            self.handle_object_location_ack(di)
        elif message_type == types.STATESERVER_OBJECT_GET_ZONES_OBJECTS_RESP:
            self.handle_object_get_zones_objects_resp(di)
        elif message_type == types.STATESERVER_OBJECT_ENTER_OWNER_WITH_REQUIRED:
            self.handle_object_enter_owner(False, di)
        elif message_type == types.STATESERVER_OBJECT_ENTER_OWNER_WITH_REQUIRED_OTHER:
            self.handle_object_enter_owner(True, di)
        elif message_type == types.STATESERVER_OBJECT_ENTER_LOCATION_WITH_REQUIRED:
            self.handle_object_enter_location(False, di)
        elif message_type == types.STATESERVER_OBJECT_ENTER_LOCATION_WITH_REQUIRED_OTHER:
            self.handle_object_enter_location(True, di)
        elif message_type == types.STATESERVER_OBJECT_CHANGING_LOCATION:
            self.handle_object_changing_location(di)
        elif message_type == types.STATESERVER_OBJECT_UPDATE_FIELD:
            self.handle_object_update_field_resp(di)
        elif message_type == types.STATESERVER_OBJECT_DELETE_RAM:
            self.handle_object_delete_ram(di)
        else:
            self.network.database_interface.handle_datagram(message_type, di)

    def handle_login(self, di):
        try:
            play_token = di.get_string()
            server_version = di.get_string()
            hash_val = di.get_uint32()
            token_type = di.get_int32()
        except:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_TRUNCATED_DATAGRAM,
                'Received truncated datagram from channel: %d!' % self._channel)

            return

        if server_version != self.network.server_version:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_BAD_VERSION,
                'Invalid server version: %s, expected: %s!' % (server_version, self.network.server_version))

            return

        if hash_val != self.network.server_hash_val:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_BAD_DCHASH,
                'Got an invalid DC hash value: %d expected: %d!' % (hash_val, self.network.server_hash_val))

            return

        if token_type != types.CLIENT_LOGIN_2_BLUE and token_type != CLIENT_LOGIN_2_PLAY_TOKEN:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_INVALID_PLAY_TOKEN_TYPE, 'Invalid play token type: %d!' % token_type)
            return

        self.network.account_manager.handle_operation(LoadAccountFSM, self, self.__handle_login_resp, play_token)

    def __handle_login_resp(self, play_token):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_LOGIN_2_RESP)
        datagram.add_uint8(0)
        datagram.add_string('All Ok')
        datagram.add_string(play_token)
        datagram.add_uint8(1)
        datagram.add_uint32(int(time.time()))
        datagram.add_uint32(int(time.clock()))
        datagram.add_uint8(1)
        datagram.add_int32(1000 * 60 * 60)
        self.handle_send_datagram(datagram)

    def handle_get_shard_list(self):
        datagram = io.NetworkDatagram()
        datagram.add_header(types.STATESERVER_CHANNEL, self.channel,
            types.STATESERVER_GET_SHARD_ALL)

        self.network.handle_send_connection_datagram(datagram)

    def handle_get_shard_list_resp(self, di):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_GET_SHARD_LIST_RESP)
        datagram.append_data(di.get_remaining_bytes())
        self.handle_send_datagram(datagram)

    def handle_get_avatars(self):
        account_id = self.get_account_id_from_channel_code(self.channel)
        self.network.account_manager.handle_operation(RetrieveAvatarsFSM, self,
            self.__handle_retrieve_avatars_resp, account_id)

    def __handle_retrieve_avatars_resp(self, avatar_data):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_GET_AVATARS_RESP)
        datagram.add_uint8(0)
        datagram.add_uint16(len(avatar_data))

        for avatar in avatar_data:
            datagram.add_uint32(avatar.do_id)
            datagram.add_string(avatar.name_list[0])
            datagram.add_string(avatar.name_list[1])
            datagram.add_string(avatar.name_list[2])
            datagram.add_string(avatar.name_list[3])
            datagram.add_string(avatar.dna)
            datagram.add_uint8(avatar.position)
            datagram.add_uint8(avatar.name_index)

        self.handle_send_datagram(datagram)

    def handle_create_avatar(self, di):
        try:
            echo_context = di.get_uint16()
            dna_string = di.get_string()
            index = di.get_uint8()
        except:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_TRUNCATED_DATAGRAM,
                'Received truncated datagram from channel: %d!' % self._channel)

            return

        account_id = self.get_account_id_from_channel_code(self.channel)
        self.network.account_manager.handle_operation(CreateAvatarFSM, self,
            self.__handle_create_avatar_resp, echo_context, account_id, dna_string, index)

    def __handle_create_avatar_resp(self, echo_context, avatar_id):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_CREATE_AVATAR_RESP)
        datagram.add_uint16(echo_context)
        datagram.add_uint8(0)
        datagram.add_uint32(avatar_id)
        self.handle_send_datagram(datagram)

    def handle_set_avatar(self, di):
        try:
            avatar_id = di.get_uint32()
        except:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_TRUNCATED_DATAGRAM,
                'Received truncated datagram from channel: %d!' % self._channel)

            return

        account_id = self.get_account_id_from_channel_code(self.channel)
        self.network.account_manager.handle_operation(LoadAvatarFSM, self,
            self.__handle_set_avatar_resp, account_id, avatar_id)

    def __handle_set_avatar_resp(self, avatar_id):
        pass

    def handle_friend_online(self, di):
        friend_id = di.get_uint32()

        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_FRIEND_ONLINE)
        datagram.add_uint32(friend_id)
        self.handle_send_datagram(datagram)

    def handle_friend_offline(self, di):
        friend_id = di.get_uint32()

        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_FRIEND_OFFLINE)
        datagram.add_uint32(friend_id)
        self.handle_send_datagram(datagram)

    def handle_get_avatar_details(self, di):
        try:
            avatar_id = di.get_uint32()
        except:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_TRUNCATED_DATAGRAM,
                'Received truncated datagram from channel: %d!' % self._channel)

            return

        self.network.account_manager.handle_operation(GetAvatarDetailsFSM, self,
            self.handle_object_enter_owner, avatar_id)

    def handle_set_wishname(self, di):
        try:
            avatar_id = di.get_uint32()
            wish_name = di.get_string()
        except:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_TRUNCATED_DATAGRAM,
                'Received truncated datagram from channel: %d!' % self._channel)

            return

        self.network.account_manager.handle_operation(SetNameFSM, self,
            self.__handle_set_wishname_resp, avatar_id, wish_name)

    def __handle_set_wishname_resp(self, avatar_id, wish_name):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_SET_WISHNAME_RESP)
        datagram.add_uint32(avatar_id)
        datagram.add_uint16(0)
        datagram.add_string('')
        datagram.add_string(wish_name)
        datagram.add_string('')
        self.handle_send_datagram(datagram)

    def handle_set_name_pattern(self, di):
        try:
            name_indices = []
            name_flags = []
            avatar_id = di.get_uint32()
            name_indices.append(di.get_uint16())
            name_flags.append(di.get_uint16())
            name_indices.append(di.get_uint16())
            name_flags.append(di.get_uint16())
            name_indices.append(di.get_uint16())
            name_flags.append(di.get_uint16())
            name_indices.append(di.get_uint16())
            name_flags.append(di.get_uint16())
        except:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_TRUNCATED_DATAGRAM,
                'Received truncated datagram from channel: %d!' % self._channel)
            return

        pattern = [
            (name_indices[0], name_flags[0]),
            (name_indices[1], name_flags[1]),
            (name_indices[2], name_flags[2]),
            (name_indices[3], name_flags[3])]

        self.network.account_manager.handle_operation(SetNamePatternFSM, self,
            self.__handle_set_name_pattern_resp, avatar_id, pattern)

    def __handle_set_name_pattern_resp(self, avatar_id):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_SET_NAME_PATTERN_ANSWER)
        datagram.add_uint32(avatar_id)
        datagram.add_uint8(0)
        self.handle_send_datagram(datagram)

    def handle_get_friends_list(self, di):
        account_id = self.get_account_id_from_channel_code(self.channel)
        avatar_id = self.get_avatar_id_from_connection_channel(self.channel)

        self.network.account_manager.handle_operation(LoadFriendsListFSM, self,
            self.__handle_get_friends_list_callback, account_id, avatar_id)

    def __handle_get_friends_list_callback(self):
        pass

    def handle_delete_avatar(self, di):
        try:
            avatar_id = di.get_uint32()
        except:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_TRUNCATED_DATAGRAM,
                'Received truncated datagram from channel: %d!' % self._channel)
            return

        account_id = self.get_account_id_from_channel_code(self.channel)
        self.network.account_manager.handle_operation(DeleteAvatarFSM, self,
            self.__handle_delete_avatar_resp, account_id, avatar_id)

    def __handle_delete_avatar_resp(self, avatar_data):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_DELETE_AVATAR_RESP)
        datagram.add_uint8(0)
        datagram.add_uint16(len(avatar_data))

        for avatar in avatar_data:
            datagram.add_uint32(avatar.do_id)
            datagram.add_string(avatar.name_list[0])
            datagram.add_string(avatar.name_list[1])
            datagram.add_string(avatar.name_list[2])
            datagram.add_string(avatar.name_list[3])
            datagram.add_string(avatar.dna)
            datagram.add_uint8(avatar.position)
            datagram.add_uint8(avatar.name_index)

        self.handle_send_datagram(datagram)

    def handle_set_shard(self, di):
        try:
            shard_id = di.get_uint32()
        except:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_TRUNCATED_DATAGRAM,
                'Received truncated datagram from channel: %d!' % self._channel)

            return

        avatar_id = self.get_avatar_id_from_connection_channel(self.channel)
        self._location_deferred_callback = util.DeferredCallback(self.handle_set_shard_callback)

        datagram = io.NetworkDatagram()
        datagram.add_header(avatar_id, self.channel,
            types.STATESERVER_OBJECT_SET_AI)

        datagram.add_uint64(shard_id)
        self.network.handle_send_connection_datagram(datagram)

    def handle_set_shard_callback(self, do_id, old_parent_id, old_zone_id, new_parent_id, new_zone_id):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_GET_STATE_RESP)
        self.handle_send_datagram(datagram)

    def handle_set_zone(self, di):
        try:
            zone_id = di.get_uint16()
        except:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_TRUNCATED_DATAGRAM,
                'Received truncated datagram from channel: %d!' % (
                    self._channel))

            return

        avatar_id = self.get_avatar_id_from_connection_channel(self.channel)
        self._location_deferred_callback = util.DeferredCallback(self.handle_set_zone_callback)

        datagram = io.NetworkDatagram()
        datagram.add_header(avatar_id, self.channel,
            types.STATESERVER_OBJECT_SET_ZONE)

        datagram.add_uint32(zone_id)
        self.network.handle_send_connection_datagram(datagram)

    def send_get_zones_objects(self, avatar_id, interest_zones):
        datagram = io.NetworkDatagram()
        datagram.add_header(avatar_id, self.channel,
            types.STATESERVER_OBJECT_GET_ZONES_OBJECTS)

        # pack the interest zones
        datagram.add_uint16(len(interest_zones))
        for interest_zone in interest_zones:
            datagram.add_uint32(interest_zone)

        self.network.handle_send_connection_datagram(datagram)

    def get_in_street_branch(self, zone_id):
        if not ZoneUtil.isPlayground(zone_id):
            where = ZoneUtil.getWhereName(zone_id, True)
            return where == 'street'

        return False

    def get_vis_branch_zones(self, zone_id):
        branch_zone_id = ZoneUtil.getBranchZone(zone_id)
        dnaStore = self._dna_stores.get(branch_zone_id)
        if not dnaStore:
            dnaStore = DNAStorage()
            dnaFileName = genDNAFileName(branch_zone_id)
            loadDNAFileAI(dnaStore, dnaFileName)
            self._dna_stores[branch_zone_id] = dnaStore

        zoneVisDict = {}
        for i in xrange(dnaStore.getNumDNAVisGroupsAI()):
            groupFullName = dnaStore.getDNAVisGroupName(i)
            visGroup = dnaStore.getDNAVisGroupAI(i)
            visZoneId = int(extractGroupName(groupFullName))
            visZoneId = ZoneUtil.getTrueZoneId(visZoneId, zone_id)
            visibles = []
            for i in xrange(visGroup.getNumVisibles()):
                visibles.append(int(visGroup.visibles[i]))

            visibles.append(ZoneUtil.getBranchZone(visZoneId))
            zoneVisDict[visZoneId] = visibles

        return zoneVisDict[zone_id]

    def handle_set_zone_callback(self, do_id, old_parent_id, old_zone_id, new_parent_id, new_zone_id):
        if self._location_deferred_callback:
            self._location_deferred_callback.destroy()
            self._location_deferred_callback = None

        old_zone_in_street_branch = self.get_in_street_branch(old_zone_id)
        new_zone_in_street_branch = self.get_in_street_branch(new_zone_id)

        old_vis_zones = set()
        if old_zone_in_street_branch:
            old_branch_zone_id = ZoneUtil.getBranchZone(old_zone_id)
            old_vis_zones.update(self.get_vis_branch_zones(old_zone_id))
            for zone_id in self._interest_manager.interest_zones.difference(old_vis_zones):
                self._interest_manager.remove_interest_zone(zone_id)
        else:
            self._interest_manager.remove_interest_zone(old_zone_id)
            if old_zone_id != OTP_ZONE_ID_OLD_QUIET_ZONE:
                self._interest_manager.remove_interest_zone(OTP_ZONE_ID_OLD_QUIET_ZONE)

        new_vis_zones = set()
        if new_zone_in_street_branch:
            new_branch_zone_id = ZoneUtil.getBranchZone(old_zone_id)
            new_vis_zones.update(self.get_vis_branch_zones(new_zone_id))
            for zone_id in new_vis_zones.difference(old_vis_zones):
                self._interest_manager.add_interest_zone(zone_id)
        else:
            self._interest_manager.add_interest_zone(new_zone_id)
            if new_zone_id != OTP_ZONE_ID_OLD_QUIET_ZONE:
                self._interest_manager.add_interest_zone(OTP_ZONE_ID_OLD_QUIET_ZONE)

        # clear the dna store for this branch zones since
        # they have left the street branch
        if (old_zone_in_street_branch and not new_zone_in_street_branch) or\
            (old_zone_in_street_branch and new_zone_in_street_branch and old_branch_zone_id != new_branch_zone_id):

            # remove the branch dna zone store
            branch_zone_id = ZoneUtil.getBranchZone(old_zone_id)
            del self._dna_stores[branch_zone_id]

            # remove the old street zones
            old_vis_zones = self.get_vis_branch_zones(old_zone_id)
            for zone_id in old_vis_zones:
                self._interest_manager.remove_interest_zone(zone_id)

        # destroy the objects we no longer have interest in
        for zone_id in dict(self._seen_objects):
            if self._interest_manager.has_interest_zone(zone_id):
                continue

            seen_objects = list(self._seen_objects[zone_id])
            for do_id in seen_objects:
                if do_id in self._owned_objects:
                    continue

                self.remove_seen_object(do_id)
                self.send_client_object_delete_resp(do_id)

        # only run a deferred callback if we moved to or from a non street zone
        if not old_zone_in_street_branch or not new_zone_in_street_branch:
            self._generate_deferred_callback = util.DeferredCallback(self.handle_set_zone_complete_callback,
                old_parent_id, old_zone_id, new_parent_id, new_zone_id)

        # request all of the objects in the zones we have interest in
        avatar_id = self.get_avatar_id_from_connection_channel(self.channel)
        interest_zones = list(self._interest_manager.interest_zones)
        self.send_get_zones_objects(avatar_id, interest_zones)

    def handle_object_location_ack(self, di):
        do_id = di.get_uint32()

        old_parent_id = di.get_uint32()
        old_zone_id = di.get_uint32()

        new_parent_id = di.get_uint32()
        new_zone_id = di.get_uint32()

        if self._location_deferred_callback:
            self._location_deferred_callback.callback(do_id, old_parent_id, old_zone_id, new_parent_id, new_zone_id)

    def handle_object_get_zones_objects_resp(self, di):
        do_id = di.get_uint64()
        num_objects = di.get_uint16()
        for _ in xrange(num_objects):
            do_id = di.get_uint64()
            if self.has_seen_object(do_id):
                continue

            if do_id in self._owned_objects:
                continue

            self._pending_objects.append(do_id)

        if self._generate_deferred_callback:
            self._generate_deferred_callback.callback(False)

        if not num_objects:
            self._handle_interest_done()
            return

        if self.__interest_timeout_task:
            taskMgr.remove(self.__interest_timeout_task)
            self.__interest_timeout_task = None

        self.__interest_timeout_task = taskMgr.doMethodLater(self.network.interest_timeout,
            self._handle_interest_timeout,
            'interest-timeout-%d' % self.channel)

    def send_client_done_set_zone_resp(self, zone_id):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_DONE_SET_ZONE_RESP)
        datagram.add_uint16(zone_id)
        self.handle_send_datagram(datagram)

    def send_client_get_state_resp(self, zone_id):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_GET_STATE_RESP)
        datagram.pad_bytes(12)
        datagram.add_uint16(zone_id)
        self.handle_send_datagram(datagram)

    def handle_send_quiet_zone_resp(self, old_zone_id, new_zone_id):
        if not old_zone_id:
            self.send_client_done_set_zone_resp(new_zone_id)
        else:
            self.send_client_get_state_resp(new_zone_id)

        if old_zone_id and new_zone_id != OTP_ZONE_ID_OLD_QUIET_ZONE:
            self.send_client_done_set_zone_resp(new_zone_id)

    def handle_send_zone_resp(self, complete, old_zone_id, new_zone_id):
        if not complete:
            if not old_zone_id:
                self.send_client_done_set_zone_resp(new_zone_id)
            else:
                self.send_client_get_state_resp(new_zone_id)

        if old_zone_id and new_zone_id != OTP_ZONE_ID_OLD_QUIET_ZONE and complete:
            self.send_client_done_set_zone_resp(new_zone_id)

    def handle_set_zone_complete_callback(self, complete, old_parent_id, old_zone_id, new_parent_id, new_zone_id):
        if new_zone_id == OTP_ZONE_ID_OLD_QUIET_ZONE:
            if not complete:
                return

            self.handle_send_quiet_zone_resp(old_zone_id, new_zone_id)
        else:
            self.handle_send_zone_resp(complete, old_zone_id, new_zone_id)

    def handle_object_enter_owner(self, has_other, di):
        do_id = di.get_uint64()
        parent_id = di.get_uint64()
        zone_id = di.get_uint32()
        dc_id = di.get_uint16()

        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_GET_AVATAR_DETAILS_RESP)
        datagram.add_uint32(do_id)
        datagram.add_uint8(0)
        datagram.append_data(di.get_remaining_bytes())
        self.handle_send_datagram(datagram)

        self._owned_objects.append(do_id)

    def _handle_interest_done(self):
        if self.__interest_timeout_task:
            taskMgr.remove(self.__interest_timeout_task)
            self.__interest_timeout_task = None

        if self._generate_deferred_callback:
            self._generate_deferred_callback.callback(True)
            self._generate_deferred_callback.destroy()
            self._generate_deferred_callback = None

        self._pending_objects = []

    def _handle_interest_timeout(self, task):
        if len(self._pending_objects) > 0:
            self.notify.warning('Interest handle timed out for channel: %d, forcing completion...' % self.channel)

        self._handle_interest_done()
        return task.done

    def handle_object_enter_location(self, has_other, di):
        do_id = di.get_uint64()
        parent_id = di.get_uint64()
        zone_id = di.get_uint32()
        dc_id = di.get_uint16()

        if self.has_seen_object(do_id):
            return

        if do_id in self._owned_objects:
            return

        if not self._interest_manager.has_interest_zone(zone_id):
            return

        dclass = self.network.dc_loader.dclasses_by_number[dc_id]
        assert(dclass != None)

        # if there is a generate for the toon and it's zone is the quiet zone,
        # then we never allow that generate through...
        if dclass.get_name() == 'DistributedToon' and zone_id == OTP_ZONE_ID_OLD_QUIET_ZONE:
            return

        datagram = io.NetworkDatagram()
        if not has_other:
            datagram.add_uint16(types.CLIENT_CREATE_OBJECT_REQUIRED)
        else:
            datagram.add_uint16(types.CLIENT_CREATE_OBJECT_REQUIRED_OTHER)

        datagram.add_uint16(dc_id)
        datagram.add_uint32(do_id)
        datagram.append_data(di.get_remaining_bytes())
        self.handle_send_datagram(datagram)

        seen_objects = self._seen_objects.setdefault(zone_id, [])
        seen_objects.append(do_id)

        # check to see if we have a pending interest handle that is looking
        # to see when this object generate has arrived.
        if do_id in self._pending_objects:
            self._pending_objects.remove(do_id)

            # if we have no more pending objects left to add,
            # then the interest timeout handle is now complete.
            if not self._pending_objects:
                self._handle_interest_done()
                return

    def send_client_object_delete_resp(self, do_id):
        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_OBJECT_DELETE_RESP)
        datagram.add_uint32(do_id)
        self.handle_send_datagram(datagram)

        self.remove_seen_object(do_id)

    def handle_object_update_field(self, di):
        try:
            do_id = di.get_uint32()
            field_id = di.get_uint16()
        except:
            self.handle_send_disconnect(types.CLIENT_DISCONNECT_TRUNCATED_DATAGRAM,
                'Received truncated datagram from channel: %d!' % self._channel)

            return

        datagram = io.NetworkDatagram()
        datagram.add_header(do_id, self.channel,
            types.STATESERVER_OBJECT_UPDATE_FIELD)

        datagram.add_uint32(do_id)
        datagram.add_uint16(field_id)

        datagram.append_data(di.get_remaining_bytes())
        self.network.handle_send_connection_datagram(datagram)

    def handle_object_changing_location(self, di):
        do_id = di.get_uint32()
        new_parent_id = di.get_uint32()
        new_zone_id = di.get_uint32()

        if not self.has_seen_object(do_id):
            return

        if do_id in self._owned_objects:
            return

        if self._interest_manager.has_interest_zone(new_zone_id):
            return

        self.send_client_object_delete_resp(do_id)

    def handle_object_update_field_resp(self, di):
        do_id = di.get_uint32()
        field_id = di.get_uint16()

        # check to see if we either have seen this object's generate already,
        # or that the object is one of our owned objects...
        can_send_update = self.has_seen_object(do_id) or do_id in self._pending_objects or do_id in self._owned_objects
        if not can_send_update:
            return

        datagram = io.NetworkDatagram()
        datagram.add_uint16(types.CLIENT_OBJECT_UPDATE_FIELD_RESP)
        datagram.add_uint32(do_id)
        datagram.add_uint16(field_id)
        datagram.append_data(di.get_remaining_bytes())
        self.handle_send_datagram(datagram)

    def handle_object_delete_ram(self, di):
        do_id = di.get_uint32()
        if not self.has_seen_object(do_id):
            return

        if do_id in self._owned_objects:
            return

        self.send_client_object_delete_resp(do_id)

    def shutdown(self):
        if self.__interest_timeout_task:
            taskMgr.remove(self.__interest_timeout_task)
            self.__interest_timeout_task = None

        if self.network.account_manager.has_fsm(self.allocated_channel):
            self.network.account_manager.stop_operation(self)

        if self.allocated_channel:
            self.network.channel_allocator.free(self.allocated_channel)

        io.NetworkHandler.shutdown(self)

class ClientAgent(io.NetworkConnector, io.NetworkListener, component.Component):
    notify = notify.new_category('ClientAgent')

    def __init__(self, dc_loader):
        address = config.GetString('clientagent-address', '0.0.0.0')
        port = config.GetInt('clientagent-port', 6667)
        connect_address = config.GetString('clientagent-connect-address', '127.0.0.1')
        connect_port = config.GetInt('clientagent-connect-port', 7100)

        io.NetworkConnector.__init__(self, dc_loader, connect_address, connect_port)
        io.NetworkListener.__init__(self, address, port, Client)
        self._channel = config.GetInt('clientagent-channel', types.CLIENTAGENT_CHANNEL)

        min_channels = config.GetInt('clientagent-min-channels', 1000000000)
        max_channels = config.GetInt('clientagent-max-channels', 1009999999)

        self._channel_allocator = UniqueIdAllocator(min_channels, max_channels - 1)
        self._server_version = config.GetString('clientagent-version', 'no-version')
        self._server_hash_val = int(config.GetString('clientagent-hash-val', '0'))

        self._interest_timeout = config.GetFloat('clientagent-interest-timeout', 2.5)

        self._database_interface = util.DatabaseInterface(self)
        self._account_manager = ClientAccountManager(self)

    @property
    def channel_allocator(self):
        return self._channel_allocator

    @property
    def server_version(self):
        return self._server_version

    @property
    def server_hash_val(self):
        return self._server_hash_val

    @property
    def interest_timeout(self):
        return self._interest_timeout

    @property
    def database_interface(self):
        return self._database_interface

    @property
    def account_manager(self):
        return self._account_manager

    def setup(self):
        io.NetworkListener.setup(self)
        io.NetworkConnector.setup(self)

    def handle_datagram(self, channel, sender, message_type, di):
        handler = self.get_handler_from_channel(channel)
        if not handler:
            self.notify.debug('Cannot handle message type: %d '
                'for unknown channel: %d!' % (message_type, channel))

            return

        handler.handle_internal_datagram(message_type, sender, di)

    def shutdown(self):
        io.NetworkListener.shutdown(self)
        io.NetworkConnector.shutdown(self)
