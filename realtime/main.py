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

import __builtin__
import os
import sys
import argparse

from panda3d.core import loadPrcFile

if os.path.exists('config/general.prc'):
    loadPrcFile('config/general.prc')

from pandac.PandaModules import *

from direct.directbase.DirectStart import *
from direct.task.TaskManagerGlobal import taskMgr as task_mgr
__builtin__.task_mgr = task_mgr

from realtime import io, component
from realtime import messagedirector, clientagent, stateserver, database

# attempt to import and utilize the C++ Message Director implementation
try:
    import libotp
    class CMessageDirector(libotp.MessageDirector, component.Component):

        def __init__(self):
            address = config.GetString('messagedirector-address', '0.0.0.0')
            port = config.GetInt('messagedirector-port', 7100)

            libotp.MessageDirector.__init__(self, address, port)

    has_clibotp = True
except ImportError:
    has_clibotp = False


parser = argparse.ArgumentParser()
parser.add_argument("-nmd", "--no-messagedirector", help="Disables the MessageDirector cluster component.", action='store_true')
parser.add_argument("-nca", "--no-clientagent", help="Disables the ClientAgent cluster component.", action='store_true')
parser.add_argument("-nss", "--no-stateserver", help="Disables the StateServer cluster component.", action='store_true')
parser.add_argument("-ndb", "--no-database", help="Disables the DatabaseServer cluster component.", action='store_true')
args = parser.parse_args()


def main():
    dc_loader = io.NetworkDCLoader()
    dc_loader.read_dc_files(['config/dclass/toon.dc'])

    component_manager = component.ComponentManager()
    if not args.no_messagedirector:
        if has_clibotp:
            component_manager.add_component(CMessageDirector())
        else:
            component_manager.add_component(messagedirector.MessageDirector())

    if not args.no_clientagent:
        component_manager.add_component(clientagent.ClientAgent(dc_loader))

    if not args.no_stateserver:
        component_manager.add_component(stateserver.StateServer(dc_loader))

    if not args.no_database:
        component_manager.add_component(database.DatabaseServer(dc_loader))

    task_mgr.run()
    component_manager.shutdown()
    return 0

if __name__ == '__main__':
    sys.exit(main())
