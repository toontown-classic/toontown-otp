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

import os
import collections
import threading

import simplejson
import yaml
import pytoml

from panda3d.core import *
from panda3d.direct import *

from direct.fsm.FSM import FSM

from realtime import io
from realtime import types
from realtime.notifier import notify
from realtime import component


class DatabaseError(RuntimeError):
    """
    An database specific runtime error
    """

class DatabaseFile(object):
    """
    An file object that represents a file in memory,
    containing all of the valid fields...
    """

    def __init__(self, database_manager):
        self._database_manager = database_manager
        self._filename = None
        self._data = {}
        self._file_lock = threading.RLock()

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, filename):
        assert(filename != self._filename)
        self._filename = filename

    @property
    def filepath(self):
        return self._database_manager.get_filepath(self._filename)

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, data):
        assert(isinstance(data, dict))
        self._data = data

    def setup(self):
        """
        Initializes the file object and reads it's values from disk.
        """

        if os.path.exists(self.filepath):
            self.load()

    def has_value(self, key):
        """
        Returns true if the key is in the dictionary else false.
        """

        return key in self._data

    def set_value(self, key, value):
        """
        Sets the key assigned to the value in the dictionary.
        """

        self._data[key] = value
        self.save()

    def set_default_value(self, key, default_value):
        """
        Returns the value if the key exists in the dictionary else,
        returns the default_value and places the default_value in the dictionary
        assigned to as the specified key...
        """

        if self.has_value(key):
            return self.get_value(key)

        self.set_value(key, default_value)
        return default_value

    def get_value(self, key):
        """
        Gets the value from the key within the dictionary.
        """

        self.load()
        return self._data.get(key)

    def save(self):
        """
        Safely saves the file data to disk using a mutex lock,
        so the process is thread safe...
        """

        with self._file_lock:
            self.handle_save()

    def handle_save(self):
        """
        Dumps the file from memory out to disk safely.
        """

    def load(self):
        """
        Safely loads the file data from disk using a mutex lock,
        so the process is thread safe...
        """

        with self._file_lock:
            self.handle_load()

    def handle_load(self):
        """
        Loads the file data from disk to memory safely.
        """

    def close(self):
        """
        Closes the file instance and saves the data in memory safely,
        out to disk then clears the file instance references.
        """

        self.save()

        self._database_manager = None
        self._filename = None
        self._data = None
        self._file_lock = None

class DatabaseJSONFile(DatabaseFile):

    def handle_save(self):
        with open(self.filepath, 'w') as io:
            simplejson.dump(self._data, io, indent=2, sort_keys=True)
            io.close()

    def handle_load(self):
        with open(self.filepath, 'r') as io:
            self._data = simplejson.load(io)
            io.close()

class DatabaseYAMLFile(DatabaseFile):

    def handle_save(self):
        with open(self.filepath, 'w') as io:
            yaml.dump(self._data, io, default_flow_style=False)
            io.close()

    def handle_load(self):
        with open(self.filepath, 'r') as io:
            self._data = yaml.load(io)
            io.close()

class DatabaseTOMLFile(DatabaseFile):

    def handle_save(self):
        with open(self.filepath, 'w') as io:
            pytoml.dump(self._data, io)
            io.close()

    def handle_load(self):
        with open(self.filepath, 'r') as io:
            self._data = pytoml.load(io)
            io.close()

