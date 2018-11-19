"""
 * Copyright (C) Caleb Marshall - All Rights Reserved
 * Written by Caleb Marshall <anythingtechpro@gmail.com>, August 17th, 2017
 * Contributed to by Prince Frizzy <theclashingfritz@gmail.com>, June 21st, 2018
 * Licensing information can found in 'LICENSE', which is part of this source code package.
"""

import copy
import collections

from panda3d.direct import *

from realtime import io
from realtime import types
from realtime.notifier import notify

from game.OtpDoGlobals import *
from game import ZoneUtil


class Shard(object):

    def __init__(self, channel, name, population):
        self.channel = channel
        self.name = name
        self.population = population


class ShardManager(object):

    def __init__(self):
        self.shards = {}

    def has_shard(self, channel):
        return channel in self.shards

    def add_shard(self, channel, name, population):
        if self.has_shard(channel):
            return

        shard = Shard(channel, name, population)
        self.shards[channel] = shard
        return shard

    def remove_shard(self, shard):
        if not self.has_shard(shard.channel):
            return

        del self.shards[shard.channel]

    def get_shard(self, channel):
        return self.shards.get(channel)


class StateObjectInterests(object):

    def __init__(self):
        self.old_interests = {}
        self.interests = {}

    def had_parent_interest(self, parent_id):
        return parent_id in self.old_interests

    def had_zone_interest(self, parent_id, zone_id):
        return self.had_parent_interest(parent_id) and zone_id in self.old_interests[parent_id]

    def has_parent_interest(self, parent_id):
        return parent_id in self.interests

    def has_zone_interest(self, parent_id, zone_id):
        return self.has_parent_interest(parent_id) and zone_id in self.interests[parent_id]

    def add_interest(self, parent_id, zone_id):
        interest = self.interests.setdefault(parent_id, [])
        if zone_id in interest:
            return

        interest.append(zone_id)

    def remove_interest(self, parent_id, zone_id=None):
        interest = self.interests.get(parent_id)
        if not interest:
            return

        if zone_id is not None:
            if zone_id not in interest:
                return

            self.update_interest()
            interest.remove(zone_id)
        else:
            self.update_interest()
            del self.interests[parent_id]

    def update_interest(self):
        self.old_interests = {}
        self.old_interests = copy.deepcopy(self.interests)

    def clear_zone_interest(self, parent_id):
        if not self.has_parent_interest(parent_id):
            return

        self.update_interest()
        self.interests[parent_id] = []

    def clear_parent_interest(self):
        self.update_interest()
        self.interests = {}


