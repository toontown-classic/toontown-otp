"""
 * Copyright (C) Caleb Marshall - All Rights Reserved
 * Written by Caleb Marshall <anythingtechpro@gmail.com>, August 17th, 2017
 * Licensing information can found in 'LICENSE', which is part of this source code package.
"""

import __builtin__
import os
import sys

from panda3d.core import loadPrcFile

if os.path.exists('config/general.prc'):
    loadPrcFile('config/general.prc')

from pandac.PandaModules import *

from direct.directbase.DirectStart import *
from direct.task.TaskManagerGlobal import taskMgr as task_mgr
__builtin__.task_mgr = task_mgr

from realtime import io, component
from realtime import messagedirector, clientagent, stateserver, database

def main():
    dc_loader = io.NetworkDCLoader()
    dc_loader.read_dc_files(['config/dclass/toon.dc'])

    component_manager = component.ComponentManager()
    component_manager.add_component(messagedirector.MessageDirector())
    component_manager.add_component(clientagent.ClientAgent(dc_loader))
    component_manager.add_component(stateserver.StateServer(dc_loader))
    component_manager.add_component(database.DatabaseServer(dc_loader))

    task_mgr.run()
    component_manager.shutdown()
    return 0

if __name__ == '__main__':
    sys.exit(main())