class DatabaseManager(object):
    """
    An class that manages database file reading/writing operations,
    creates/destroys file object instances...
    """

    def __init__(self, file_object_handler, directory, file_extension):
        self._file_object_handler = file_object_handler
        self._directory = directory
        self._file_extension = file_extension
        self._files = {}

    @property
    def file_object_handler(self):
        return self._file_object_handler

    @property
    def directory(self):
        return self._directory

    @property
    def file_extension(self):
        return self._file_extension

    @property
    def files(self):
        return self._files

    def get_filepath(self, filename):
        """
        Returns the filename joined with the root database file directory.
        """

        return '%s%s' % (os.path.join(self._directory, filename), self._file_extension)

    def has_file(self, filename):
        """
        Returns true if the filename is in the file dictionary else false.
        """

        return filename in self._files

    def open_file(self, filename, *args, **kwargs):
        """
        Creates a new file instance in memory and loads the corresponding
        file object from disk, placing the data in memory
        """

        if self.has_file(filename):
            raise DatabaseError('Cannot open file: %s, file already open!' % filename)

        file_object = self._file_object_handler(self)
        file_object.filename = filename

        self._files[file_object.filename] = file_object
        file_object.setup()

        return file_object

    def close_file(self, file_object):
        """
        Removes a file instance in memory and closes the file,
        saving the data from memory to disk
        """

        if not self.has_file(file_object.filename):
            raise DatabaseError('Cannot close file: %s, file was never opened!' % filename)

        del self._files[file_object.filename]
        file_object.close()

        del file_object

    def get_file(self, filename):
        """
        Gets a file instance object from the file dictionary by name.
        """

        return self._files.get(filename)

    def setup(self):
        """
        Initializes the database manager and any other specific operations...
        """

        if not os.path.exists(self._directory):
            os.makedirs(self._directory)

    def shutdown(self):
        """
        Destroys all file object instances and saves them to disk.
        """

        for filename, file_object in self._files.items():
            self.close_file(file_object)

class DatabaseInterface(DatabaseManager):

    def __init__(self, file_object):
        directory = config.GetString('database-directory', 'databases/json')
        extension = config.GetString('database-extension', '.json')

        DatabaseManager.__init__(self, file_object, directory, extension)

        self._min_id = config.GetInt('database-min-channels', 1000000000)
        self._max_id = config.GetInt('database-max-channels', 1009999999)

        self._tracker = None
        self._tracker_filename = config.GetString('database-tracker', 'next')

        self._allocator = None

    @property
    def tracker(self):
        return self._tracker

    @property
    def allocator(self):
        return self._allocator

    def setup(self):
        DatabaseManager.setup(self)

        self._tracker = self.open_file(self._tracker_filename)
        self._tracker.save()

        self._min_id = self._tracker.set_default_value('next', self._min_id)
        self._allocator = UniqueIdAllocator(self._min_id, self._max_id)

    def shutdown(self):
        self._tracker = None
        self._min_id = None
        self._max_id = None
        self._allocator = None

        DatabaseManager.shutdown(self)

class DatabaseJSONBackend(DatabaseInterface):

    def __init__(self):
        DatabaseInterface.__init__(self, DatabaseJSONFile)

class DatabaseYAMLBackend(DatabaseInterface):

    def __init__(self):
        DatabaseInterface.__init__(self, DatabaseYAMLFile)

class DatabaseTOMLBackend(DatabaseInterface):

    def __init__(self):
        DatabaseInterface.__init__(self, DatabaseTOMLFile)

class DatabaseOperationFSM(FSM):
    notify = notify.new_category('DatabaseOperationFSM')

    def __init__(self, network, sender, callback=None):
        FSM.__init__(self, self.__class__.__name__)

        self._network = network
        self._sender = sender
        self._callback = callback

    @property
    def network(self):
        return self._network

    @property
    def sender(self):
        return self._sender

    @property
    def callback(self):
        return self._callback

    def enterOff(self):
        pass

    def exitOff(self):
        pass

    def enterStart(self):
        pass

    def exitStart(self):
        pass

    def cleanup(self, success, *args, **kwargs):
        self.ignoreAll()
        self.demand('Off')

        if self.callback:
            self.callback(success, self._sender, *args, **kwargs)

class DatabaseOperationManager(object):
    notify = notify.new_category('DatabaseOperationManager')

    def __init__(self):
        self._operations = collections.deque()

        self._flush_timeout = config.GetFloat('database-flush-timeout', 0.001)
        self.__flush_task = None

    @property
    def operations(self):
        return self._operations

    def add_operation(self, fsm_class, *args, **kwargs):
        operation = fsm_class(*args, **kwargs)
        self._operations.append(operation)

    def setup(self):
        self.__flush_task = task_mgr.doMethodLater(self._flush_timeout, self.__flush, 'database-flush')

    def __flush(self, task):
        """
        Gets an database operation from the queue and processes it...
        """

        while len(self._operations) > 0:
            operation = self._operations.popleft()
            operation.request('Start')

        return task.again

    def shutdown(self):
        if self.__flush_task:
            task_mgr.remove(self.__flush_task)
            self.__flush_task = None

        self._operations = None