class StateObject(object):
    notify = notify.new_category('StateObject')

    def __init__(self, network, object_manager, do_id, parent_id, zone_id, dc_class, has_other, di):
        self._network = network
        self.object_manager = object_manager

        self._do_id = do_id

        self._old_owner_id = 0
        self._owner_id = 0

        self._old_parent_id = 0
        self._parent_id = parent_id

        self._old_zone_id = 0
        self._zone_id = zone_id

        self._dc_class = dc_class
        self._has_other = has_other

        self._required_fields = {}
        self._other_fields = {}

        self.interest_set = StateObjectInterests()

        field_packer = DCPacker()
        field_packer.set_unpack_data(di.get_remaining_bytes())

        for field_index in xrange(self._dc_class.get_num_inherited_fields()):
            field = self._dc_class.get_inherited_field(field_index)
            if not field:
                self.notify.error('Failed to unpack required field: %d '
                    'dclass: %s, unknown field!' % (field_index, self._dc_class.get_name()))

            if not field.is_required():
                continue

            field_packer.begin_unpack(field)
            field_args = field.unpack_args(field_packer)
            field_packer.end_unpack()

            self._required_fields[field.get_number()] = field_args

        self._required_fields = collections.OrderedDict(sorted(
            self._required_fields.items()))

        if self._has_other:
            num_fields = field_packer.raw_unpack_uint16()
            for _ in xrange(num_fields):
                field_id = field_packer.raw_unpack_uint16()
                field = self._dc_class.get_field_by_index(field_id)
                if not field:
                    self.notify.error('Failed to unpack other field: %d '
                        'dclass: %s, unknown field!' % (field_id, self._dc_class.get_name()))

                if not field.is_ram():
                    continue

                field_packer.begin_unpack(field)
                field_args = field.unpack_args(field_packer)
                field_packer.end_unpack()

                self._other_fields[field.get_number()] = field_args

        self._other_fields = collections.OrderedDict(sorted(
            self._other_fields.items()))

        self._network.register_for_channel(self._do_id)

    @property
    def do_id(self):
        return self._do_id

    @property
    def old_owner_id(self):
        return self._old_owner_id

    @property
    def owner_id(self):
        return self._owner_id

    @owner_id.setter
    def owner_id(self, owner_id):
        self._old_owner_id = self._owner_id
        self._owner_id = owner_id

    @property
    def old_parent_id(self):
        return self._old_parent_id

    @property
    def parent_id(self):
        return self._parent_id

    @parent_id.setter
    def parent_id(self, parent_id):
        self._old_parent_id = self._parent_id
        self._parent_id = parent_id

    @property
    def old_zone_id(self):
        return self._old_zone_id

    @property
    def zone_id(self):
        return self._zone_id

    @zone_id.setter
    def zone_id(self, zone_id):
        self._old_zone_id = self._zone_id
        self._zone_id = zone_id

    @property
    def dc_class(self):
        return self._dc_class

    @property
    def has_other(self):
        return self._has_other

    def append_required_data(self, datagram, broadcast_only=True):
        field_packer = DCPacker()
        for field_index in self._required_fields:
            field = self._dc_class.get_field_by_index(field_index)
            if not field:
                self.notify.error('Failed to append required data for field: %d '
                    'dclass: %s, unknown field!' % (field_index, self._dc_class.get_name()))

            if broadcast_only and not field.is_broadcast():
                continue

            field_packer.begin_pack(field)
            field.pack_args(field_packer, self._required_fields[field_index])
            field_packer.end_pack()

        datagram.append_data(field_packer.get_string())

    def append_other_data(self, datagram):
        field_packer = DCPacker()
        for field_index in self._other_fields:
            field = self._dc_class.get_field_by_index(field_index)
            if not field:
                self.notify.error('Failed to append other data for field: %d '
                    'dclass: %s, unknown field!' % (field_index, self._dc_class.get_name()))

            field_packer.raw_pack_uint16(field.get_number())
            field_packer.begin_pack(field)
            field.pack_args(field_packer, self._other_fields[field_index])
            field_packer.end_pack()

        datagram.add_uint16(len(self._other_fields))
        datagram.append_data(field_packer.get_string())

    def get_in_street_branch(self, zone_id=None):
        if not zone_id:
            zone_id = self._zone_id

        if not ZoneUtil.isPlayground(zone_id):
            where = ZoneUtil.getWhereName(zone_id, True)

            if where == 'street':
                return True

        return False

    def setup(self):
        self.object_manager.handle_changing_location(self)

    def handle_internal_datagram(self, sender, message_type, di):
        if message_type == types.STATESERVER_OBJECT_SET_OWNER:
            self.handle_set_owner(sender, di)
        elif message_type == types.STATESERVER_OBJECT_SET_AI:
            self.handle_set_ai(sender, di)
        elif message_type == types.STATESERVER_OBJECT_SET_ZONE:
            self.handle_set_zone(sender, di)
        elif message_type == types.STATESERVER_OBJECT_CHANGING_LOCATION:
            self.handle_changing_location(sender, di)
        else:
            self.notify.warning('Received unknown message type: %d '
                'for object %d!' % (message_type, self._do_id))

            return

    def handle_send_changing_owner(self, channel, old_owner_id, new_owner_id):
        datagram = io.NetworkDatagram()
        datagram.add_header(channel, self._do_id,
            types.STATESERVER_OBJECT_CHANGING_OWNER)

        datagram.add_uint64(self._do_id)
        datagram.add_uint64(new_owner_id)
        datagram.add_uint64(old_owner_id)
        self._network.handle_send_connection_datagram(datagram)

    def handle_send_owner_entry(self, channel):
        datagram = io.NetworkDatagram()
        if not self._has_other:
            datagram.add_header(channel, self._do_id,
                types.STATESERVER_OBJECT_ENTER_OWNER_WITH_REQUIRED)
        else:
            datagram.add_header(channel, self._do_id,
                types.STATESERVER_OBJECT_ENTER_OWNER_WITH_REQUIRED_OTHER)

        datagram.add_uint64(self._do_id)
        datagram.add_uint64(self._parent_id)
        datagram.add_uint32(self._zone_id)
        datagram.add_uint16(self._dc_class.get_number())

        self.append_required_data(datagram, broadcast_only=False)

        if self._has_other:
            self.append_other_data(datagram)

        self._network.handle_send_connection_datagram(datagram)

    def handle_set_owner(self, sender, di):
        new_owner_id = di.get_uint64()
        if new_owner_id == self._owner_id:
            self.notify.warning('Failed to set new owner: %d for object %d, '
                'object did not change owners!' % (new_owner_id, self._do_id))

            return

        self.owner_id = new_owner_id
        if self._old_owner_id:
            self.handle_send_changing_owner(self._old_owner_id, self._old_owner_id,
                self._owner_id)

        if self._owner_id:
            self.handle_send_owner_entry(self._owner_id)

    def handle_send_changing_ai(self, channel, old_parent_id, new_parent_id):
        datagram = io.NetworkDatagram()
        datagram.add_header(channel, self._do_id,
            types.STATESERVER_OBJECT_CHANGING_AI)

        datagram.add_uint64(self._do_id)
        datagram.add_uint64(old_parent_id)
        datagram.add_uint64(new_parent_id)
        self._network.handle_send_connection_datagram(datagram)

    def handle_send_ai_entry(self, channel):
        datagram = io.NetworkDatagram()

        if not self._has_other:
            datagram.add_header(channel, self._do_id,
                types.STATESERVER_OBJECT_ENTER_AI_WITH_REQUIRED)
        else:
            datagram.add_header(channel, self._do_id,
                types.STATESERVER_OBJECT_ENTER_AI_WITH_REQUIRED_OTHER)

        datagram.add_uint64(self._do_id)
        datagram.add_uint64(self._parent_id)
        datagram.add_uint32(self._zone_id)
        datagram.add_uint16(self._dc_class.get_number())

        self.append_required_data(datagram, broadcast_only=not self._owner_id)

        if self._has_other:
            self.append_other_data(datagram)

        self._network.handle_send_connection_datagram(datagram)

    def handle_set_ai_callback(self, sender):
        datagram = io.NetworkDatagram()
        datagram.add_header(sender, self._do_id,
            types.STATESERVER_OBJECT_SET_AI_RESP)

        self._network.handle_send_connection_datagram(datagram)

    def handle_set_ai(self, sender, di):
        new_parent_id = di.get_uint64()
        if new_parent_id == self._parent_id:
            self.notify.debug('Failed to set new parent: %d for object %d, '
                'object did not change parents!' % (new_parent_id, self._do_id))

            return

        self.parent_id = new_parent_id
        if self._old_parent_id:
            self.handle_send_changing_ai(self._old_parent_id, self._old_parent_id,
                self._parent_id)

            self.interest_set.remove_interest(self._old_parent_id)

        if self._parent_id:
            self.handle_send_ai_entry(self._parent_id)
            self.interest_set.add_interest(self._parent_id, OTP_ZONE_ID_OLD_QUIET_ZONE)

        # the client can send set ai for it's owned object,
        # it will expect a response from us...
        if self._owner_id:
            self.handle_set_ai_callback(self._owner_id)

    def handle_send_changing_location(self, channel):
        datagram = io.NetworkDatagram()
        datagram.add_header(channel, self._do_id,
            types.STATESERVER_OBJECT_CHANGING_LOCATION)

        datagram.add_uint32(self._do_id)
        datagram.add_uint32(self._parent_id)
        datagram.add_uint32(self._zone_id)
        self._network.handle_send_connection_datagram(datagram)

    def handle_send_set_zone_callback(self, channel, old_zone_id, new_zone_id, zone_change_complete=False):
        datagram = io.NetworkDatagram()
        datagram.add_header(channel, self._do_id,
            types.STATESERVER_OBJECT_SET_ZONE_RESP)

        datagram.add_uint32(old_zone_id)
        datagram.add_uint32(new_zone_id)
        datagram.add_uint8(zone_change_complete)
        self._network.handle_send_connection_datagram(datagram)

    def handle_set_zone(self, sender, di):
        new_zone_id = di.get_uint32()

        self.parent_id = self._parent_id
        self.zone_id = new_zone_id

        if self._old_zone_id:
            self.interest_set.remove_interest(self._parent_id, self._old_zone_id)

            # remove street branch interest
            if self.get_in_street_branch(self._old_zone_id):
                self.interest_set.remove_interest(self._parent_id, ZoneUtil.getBranchZone(self._old_zone_id))

            self.handle_send_changing_location(self._parent_id)
            self.object_manager.handle_changing_location(self)

        # the client can send set zone for it's owned object,
        # it will expect a response from us...
        if self._owner_id:
            # send the quiet zone objects before sending the zone objects,
            # this is how the client expects generation order...
            if self._zone_id == OTP_ZONE_ID_OLD_QUIET_ZONE:
                self.object_manager.handle_changing_location(self)

            self.handle_send_set_zone_callback(self._owner_id, self._old_zone_id, self._zone_id)

        if self._zone_id and self._zone_id != OTP_ZONE_ID_OLD_QUIET_ZONE:
            self.interest_set.add_interest(self._parent_id, self._zone_id)

            # add street branch interest
            if self.get_in_street_branch(self._zone_id):
                self.interest_set.add_interest(self._parent_id, ZoneUtil.getBranchZone(self._zone_id))

            self.interest_set.add_interest(self._parent_id, OTP_ZONE_ID_OLD_QUIET_ZONE)
            self.object_manager.handle_changing_location(self)

        # we must send the zone callback again to tell the client,
        # that all of the objects from the last zone message have been generated...
        if self._owner_id:
            self.handle_send_set_zone_callback(self._owner_id, self._old_zone_id, self._zone_id,
                zone_change_complete=True)

    def handle_send_location_entry(self, channel):
        datagram = io.NetworkDatagram()
        if not self._has_other:
            datagram.add_header(channel, self._do_id,
                types.STATESERVER_OBJECT_ENTER_LOCATION_WITH_REQUIRED)
        else:
            datagram.add_header(channel, self._do_id,
                types.STATESERVER_OBJECT_ENTER_LOCATION_WITH_REQUIRED_OTHER)

        datagram.add_uint64(self._do_id)
        datagram.add_uint64(self._parent_id)
        datagram.add_uint32(self._zone_id)
        datagram.add_uint16(self._dc_class.get_number())

        self.append_required_data(datagram)
        if self._has_other:
            self.append_other_data(datagram)

        self._network.handle_send_connection_datagram(datagram)

    def handle_send_departure(self, channel):
        datagram = io.NetworkDatagram()
        datagram.add_header(channel, self._do_id,
            types.STATESERVER_OBJECT_DELETE_RAM)

        datagram.add_uint32(self._do_id)
        self._network.handle_send_connection_datagram(datagram)

    def handle_changing_location(self, sender, di):
        new_parent_id = di.get_uint32()
        new_zone_id = di.get_uint32()

        if new_parent_id == self._parent_id:
            self.notify.debug('Failed to move to parent: %d for object: %d, '
                'object did not change parents!' % (new_parent_id, self._do_id))

            return

        if new_zone_id == self._zone_id:
            self.notify.debug('Failed to move to zone: %d for object: %d, '
                'object did not change zones!' % (new_zone_id, self._do_id))

            return

        self.parent_id = new_parent_id
        self.zone_id = new_zone_id

        self.object_manager.handle_changing_location(self)

    def handle_send_update_field(self, channel, sender, field, field_args):
        datagram = io.NetworkDatagram()
        datagram.add_header(channel, sender,
            types.STATESERVER_OBJECT_UPDATE_FIELD)

        datagram.add_uint32(self._do_id)
        datagram.add_uint16(field.get_number())

        field_packer = DCPacker()
        field_packer.begin_pack(field)

        if field_args is not None:
            field.pack_args(field_packer, field_args)

        field_packer.end_pack()

        datagram.append_data(field_packer.get_string())
        self._network.handle_send_connection_datagram(datagram)

    def handle_send_save_field(self, field, field_args):
        datagram = io.NetworkDatagram()
        datagram.add_header(types.DATABASE_CHANNEL, self._do_id,
            types.DBSERVER_OBJECT_SET_FIELD)

        datagram.add_uint32(self._do_id)

        field_packer = DCPacker()
        field_packer.raw_pack_uint16(field.get_number())
        field_packer.begin_pack(field)
        field.pack_args(field_packer, field_args)
        field_packer.end_pack()

        datagram.append_data(field_packer.get_string())
        self._network.handle_send_connection_datagram(datagram)

    def handle_update_field(self, channel, sender, di):
        field_id = di.get_uint16()
        field = self._dc_class.get_field_by_index(field_id)
        if not field:
            self.notify.warning('Failed to update field: %d dclass: %s, '
                'unknown field!' % (field_id, self._dc_class.get_name()))

            return

        datagram = io.NetworkDatagram()
        datagram.append_data(di.get_remaining_bytes())
        di = io.NetworkDatagramIterator(datagram)

        # if the iterator is empty, this means that the field
        # has no arguents and that we should not attempt to update it...
        if di.get_remaining_size():
            field_packer = DCPacker()
            field_packer.set_unpack_data(di.get_remaining_bytes())

            try:
                field_packer.begin_unpack(field)
                field_args = field.unpack_args(field_packer)
                field_packer.end_unpack()
            except RuntimeError:
                # apparently we failed to unpack the arguments for
                # this field we recieved, ignore the update...
                return
        else:
            field_args = None

        di = io.NetworkDatagramIterator(datagram)
        if field.is_bogus_field():
            self.notify.warning('Cannot handle field update for field: %s dclass: %s, field is bogus!' % (
                field.get_name(), self._dc_class.get_name()))

            return

        if not self._network.shard_manager.has_shard(sender):
            avatar_id = self._network.get_avatar_id_from_connection_channel(sender)

            if not avatar_id:
                self.notify.warning('Cannot handle field update for field: %s dclass: %s, '
                    'unknown avatar: %d!' % (field.get_name(), self._dc_class.get_name(), avatar_id))

                return

            # check to ensure the client can send this field, if the field
            # is marked ownsend; the field can only be sent by the owner of the object,
            # if the field is marked clsend the field is sendable always. Otherwise
            # if the client sends the field and it is not marked either of these,
            # the field update is invalid and the field is not sendable by a client...
            if field.is_ownsend():
                if sender != self._owner_id:
                    self.notify.warning('Cannot handle field update for field: %s '
                        'dclass: %s, field not sendable!' % (field.get_name(), self._dc_class.get_name()))

                    return
            else:
                if not field.is_clsend():
                    self.notify.warning('Cannot handle field update for field: %s '
                        'dclass: %s, field not sendable!' % (field.get_name(), self._dc_class.get_name()))

                    return

            # we must always send this update to the other receiver,
            # so that they get the field update always even if the field
            # is broadcasted to other objects in the same interest...
            self.handle_send_update_field(self._parent_id, sender, field, field_args)

            # if the field is marked broadcast, then we can proceed to broadcast
            # this field to any other objects in our interest.
            if field.is_broadcast():
                self.object_manager.handle_updating_field(self, sender, field, field_args,
                    excludes=[avatar_id])

            # the client has sent an broadcast field that is marked ram,
            # store this field since it passes both the isclsend or isownsend tests...
            if field_args is not None and field.is_ram():
                # ensure the object the client sent the field update for
                # has other fields...
                if not self._has_other:
                    return

                # check to see if this field is a required field, if it is then
                # this means it should be stored as a required field....
                if field.is_required():
                    self._required_fields[field.get_number()] = field_args
                else:
                    self._other_fields[field.get_number()] = field_args
        else:
            # we must always send this update to the other receiver,
            # so that they get the field update always even if the field
            # is broadcasted to other objects in the same interest...
            self.handle_send_update_field(self._owner_id, self._parent_id, field, field_args)

            # if the field is marked broadcast, then we can proceed to broadcast
            # this field to any other objects in our interest.
            if field.is_broadcast():
                self.object_manager.handle_updating_field(self, self._parent_id, field, field_args,
                    excludes=[self._do_id])

            # if the AI object sends specifically other (ram) fields for this object,
            # this means the object now has other fields...
            if field_args is not None and field.is_ram():
                # check to see if this field is a required field, if it is then
                # this means it should be stored as a required field....
                if field.is_required():
                    self._required_fields[field.get_number()] = field_args
                else:
                    self._other_fields[field.get_number()] = field_args

                # the object now has other fields, let's update the object's has_other
                # value so that generates will be sent including the other fields...
                self._has_other = True

            # check to see if the field is marked db, this means that we send the field
            # to the database to override any current fields with that value...
            if field_args is not None and field.is_db():
                self.handle_send_save_field(field, field_args)

    def destroy(self):
        self.interest_set.clear_parent_interest()
        self.handle_send_departure(self._parent_id)
        self.object_manager.handle_changing_location(self, force_delete=not self._owner_id)

