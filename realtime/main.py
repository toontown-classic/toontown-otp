"""
 * Copyright (C) Caleb Marshall - All Rights Reserved
 * Written by Caleb Marshall <anythingtechpro@gmail.com>, August 17th, 2017
 * Licensing information can found in 'LICENSE', which is part of this source code package.
"""

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