class DatabaseCreateFSM(DatabaseOperationFSM):
    notify = notify.new_category('DatabaseCreateFSM')

    def __init__(self, *args, **kwargs):
        self._context = kwargs.pop('context', 0)
        self._dc_id = kwargs.pop('dc_id', 0)
        self._field_count = kwargs.pop('field_count', 0)
        self._field_data = kwargs.pop('field_data', None)

        DatabaseOperationFSM.__init__(self, *args, **kwargs)

    def enterStart(self):
        dc_class = self.network.dc_loader.dclasses_by_number.get(self._dc_id)
        if not dc_class:
            self.notify.error('Failed to create object: %d context: %d, '
                'unknown dclass!' % (self._dc_id, self._context))

        self._do_id = self.network.backend.allocator.allocate()
        if not self._do_id:
            self.notify.warning('Failed to create object: %d context: %d, '
                'could not allocate new do_id!' % (self._dc_class, self._context))

            self.cleanup(False, self._context, 0)
            return

        if self.network.backend.has_file('%d' % self._do_id):
            self.notify.warning('Failed to create object: %d context: %d, '
                'could not create new entry with same do_id: %d!' % (self._dc_class, self._context, self._do_id))

            self.cleanup(False, self._context, 0)
            return

        file_object = self.network.backend.open_file('%d' % self._do_id)
        file_object.save()

        file_object.set_value('dclass', dc_class.get_name())
        file_object.set_value('do_id', self._do_id)

        fields = {}
        field_packer = DCPacker()
        field_packer.set_unpack_data(self._field_data)

        for _ in xrange(self._field_count):
            field_id = field_packer.raw_unpack_uint16()
            field = dc_class.get_field_by_index(field_id)
            if not field:
                self.notify.error('Failed to unpack field: %d dclass: %s, '
                    'invalid field!' % (field_id, dc_class.get_name()))

            field_packer.begin_unpack(field)
            field_args = field.unpack_args(field_packer)
            field_packer.end_unpack()
            if not field_args:
                self.notify.error('Failed to unpack field args for field: %d dclass: %s, '
                    'invalid result!' % (field.get_name(), dc_class.get_name()))

            fields[field.get_name()] = field_args

        for field_index in xrange(dc_class.get_num_inherited_fields()):
            field_packer = DCPacker()
            field = dc_class.get_inherited_field(field_index)

            if not field or field.get_name() in fields:
                continue

            if not field.is_db() or not field.has_default_value():
                continue

            field_packer.set_unpack_data(field.get_default_value())
            field_packer.begin_unpack(field)
            field_args = field.unpack_args(field_packer)
            field_packer.end_unpack()
            if not field_args:
                self.notify.error('Failed to unpack field args for field: %d dclass: %s, '
                    'invalid result!' % (field.get_name(), dc_class.get_name()))

            fields[field.get_name()] = field_args

        file_object.set_value('fields', fields)
        self.network.backend.close_file(file_object)
        self.network.backend.tracker.set_value('next', self._do_id + 1)
        self.cleanup(True, self._context, self._do_id)

    def exitStart(self):
        pass