class StateObjectManager(object):
    notify = notify.new_category('StateObjectManager')

    def __init__(self):
        self.objects = {}

    def has_object(self, do_id):
        return do_id in self.objects

    def add_object(self, state_object):
        if self.has_object(state_object.do_id):
            return

        self.objects[state_object.do_id] = state_object
        state_object.setup()

    def remove_object(self, state_object):
        if not self.has_object(state_object.do_id):
            return

        state_object.destroy()
        del self.objects[state_object.do_id]

    def get_object(self, do_id):
        return self.objects.get(do_id)

    def handle_changing_location(self, state_object, everyone_else=True, force_delete=False):
        for other_object in list(self.objects.values()):
            if other_object.do_id == state_object.do_id and everyone_else:
                continue

            if state_object.owner_id:
                if state_object.interest_set.has_parent_interest(other_object.parent_id) and state_object.interest_set.has_zone_interest(other_object.parent_id, other_object.zone_id):
                    other_object.handle_send_location_entry(state_object.owner_id)
                    if other_object.owner_id:
                        state_object.handle_send_location_entry(other_object.owner_id)
                elif state_object.interest_set.had_parent_interest(other_object.parent_id) and state_object.interest_set.had_zone_interest(other_object.parent_id, other_object.zone_id):
                    other_object.handle_send_departure(state_object.owner_id)
                    if other_object.owner_id:
                        state_object.handle_send_departure(other_object.owner_id)
            else:
                if not other_object.owner_id:
                    continue

                if other_object.interest_set.has_parent_interest(state_object.parent_id) and other_object.interest_set.has_zone_interest(state_object.parent_id, state_object.zone_id):
                    # if object has interest and force delete is true, then let's assume
                    # they still want to delete this AI object, because in some cases the avatar
                    # can be present when the AI want's to delete it's object from their scope...
                    if force_delete:
                        state_object.handle_send_departure(other_object.owner_id)
                    else:
                        state_object.handle_send_location_entry(other_object.owner_id)
                elif other_object.interest_set.had_parent_interest(state_object.parent_id) and other_object.interest_set.had_zone_interest(state_object.parent_id, state_object.zone_id):
                    state_object.handle_send_departure(other_object.owner_id)

    def handle_updating_field(self, state_object, sender, field, field_args, excludes=[]):
        for other_object in list(self.objects.values()):
            if other_object.do_id in excludes:
                continue

            if not other_object.owner_id:
                continue

            if other_object.interest_set.has_parent_interest(state_object.parent_id) and other_object.interest_set.has_zone_interest(state_object.parent_id, state_object.zone_id):
                state_object.handle_send_update_field(other_object.owner_id, sender, field, field_args)


