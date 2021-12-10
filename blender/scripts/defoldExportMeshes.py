bl_info = {
    "name": "Defold Export Meshes",
    "blender": (2, 80, 0),
    "category": "Object",
}

import bpy, sys, os
import asyncio, socket, threading

# When bpy is already in local, we know this is not the initial import...
if "bpy" in locals():
    # ...so we need to reload our submodule(s) using importlib
    import importlib
    if "defoldCmds" in locals():
        importlib.reload(defoldCmds)
    if "tcpserver" in locals():
        importlib.reload(tcpserver)

dir = os.path.dirname(bpy.data.filepath)
if not dir in sys.path:
    sys.path.append(dir )

import defoldCmds
from tcpserver import TCPServer

# ------------------------------------------------------------------------
# Defold export tool
#    What is this?  This is a tool for the Defold game engine to export information/data from 
#    Blender to a Defold project tool. 
#    Allows users to create complex 3D scenes in Blender, and instantly be able to use those 3D
#    scenes in Defold - this may even be possible live (TODO)
#
#   General Structure
#     This server script that takes commands from a client and sends requested data 
#     An intermediary tool (Make in Defold) that requests the data and creates Defold components
#     The Defold project is assigned to the intermediary tool which allows direct export to the project
#
# Initial Tests:
#  - Some simple commands - Get Object, Get Mesh, Get Texture/UVs
#  - Display in intermediary tool
#  - Write a collection file, go files, mesh files and texture/image files

class StartDefoldServer(bpy.types.Operator):
    """Defold Server Started..."""          # Use this as a tooltip for menu items and buttons.
    bl_idname = "defold.serverstart"       # Unique identifier for buttons and menu items to reference.
    bl_label = "Start Defold Server"        # Display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}       # Enable undo for the operator.

    def execute(self, context):        # execute() is called when running the operator.

        exit_server = 0
        server = None

        # Handle commands - may break this out into a module 
        def run_command(ip, client, data):  
            cmd = data.decode("utf-8")          
            if(cmd == 'shutdown'):
                server.stop()
                server.join()
                return
            defoldCmds.runCommand( context, client, cmd )

        def run_server():
            server = TCPServer("localhost", 5000, run_command)
            server.run()

        # Submit the coroutine to a given loop
        server_thread = threading.Thread(target=run_server)
        server_thread.start()

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.

def menu_func(self, context):
    self.layout.operator(StartDefoldServer.bl_idname)

def register():
    bpy.utils.register_class(StartDefoldServer)
    bpy.types.VIEW3D_MT_object.append(menu_func)  # Adds the new operator to an existing menu.

def unregister():
    bpy.utils.unregister_class(StartDefoldServer)


# This allows you to run the script directly from Blender's Text editor
# to test the add-on without having to install it.
if __name__ == "__main__":
    register()