class DatabaseRetrieveFSM(DatabaseOperationFSM):
    notify = notify.new_category('DatabaseRetrieveFSM')

    def __init__(self, *args, **kwargs):
        self._context = kwargs.pop('context', 0)
        self._do_id = kwargs.pop('do_id', 0)

        DatabaseOperationFSM.__init__(self, *args, **kwargs)

    def enterStart(self):
        if not self._do_id:
            self.notify.warning('Failed to get fields for object: %d context: %d, '
                'unknown object!' % (self._do_id, self._context))

            self.cleanup(False, self._context, 0, 0, None)
            return

        file_object = self.network.backend.open_file('%d' % self._do_id)
        if not file_object:
            self.notify.warning('Failed to get fields for object: %d context: %d, '
                'unknown object!' % (self._do_id, self._context))

            self.cleanup(False, self._context, 0, 0, None)
            return

        dc_name = file_object.get_value('dclass')
        self._dc_class = self.network.dc_loader.dclasses_by_name.get(dc_name)
        if not self._dc_class:
            self.notify.warning('Failed to query object: %d context: %d, '
                'unknown dclass: %s!' % (self._do_id, self._context, dc_name))

            self.cleanup(False, self._context, 0, 0, None)
            return

        self._fields = file_object.get_value('fields')
        if not self._fields:
            self.notify.warning('Failed to query object: %d context %d, '
                'invalid fields!' % (self._do_id, self._context))

            self.cleanup(False, self._context, 0, 0, None)
            return

        self.network.backend.close_file(file_object)
        field_packer = DCPacker()
        for field_name, field_args in self._fields.items():
            field = self._dc_class.get_field_by_name(field_name)
            if not field:
                self.notify.warning('Failed to query object %d context: %d, '
                    'unknown field: %s' % (do_id, self._context, field_name))

                return

            field_packer.raw_pack_uint16(field.get_number())
            field_packer.begin_pack(field)
            field.pack_args(field_packer, field_args)
            field_packer.end_pack()

        self.cleanup(True, self._context, self._dc_class.get_number(), len(self._fields), field_packer)

    def exitStart(self):
        pass

class DatabaseSetFieldFSM(DatabaseOperationFSM):
    notify = notify.new_category('DatabaseSetFieldFSM')

    def __init__(self, *args, **kwargs):
        self._do_id = kwargs.pop('do_id', 0)
        self._context = kwargs.pop('context', 0)
        self._field_data = kwargs.pop('field_data', None)

        DatabaseOperationFSM.__init__(self, *args, **kwargs)

    def enterStart(self):
        file_object = self.network.backend.open_file('%d' % self._do_id)
        if not file_object:
            self.notify.warning('Failed to set fields for object: %d, '
                'unknown object!' % self._do_id)

            self.cleanup(False, self._context, None, None)
            return

        dc_name = file_object.get_value('dclass')
        dc_class = self.network.dc_loader.dclasses_by_name.get(dc_name)
        if not dc_class:
            self.notify.warning('Failed to set fields for object: %d, '
                'unknown dclass: %s!' % (self._do_id, dc_name))

            self.cleanup(False, self._context, None, None)
            return

        field_packer = DCPacker()
        field_packer.set_unpack_data(self._field_data)
        field_id = field_packer.raw_unpack_uint16()
        field = dc_class.get_field_by_index(field_id)
        if not field:
            self.notify.error('Failed to unpack field: %d dclass: %s, '
                'invalid field!' % (field_id, dc_class.get_name()))

        fields = file_object.get_value('fields')
        if not fields:
            self.notify.warning('Failed to set fields for object: %d, '
                'invalid fields!' % self._do_id)

            self.cleanup(False, self._context, field_id, self._field_data)
            return

        field_packer.begin_unpack(field)
        field_args = field.unpack_args(field_packer)
        field_packer.end_unpack()
        if not field_args:
            self.notify.error('Failed to unpack field args for field: %d dclass: %s, '
                'invalid result!' % (field.get_name(), dc_class.get_name()))

        fields[field.get_name()] = field_args
        file_object.set_value('fields', fields)

        self.network.backend.close_file(file_object)
        self.cleanup(True, 0, None)

    def exitStart(self):
        pass