class StateServer(io.NetworkConnector):
    notify = notify.new_category('StateServer')

    def __init__(self, *args, **kwargs):
        io.NetworkConnector.__init__(self, *args, **kwargs)

        self.shard_manager = ShardManager()
        self.object_manager = StateObjectManager()

    def handle_datagram(self, channel, sender, message_type, di):
        if message_type == types.STATESERVER_ADD_SHARD:
            self.handle_add_shard(sender, di)
        elif message_type == types.STATESERVER_UPDATE_SHARD:
            self.handle_update_shard(sender, di)
        elif message_type == types.STATESERVER_REMOVE_SHARD:
            self.handle_remove_shard(sender)
        elif message_type == types.STATESERVER_GET_SHARD_ALL:
            self.handle_get_shard_list(sender)
        elif message_type == types.STATESERVER_OBJECT_GENERATE_WITH_REQUIRED:
            self.handle_generate(sender, False, di)
        elif message_type == types.STATESERVER_OBJECT_GENERATE_WITH_REQUIRED_OTHER:
            self.handle_generate(sender, True, di)
        elif message_type == types.STATESERVER_OBJECT_UPDATE_FIELD:
            self.handle_object_update_field(channel, sender, di)
        elif message_type == types.STATESERVER_OBJECT_DELETE_RAM:
            self.handle_delete_object(sender, di)
        else:
            self.handle_object_datagram(channel, sender, message_type, di)

    def handle_object_datagram(self, channel, sender, message_type, di):
        state_object = self.object_manager.get_object(channel)
        if not state_object:
            self.notify.debug('Received an unknown message type: '
                '%d from channel: %d!' % (message_type, sender))

            return

        state_object.handle_internal_datagram(sender, message_type, di)

    def handle_add_shard(self, sender, di):
        shard = self.shard_manager.add_shard(sender, di.getString(), di.get_uint32())
        self.handle_send_update_shard(shard)

    def handle_update_shard(self, sender, di):
        shard = self.shard_manager.get_shard(sender)
        if not shard:
            self.notify.warning('Cannot update shard: %d, does not exist!' % sender)
            return

        shard.name = di.get_string()
        shard.population = di.get_uint32()

        self.handle_send_update_shard(shard, only_children=True)

    def handle_remove_shard(self, sender):
        shard = self.shard_manager.get_shard(sender)
        if not shard:
            self.notify.warning('Cannot remove shard: %d, does not exist!' % sender)
            return

        self.handle_delete_shard_objects(shard)

    def handle_send_update_shard(self, shard, only_children=False):
        for state_object in list(self.object_manager.objects.values()):
            if not state_object.owner_id:
                continue

            if state_object.parent_id != shard.channel and only_children:
                continue

            self.handle_get_shard_list(state_object.owner_id)

    def handle_delete_shard_objects(self, shard):
        for state_object in list(self.object_manager.objects.values()):
            if not state_object.owner_id:
                continue

            if state_object.parent_id != shard.channel:
                continue

            # if this object is owned and since this shard is closed,
            # send a disconnect to the client agent to be bounced back to the client.
            if state_object.owner_id:
                self.handle_send_disconnect(state_object.owner_id, shard)

            self.object_manager.remove_object(state_object)

        self.handle_send_update_shard(shard)
        self.shard_manager.remove_shard(shard)

    def handle_send_disconnect(self, channel, shard):
        datagram = io.NetworkDatagram()
        datagram.add_header(channel, self.channel,
            types.CLIENTAGENT_DISCONNECT)

        datagram.add_uint16(types.CLIENT_DISCONNECT_SHARD_CLOSED)
        datagram.add_string('Shard with channel: %d has been terminated!' % shard.channel)
        self.handle_send_connection_datagram(datagram)

    def handle_get_shard_list(self, sender):
        datagram = io.NetworkDatagram()
        datagram.add_header(sender, self.channel,
            types.STATESERVER_GET_SHARD_ALL_RESP)

        datagram.add_uint16(len(self.shard_manager.shards))
        for shard in list(self.shard_manager.shards.values()):
            datagram.add_uint32(shard.channel)
            datagram.add_string(shard.name)
            datagram.add_uint32(shard.population)

        self.handle_send_connection_datagram(datagram)

    def handle_generate(self, sender, has_other, di):
        do_id = di.get_uint32()
        parent_id = di.get_uint32()
        zone_id = di.get_uint32()
        dc_id = di.get_uint16()

        if self.object_manager.has_object(do_id):
            self.notify.info('Failed to generate an already existing object with do_id: %d!' % do_id)
            return

        dc_class = self.dc_loader.dclasses_by_number.get(dc_id)
        if not dc_class:
            self.notify.warning('Failed to generate an object with do_id: %d, '
                'no dclass found for dc_id: %d!' % do_id, dc_id)

            return

        state_object = StateObject(self, self.object_manager, do_id, parent_id,
            zone_id, dc_class, has_other, di)

        self.object_manager.add_object(state_object)

    def handle_object_update_field(self, channel, sender, di):
        do_id = di.get_uint32()
        if not di.get_remaining_size():
            self.notify.warning('Cannot handle an field update for object: %d, truncated datagram!' % do_id)
            return

        state_object = self.object_manager.get_object(do_id)
        if not state_object:
            self.notify.debug('Cannot handle an field update for object: %d, unknown object!' % do_id)
            return

        state_object.handle_update_field(channel, sender, di)

    def handle_delete_object(self, sender, di):
        do_id = di.get_uint32()
        state_object = self.object_manager.get_object(do_id)
        if not state_object:
            self.notify.debug('Failed to delete object: %d, object does not exist!' % do_id)
            return

        self.object_manager.remove_object(state_object)
