#TODO
#attention Start lance autant de fois l'addon
#implémenter un offset
#ne pas skipper les frames mais faire un systeme de lecture avec test de synchro sinon le son du VSE sera caca
#idee de faire des templates generique par objet pour les controlleur MIDI, ainsi on peut reutiliser une liste de controlleur rapidement sur d'autres objets
#faire sauver/charge de la liste des controlleurs
#pbm criant des properties non simples
#faire attention à l'envoi que les valeur soient comprises entre 0 et 127

bl_info = {
    "name": "AddMIDI",
    "author": "J.P.P",
    "version": (0, 2),
    "blender": (2, 6, 4),
    "location": "",
    "description": "MIDI Sync for Blender VSE (slave)",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "System"}


import bpy
from sys import exit
from select import select
from bpy.utils import register_module, unregister_module

import time
import rtmidi

#Creation of two blender MIDI ports
midiin = rtmidi.MidiIn()
midiin.open_virtual_port("Blender In")
 
midiout = rtmidi.MidiOut()
midiout.open_virtual_port("Blender Out")


tempo = 120
fps = 24
clock = 0 
running_status = 0
startpos = 0
 

class MIDIsync(bpy.types.Operator):
    '''MIDI Sync for Blender VSE (slave)'''
    bl_idname = "addmidi.modal_timer_operator"
    bl_label = "MIDIsync"
    
    _timer = None   
    
    def modal(self, context, event):
        
        global tempo
        global fps
        global clock
        global running_status 
        global startpos
        
        beatframe = (60/tempo)*fps              
        
        if event.type == 'ESC':
            return self.cancel(context)
       
        if event.type == 'TIMER':	
            timer = time.time()	  
            
            #Receiving 
            msg = midiin.get_message()
            while msg != None:
                message, deltatime = msg
                timer += deltatime
                #print("@%0.6f %r" % (timer, message))
                msg = midiin.get_message()
                if running_status== 1 and message[0] == 248:
                    clock += 1
                if message[0] == 251 or message[0] == 250:  #caution: when the playhead is at the begining, it sends a different MIDI START value..
                    print ('START')
                    running_status = 1
                    clock = 0
                    startpos = bpy.data.scenes["Scene"].frame_current
                if message[0] == 252:
                    print ('STOP')
                    bpy.ops.screen.animation_cancel(restore_frame=False)
                    running_status = 0
                if message[0] == 242:
                    locbeat = (message[1] + 128 * message[2]) / 4
                    frame = locbeat * beatframe
                    bpy.data.scenes["Scene"].frame_set(frame)
                    print ('JUMP TO FRAME ',frame)
            
            
                for item in bpy.context.scene.MIDI_keys:
                    if (message[0]-175) == item.channel and message[1] == item.controller:
                        strtoexec = item.name + "=" + str(message[2])
                        exec(strtoexec) 
            
            if running_status == 1:
                frame = startpos + (clock / 48) * fps 
                bpy.ops.screen.animation_play()
                #bpy.data.scenes["Scene"].frame_set(frame)
                #print(clock,frame)
            #print(running_status, clock)
        #bpy.data.scenes["Scene"].frame_current += clock     
        
        #render.fps
        # 128 tick = 8 bar / 16 tick = 1 bar / 4 tick = 1 temps / 1 tick = 1 double croche
        #print(clock)
        #48 clock /seconde à 120bpm
        # x clock = 1 bar
        # 120 bpm
        # y frames / seconde 
            
           
         
            
            
            #For sending values
            for item in  bpy.context.scene.MIDI_keys:
                chan = item.channel + 175 #  1011nnnn = 176 to 191 from the midi specs and -1 since we don't say channel 0
                cont = item.controller
                diff = item.max - item.min
                diff2 = eval(item.name) - item.min
                value = int( (diff2 / diff) * 127) 
                midiout.send_message([chan,cont,value])
             
 
            
             
        return {'PASS_THROUGH'}            



    def execute(self, context):
        context.window_manager.modal_handler_add(self)
        self._timer = context.window_manager.event_timer_add(1, context.window)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        context.window_manager.event_timer_remove(self._timer)
        return {'CANCELLED'}