class DatabaseServer(io.NetworkConnector, component.Component):
    notify = notify.new_category('DatabaseServer')

    def __init__(self, dc_loader):
        connect_address = config.GetString('database-connect-address', '127.0.0.1')
        connect_port = config.GetInt('database-connect-port', 7100)

        io.NetworkConnector.__init__(self, dc_loader, connect_address, connect_port)
        self._channel = config.GetInt('database-channel', types.DATABASE_CHANNEL)

        self._backend = DatabaseJSONBackend()
        self._operation_manager = DatabaseOperationManager()

    @property
    def backend(self):
        return self._backend

    @property
    def operation_manager(self):
        return self._operation_manager

    def setup(self):
        io.NetworkConnector.setup(self)

        self._backend.setup()
        self._operation_manager.setup()

    def handle_datagram(self, channel, sender, message_type, di):
        if message_type == types.DBSERVER_CREATE_OBJECT:
            self.handle_create_object(sender, di)
        elif message_type == types.DBSERVER_OBJECT_GET_ALL:
            self.handle_object_get_all(sender, di)
        elif message_type == types.DBSERVER_OBJECT_SET_FIELD:
            self.handle_object_set_field(sender, di)
        elif message_type == types.DBSERVER_OBJECT_SET_FIELD_IF_EQUALS:
            self.handle_object_set_field_if_equals(sender, di)
        else:
            self.notify.warning('Received unknown message type: %d' % message_type)

    def handle_create_object(self, sender, di):
        self._operation_manager.add_operation(DatabaseCreateFSM, self, sender,
            context=di.get_uint32(), dc_id=di.get_uint16(), field_count=di.get_uint16(),
            field_data=di.get_remaining_bytes(), callback=self._create_object_callback)

    def _create_object_callback(self, success, sender, context, do_id):
        datagram = io.NetworkDatagram()
        datagram.add_header(sender, self.channel,
            types.DBSERVER_CREATE_OBJECT_RESP)

        datagram.add_uint32(context)
        datagram.add_uint32(do_id)

        self.handle_send_connection_datagram(datagram)

    def handle_object_get_all(self, sender, di):
        self._operation_manager.add_operation(DatabaseRetrieveFSM, self, sender,
            context=di.get_uint32(), do_id=di.get_uint32(), callback=self._object_get_all_callback)

    def _object_get_all_callback(self, success, sender, context, dc_id, num_fields, field_packer):
        datagram = io.NetworkDatagram()
        datagram.add_header(sender, self.channel,
            types.DBSERVER_OBJECT_GET_ALL_RESP)

        datagram.add_uint32(context)
        datagram.add_uint8(success)
        if success:
            datagram.add_uint16(dc_id)
            datagram.add_uint16(num_fields)

            assert(field_packer is not None)
            datagram.append_data(field_packer.get_string())

        self.handle_send_connection_datagram(datagram)

    def handle_object_set_field(self, sender, di):
        self._operation_manager.add_operation(DatabaseSetFieldFSM, self, sender,
            do_id=di.get_uint32(), field_data=di.get_remaining_bytes())

    def handle_object_set_field_if_equals(self, sender, di):
        self._operation_manager.add_operation(DatabaseSetFieldFSM, self, sender,
            do_id=di.get_uint32(), context=di.get_uint32(), field_data=di.get_remaining_bytes(), callback=self._object_set_field_if_equals_callback)

    def _object_set_field_if_equals_callback(self, success, sender, context, field_id, field_data):
        datagram = io.NetworkDatagram()
        datagram.add_header(sender, self.channel,
            types.DBSERVER_OBJECT_SET_FIELD_IF_EQUALS_RESP)

        datagram.add_uint32(context)
        datagram.add_uint8(success)
        if not success:
            if field_id is not None:
                field_packer = DCPacker()
                field = self._dc_class.get_field_by_index(field_id)
                assert(field is not None)

                field_packer.raw_pack_uint16(field_id)
                field_packer.begin_pack(field)
                field.pack_args(field_packer, field_data)
                field_packer.end_pack()

                datagram.add_uint16(1)
                datagram.append_data(field_packer.get_string())
            else:
                datagram.add_uint16(0)

        self.handle_send_connection_datagram(datagram)

    def shutdown(self):
        self._backend.shutdown()
        self._operation_manager.shutdown()

        io.NetworkConnector.shutdown(self)
