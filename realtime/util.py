from panda3d.core import *
from panda3d.direct import *

from realtime import io
from realtime import types
from realtime.notifier import notify


class DatabaseInterface(object):
    notify = notify.new_category('NetworkDatabaseInterface')

    def __init__(self, network):
        self._network = network

        self._context = 0

        self._callbacks = {}
        self._dclasses = {}

    def get_context(self):
        self._context = (self._context + 1) & 0xFFFFFFFF
        return self._context

    def create_object(self, channel_id, database_id, dclass, fields={}, callback=None):
        """
        Create an object in the specified database.
        database_id specifies the control channel of the target database.
        dclass specifies the class of the object to be created.
        fields is a dict with any fields that should be stored in the object on creation.
        callback will be called with callback(do_id) if specified. On failure, do_id is 0.
        """

        # Save the callback:
        ctx = self.get_context()
        self._callbacks[ctx] = callback

        # Pack up/count valid fields.
        field_packer = DCPacker()
        field_count = 0
        for k,v in fields.items():
            field = dclass.get_field_by_name(k)
            if not field:
                self.notify.error('Creation request for %s object contains an invalid field named %s' % (
                    dclass.get_name(), k))

            field_packer.raw_pack_uint16(field.get_number())
            field_packer.begin_pack(field)
            field.pack_args(field_packer, v)
            field_packer.end_pack()
            field_count += 1

        # Now generate and send the datagram:
        dg = io.NetworkDatagram()
        dg.add_header(database_id, channel_id, types.DBSERVER_CREATE_OBJECT)
        dg.add_uint32(ctx)
        dg.add_uint16(dclass.get_number())
        dg.add_uint16(field_count)
        dg.append_data(field_packer.get_string())
        self._network.handle_send_connection_datagram(dg)

    def handle_create_object_resp(self, di):
        ctx = di.get_uint32()
        do_id = di.get_uint32()

        if ctx not in self._callbacks:
            self.notify.warning('Received unexpected DBSERVER_CREATE_OBJECT_RESP (ctx %d, do_id %d)' % (
                ctx, do_id))

            return

        if self._callbacks[ctx]:
            self._callbacks[ctx](do_id)

        del self._callbacks[ctx]

    def query_object(self, channel_id, database_id, do_id, callback, dclass=None, field_names=()):
        """
        Query object `do_id` out of the database.
        On success, the callback will be invoked as callback(dclass, fields)
        where dclass is a DCClass instance and fields is a dict.
        On failure, the callback will be invoked as callback(None, None).
        """

        # Save the callback:
        ctx = self.get_context()
        self._callbacks[ctx] = callback
        self._dclasses[ctx] = dclass

        # Generate and send the datagram:
        dg = io.NetworkDatagram()

        if not field_names:
            dg.add_header(database_id, channel_id, types.DBSERVER_OBJECT_GET_ALL)
        else:
            # We need a dclass in order to convert the field names into field IDs:
            assert dclass is not None

            if len(field_names) > 1:
                dg.add_header(database_id, channel_id, types.DBSERVER_OBJECT_GET_FIELDS)
            else:
                dg.add_header(database_id, channel_id, types.DBSERVER_OBJECT_GET_FIELD)

        dg.add_uint32(ctx)
        dg.add_uint32(do_id)
        if len(field_names) > 1:
            dg.add_uint16(len(field_names))

        for field_name in field_names:
            field = dclass.get_field_by_name(field_name)
            if field is None:
                self.notify.error('Bad field named %s in query for %s object' % (
                    field_name, dclass.get_name()))

            dg.add_uint16(field.get_number())

        self._network.handle_send_connection_datagram(dg)

    def handle_query_object_resp(self, message_type, di):
        ctx = di.get_uint32()
        success = di.get_uint8()

        if ctx not in self._callbacks:
            self.notify.warning('Received unexpected %s (ctx %d)' % (message_type, ctx))
            return

        try:
            if not success:
                if self._callbacks[ctx]:
                    self._callbacks[ctx](None, None)

                return

            if message_type == types.DBSERVER_OBJECT_GET_ALL_RESP:
                dclass_id = di.get_uint16()
                dclass = self._network.dc_loader.dclasses_by_number.get(dclass_id)
            else:
                dclass = self._dclasses[ctx]

            if not dclass:
                self.notify.error('Received bad dclass %d in DBSERVER_OBJECT_GET_ALL_RESP' % (
                    dclass_id))

            if message_type == types.DBSERVER_OBJECT_GET_FIELD_RESP:
                field_count = 1
            else:
                field_count = di.get_uint16()

            field_packer = DCPacker()
            field_packer.set_unpack_data(di.get_remaining_bytes())
            fields = {}
            for x in xrange(field_count):
                field_id = field_packer.raw_unpack_uint16()
                field = dclass.get_field_by_index(field_id)

                if not field:
                    self.notify.error('Received bad field %d in query for %s object' % (
                        field_id, dclass.get_name()))

                field_packer.begin_unpack(field)
                fields[field.get_name()] = field.unpack_args(field_packer)
                field_packer.end_unpack()

            if self._callbacks[ctx]:
                self._callbacks[ctx](dclass, fields)

        finally:
            del self._callbacks[ctx]
            del self._dclasses[ctx]

    def update_object(self, channel_id, database_id, do_id, dclass, new_fields, old_fields=None, callback=None):
        """
        Update field(s) on an object, optionally with the requirement that the
        fields must match some old value.
        database_id and do_id represent the database control channel and object ID
        for the update request.
        new_fields is to be a dict of fieldname->value, representing the fields
        to add/change on the database object.
        old_fields, if specified, is a similarly-formatted dict that contains the
        expected older values. If the values do not match, the database will
        refuse to process the update. This is useful for guarding against race
        conditions.
        On success, the callback is called as callback(None).
        On failure, the callback is called as callback(dict), where dict contains
        the current object values. This is so that the updater can try again,
        basing its updates off of the new values.
        """

        # Ensure that the keys in new_fields and old_fields are the same if
        # old_fields is given...
        if old_fields is not None:
            if set(new_fields.keys()) != set(old_fields.keys()):
                self.notify.error('new_fields and old_fields must contain the same keys!')
                return

        field_packer = DCPacker()
        field_count = 0
        for k,v in new_fields.items():
            field = dclass.get_field_by_name(k)
            if not field:
                self.notify.error('Update for %s(%d) object contains invalid field named %s' % (
                    dclass.get_name(), do_id, k))

            field_packer.raw_pack_uint16(field.get_number())

            if old_fields is not None:
                # Pack the old values:
                field_packer.begin_pack(field)
                field.pack_args(field_packer, old_fields[k])
                field_packer.end_pack()

            field_packer.begin_pack(field)
            field.pack_args(field_packer, v)
            field_packer.end_pack()
            field_count += 1

        # Generate and send the datagram:
        dg = io.NetworkDatagram()
        if old_fields is not None:
            ctx = self.get_context()
            self._callbacks[ctx] = callback
            if field_count == 1:
                dg.add_header(database_id, channel_id, types.DBSERVER_OBJECT_SET_FIELD_IF_EQUALS)
            else:
                dg.add_header(database_id, channel_id, types.DBSERVER_OBJECT_SET_FIELDS_IF_EQUALS)

            dg.add_uint32(ctx)
        else:
            if field_count == 1:
                dg.add_header(database_id, channel_id, types.DBSERVER_OBJECT_SET_FIELD)
            else:
                dg.add_header(database_id, channel_id, types.DBSERVER_OBJECT_SET_FIELDS)

        dg.add_uint32(do_id)
        if field_count != 1:
            dg.add_uint16(field_count)

        dg.append_data(field_packer.getString())
        self._network.handle_send_connection_datagram(dg)

        if old_fields is None and callback is not None:
            # Why oh why did they ask for a callback if there's no old_fields?
            # Oh well, better honor their request:
            callback(None)

    def handle_update_object_resp(self, di, multi):
        ctx = di.get_uint32()
        success = di.get_uint8()

        if ctx not in self._callbacks:
            self.notify.warning('Received unexpected DBSERVER_OBJECT_SET_FIELD(S)_IF_EQUALS_RESP (ctx %d)' % (
                ctx))

            return

        try:
            if success:
                if self._callbacks[ctx]:
                    self._callbacks[ctx](None)

                return

            if not di.get_remaining_size():
                # We failed due to other reasons.
                if self._callbacks[ctx]:
                    return self._callbacks[ctx]({})

            if multi:
                field_count = di.get_uint16()
            else:
                field_count = 1

            field_packer = DCPacker()
            field_packer.set_unpack_data(di.get_remaining_bytes())
            fields = {}
            for x in xrange(field_count):
                fieldId = field_packer.raw_pack_uint16()
                field = self._network.dc_loader.dc_file.get_field_by_index(fieldId)

                if not field:
                    self.notify.error('Received bad field %d in update failure response message' % (
                        fieldId))

                field_packer.begin_unpack(field)
                fields[field.get_name()] = field.unpack_args(field_packer)
                field_packer.end_unpack()

            if self._callbacks[ctx]:
                self._callbacks[ctx](fields)

        finally:
            del self._callbacks[ctx]

    def handle_datagram(self, message_type, di):
        if message_type == types.DBSERVER_CREATE_OBJECT_RESP:
            self.handle_create_object_resp(di)
        elif message_type in (types.DBSERVER_OBJECT_GET_ALL_RESP,
                              types.DBSERVER_OBJECT_GET_FIELDS_RESP,
                              types.DBSERVER_OBJECT_GET_FIELD_RESP):
            self.handle_query_object_resp(message_type, di)
        elif message_type == types.DBSERVER_OBJECT_SET_FIELD_IF_EQUALS_RESP:
            self.handle_update_object_resp(di, False)
        elif message_type == types.DBSERVER_OBJECT_SET_FIELDS_IF_EQUALS_RESP:
            self.handle_update_object_resp(di, True)

class DeferredCallback(object):
    """
    A class that represents a pending callback event when called
    it initiates the callback event with the specified arguments
    """

    def __init__(self, function, *args, **kwargs):
        assert(callable(function))
        self._function = function
        self._args = args
        self._kwargs = kwargs

    def callback(self, *args, **kwargs):
        cb_args = []
        cb_args.extend(args)
        cb_args.extend(self._args)

        cb_kwargs = dict(kwargs.items() + self._kwargs.items())

        result = self._function(*cb_args, **cb_kwargs)

        del cb_args
        del cb_kwargs

        return result

    def destroy(self):
        self._function = None
        self._args = None
        self._kwargs = None