class AddMIDI_UIPanel(bpy.types.Panel):
    bl_label = "AddMIDI"
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_category = "AddMIDI"
 
    def draw(self, context):
        layout = self.layout
        layout.operator("addmidi.start", text='Start')
        layout.prop(bpy.context.scene , "midi_in_device", text="Midi In")
        layout.prop(bpy.context.scene , "midi_out_device", text="Midi Out")
        layout.separator()
        layout.operator("addmidi.importks", text='Import Keying Set')        
        layout.separator()
        for item in bpy.context.scene.MIDI_keys:
            row = layout.row()
            box = row.box()
            box.prop(item, 'name')
            box.prop(item, 'channel')
            box.prop(item, 'controller')
            box.prop(item, 'nrpn')
            box.prop(item, 'min')
            box.prop(item, 'max')
               
        
class OBJECT_OT_StartButton(bpy.types.Operator):
    bl_idname = "addmidi.start"
    bl_label = "Start AddMidi"
     
    def execute(self, context):
        bpy.ops.addmidi.modal_timer_operator()
        return{'FINISHED'}

class OBJECT_OT_Addpropbutton(bpy.types.Operator):
    bl_idname = "addmidi.importks"
    bl_label = "Import Keying Set for AddMIDI"
    
    class SceneSettingItem(bpy.types.PropertyGroup):
        name = bpy.props.StringProperty(name="Key", default="Unknown")
        channel = bpy.props.IntProperty(name="Channel", default=1)
        controller = bpy.props.IntProperty(name="Controller", default=1)
        min = bpy.props.IntProperty(name="Min", default=0)
        max = bpy.props.IntProperty(name="Max", default=100)
        nrpn = bpy.props.BoolProperty(name="NRPN", default=False)
    bpy.utils.register_class(SceneSettingItem) #necessary ?
    
    bpy.types.Scene.MIDI_keys = bpy.props.CollectionProperty(type=SceneSettingItem)
 
    def execute(self, context):
 
        ks = bpy.context.scene.keying_sets.active
        my_item = bpy.context.scene.MIDI_keys.clear()
        tvar2 = ""
        if str(ks) !="None" :
            for items in ks.paths:
                tvar="bpy.data."+items.id_type.lower()+"s"+"['"+items.id.name+"']."+items.data_path
                '''if str(eval(tvar)).find("Vector") != -1 or str(eval(tvar)).find("Euler")  != -1 :  #Pour traiter le cas des Vectors
                    tvar2 = tvar2 + tvar+".x\n"
                    tvar2 = tvar2 + tvar+".y\n"
                    tvar2 = tvar2 + tvar+".z\n"
                elif str(eval(tvar)).find("Quaternion") != -1 :
                    tvar2 = tvar2 + tvar+".w\n"
                    tvar2 = tvar2 + tvar+".x\n"
                    tvar2 = tvar2 + tvar+".y\n"
                    tvar2 = tvar2 + tvar+".z\n"
                else:    
                    tvar2 = tvar2 + tvar+"\n"  '''  
                      
                my_item = bpy.context.scene.MIDI_keys.add()
                my_item.name = tvar
                print("Imported keys:\n"+tvar)
        return{'FINISHED'}



def register():
    bpy.utils.register_module(__name__)

    b=[]
    for i in midiin.get_ports():
        a = (i,i,i)
        b.append(a)
    obj_types_enum = b
    bpy.types.Scene.midi_in_device = bpy.props.EnumProperty(name = "MIDI In Ports", items = obj_types_enum)
    
    b=[]
    for i in midiout.get_ports():
        a = (i,i,i)
        b.append(a)
    obj_types_enum = b
    bpy.types.Scene.midi_out_device = bpy.props.EnumProperty(name = "MIDI Out Ports", items = obj_types_enum)
    
def unregister():
    bpy.utils.unregister_module(__name__)
 
if __name__ == "__main__": 
    register()
 
 

