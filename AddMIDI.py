#    This Addon for Blender implements realtime MIDI support in the viewport
#
# ***** BEGIN GPL LICENSE BLOCK *****
#
#    Copyright (C) 2015  JPfeP <http://www.jpfep.net/>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ***** END GPL LICENCE BLOCK *****


#TODO

#MIDI SYNC
#ne pas skipper les frames mais faire un systeme de lecture avec test de synchro sinon le son du VSE sera caca
#en mode slave evaluer la clock a la fin de la boucle while 

#faire sauver/charge de la liste des controlleurs en fichier text
# memoriser les listes de properties et leur parametres sinon quand on reimport tout est perdu

#pbm des properties list, qui peuvent se tester indirectement quand on leur envoi une mauvaise valeur. en MIDI impossible de donner une string.
#bpy.types.Material.bl_rna.properties['diffuse_shader'].enum_items[0].name

#le system physique rigid body + animation fait stopper le modal timer ? pas de bonne integration, pbm des scripts également
# c quoi cette histoire de delta dans la norme midi
#pbm des note_on =0 utilisé comme noteoff sur certains sequencer

#attention avec le autorun, tester si le device MIDI existe bien car il est stoqué dans le .blend, si pas de device en creer un ?
#faire que la prop autorun ne depende pas de la scene mais du .blend ?

#enrichier la structure des keys, et faire que selon 7 ou 14 bit le numero de ctl soit borné differement.
#gerer les RPN/NRPN 7 et 14 bit

#faire un parsing avant pour qu'en fonction de la liste de cont_type la grosse boucle ne teste que les classes de cont_type retenus par l'user.

#faut il tout le temps emmettre les valeurs ou juste quand changement, choix possible, mais ca serait plus logique.
#faire attention à l'envoi que les valeur soient comprises entre 0 et 127

#reiplementer le refresh et faire le test proposé cf. BArtists 
#mettre une option debug pour les messages venant

#Later:
#break the script into several files
#implement pitchbend ?
#object per midi channel list of properties or by routing properties to object selection for user with some knobs ?
#Import Midifiles facility using an external module ?

bl_info = {
    "name": "AddMIDI",
    "author": "JPfeP",
    "version": (0, 3),
    "blender": (2, 6, 4),
    "location": "",
    "description": "MIDI for Blender",
    "warning": "",
    "wiki_url": "http://www.jpfep.net/AddMIDI",
    "tracker_url": "",
    "category": "System"}


import bpy
from sys import exit
from select import select
from bpy.utils import register_module, unregister_module
from bpy.app.handlers import persistent

import time
import rtmidi

#Some global variables
tempo = 120
fps = 24
clock = 0 
running_status = 0
startpos = 0
 
MIDI_list_enum = []

#Creation of two MIDI ports
midiin = rtmidi.MidiIn()
midiout = rtmidi.MidiOut()

CC_6  = [0 for i in range(16)] 
CC_38 = [0 for i in range(16)]
CC_100 = [0 for i in range(16)]
CC_101 = [0 for i in range(16)]
CC_98 = [0 for i in range(16)]
CC_99 = [0 for i in range(16)]


def set_midiin(port):     
    global midiin
    midiin.close_port()
    midiin = None
    midiin = rtmidi.MidiIn()
    midiin.open_port(name=port)

def set_midiout(port):
    global midiout
    midiout.close_port()
    midiout = None
    midiout = rtmidi.MidiOut()
    midiout.open_port(name=port)


class AddMIDI_ModalTimer(bpy.types.Operator):
    '''MIDI Sync for Blender VSE (slave)'''
    bl_idname = "addmidi.modal_timer_operator"
    bl_label = "AddMIDI Modal Timer"
    
    _timer = None 
    
    bpy.types.WindowManager.addmidi_running = bpy.props.StringProperty(default="Stopped")
        
    def modal(self, context, event):
        
        global tempo
        global fps
        global clock
        global running_status 
        global startpos                    
        
        beatframe = (60/tempo)*fps              
        
       
        if event.type == 'TIMER':	
            timer = time.time()	  
            
            #Receiving 
            msg = midiin.get_message()
            while msg != None:
                message, deltatime = msg
                timer += deltatime
                print("@%0.6f %r" % (timer, message))
                
                msg = midiin.get_message()   #why this line is necessary (if not, infinite loop) ?
                
                             
                #For the MIDI clock
                if running_status== 1 and message[0] == 248:
                    clock += 1
                if message[0] == 251 or message[0] == 250:  #workaround: when the playhead is at the begining, it sends a different MIDI START value..
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
            
                #For the MIDI controllers
                for item in bpy.context.scene.MIDI_keys:
                    result_message2 = (message[2]/127) * (item.max - item.min) + item.min
                    result_message1 = (message[1]/127) * (item.max - item.min) + item.min
                    
                    
                    ''' Old code
                    #pour CC 7bit
                    if (message[0]-175) == item.channel and message[1] == item.controller:
                        strtoexec = "bpy.data."+item.name + "=" + str(result_message2)
                        exec(strtoexec) 
                    
                    #for RPN
                    a = message[0]-175 #the channel
                    b = message[1]     #the controler number
                    c = message[2]     #the value
                    
                    elif b == 6 :
                        CC_6[a] = c
                    
                    elif b == 38 :
                        CC_38[a] = c                   
                                                                           
                    elif b == 101 :
                        CC_101[a] = c
                    
                    elif b == 100 :
                        if CC_101[a]*127 + c*107 == item.controller and message[a]
                    '''
                    
                    #New code for CC_7 and CC_14
                    chan = message[0]-175
                    cc   = message[1]
                    val  = message[2]
                    
                    
                    if chan == item.channel:
                        
                        #For classic CC_7
                        if cc == item.controller: 
                            strtoexec = "bpy.data."+item.name + "=" + str(result_message2)
                            exec(strtoexec)
                        
                        
                        elif cc == 6 :
                            CC_6[chan] = val
                            #CC_38[chan] = 0
                        elif cc == 38 :
                            CC_38[chan] = val
                        #For NRPN
                        elif cc == 99:
                            CC_99[chan] = val
                        elif cc == 98:
                            if CC_99[chan]*127 + val == item.controller and item.cont_type == 'nrpn14':
                                strtoexec = "bpy.data."+item.name + "=" + str(CC_6[chan]*127 + CC_38[chan])
                                exec(strtoexec)
                        #For RPN
                        elif cc == 101:
                            CC_101[chan] = val
                        elif cc == 100:
                            if CC_101[chan]*127 + val == item.controller and item.cont_type == 'rpn14':
                                strtoexec = "bpy.data."+item.name + "=" + str(CC_6[chan]*127 + CC_38[chan])
                                exec(strtoexec)
           
                    
                    #for the notes on
                    elif (message[0]-143) == item.channel and message[2] != 0:
                        strtoexec = "bpy.data."+item.name + "=" + str(result_message1)
                        #print(strtoexec)
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
            
           
         
            
            '''
            #For sending values
            for item in  bpy.context.scene.MIDI_keys:
                chan = item.channel + 175 #  1011nnnn = 176 to 191 from the midi specs and -1 since we don't say channel 0
                cont = item.controller
                diff = item.max - item.min
                diff2 = eval("bpy.data."+item.name) - item.min
                value = int( (diff2 / diff) * 127) 
                midiout.send_message([chan,cont,value])
            '''
 
            
             
        return {'PASS_THROUGH'}            



    def execute(self, context):
        context.window_manager.modal_handler_add(self)
        self._timer = context.window_manager.event_timer_add(.1, context.window)
        context.window_manager.addmidi_running = "Running"
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        context.window_manager.event_timer_remove(self._timer)
        context.window_manager.addmidi_running = "Stopped"
        return {'CANCELLED'}


def init_settings():
    #Checking if a hidden text already exists for our settings
    text_settings = None
    for text in bpy.data.texts:
        if text.name != '.addmidi_settings':
            text_settings = text
    if text_settings == None:
        bpy.ops.text.new()
        text_settings = bpy.data.texts[-1]
        text_settings.name = '.addmidi_settings'
    bpy.types.Text.my_string = bpy.props.StringProperty(default="plop")

class AddMIDI_UIPanel(bpy.types.Panel):
    bl_label = "AddMIDI"
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_category = "AddMIDI"
   
    

 
    
    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="MIDI Settings:")
        row = col.row(align=True)
        row.operator("addmidi.start", text='Start')
        row.operator("addmidi.stop", text='Stop')
        layout.prop(bpy.context.window_manager, "addmidi_running")
        layout.prop(bpy.context.scene , "midi_in_device", text="Midi In")
        layout.prop(bpy.context.scene , "midi_out_device", text="Midi Out")
        layout.prop(bpy.context.scene , "autorun", text="Start at launch")
        layout.prop(bpy.data.texts[0], "my_string")
        
        layout.separator()
        layout.operator("addmidi.importks", text='Import Keying Set')        
        layout.separator()
        for item in bpy.context.scene.MIDI_keys:
            row = layout.row()
            box = row.box()
            box.prop(item, 'name')
            box.prop(item, 'channel')
            box.prop(item, 'cont_type')
            if item.cont_type != 'note_off' and item.cont_type != 'note_on' and item.cont_type != 'vel':
                box.prop(item, 'controller')
            box.prop(item, 'min')
            box.prop(item, 'max')

    bpy.types.WindowManager.autorun = bpy.props.BoolProperty()
    
    def upd_midiin(self, context):     
        set_midiin(bpy.context.scene.midi_in_device)
    
    def upd_midiout(self, context):
        set_midiout(bpy.context.scene.midi_out_device)
    
    b=[]
    for i in midiin.get_ports():
        a = (i,i,i)
        b.append(a)
    obj_types_enum = b
    bpy.types.Scene.midi_in_device = bpy.props.EnumProperty(name="MIDI In Ports", items=obj_types_enum, update=upd_midiin)
    
    b=[]
    for i in midiout.get_ports():
        a = (i,i,i)
        b.append(a)
    obj_types_enum = b
    bpy.types.Scene.midi_out_device = bpy.props.EnumProperty(name = "MIDI Out Ports", items = obj_types_enum, update=upd_midiout)
             
        
class AddMIDI_StartButton(bpy.types.Operator):
    bl_idname = "addmidi.start"
    bl_label = "Start AddMidi"
     
    def execute(self, context):
        if bpy.context.window_manager.addmidi_running != "Running":
            self.report({'INFO'}, "Starting MIDI...")
            set_midiin(bpy.context.scene.midi_in_device)
            set_midiout(bpy.context.scene.midi_out_device)
            bpy.ops.addmidi.modal_timer_operator()
        else:
            self.report({'INFO'}, "Already running !")
        return{'FINISHED'}
    
class AddMIDI_StopButton(bpy.types.Operator):
    bl_idname = "addmidi.stop"
    bl_label = "Stop AddMidi"
     
    def execute(self, context):
        bpy.ops.addmidi.modal_timer_operator('CANCEL_DEFAULT')
        return{'FINISHED'}
    

class AddMIDI_Import_KS_button(bpy.types.Operator):
    bl_idname = "addmidi.importks"
    bl_label = "Import Keying Set for AddMIDI"   
    
   
    list = (('note_on','note_on',''),
            ('note_off','note_off',''),
            ('vel','velocity','',),
            ('aft','aftertouch','',),
            ('cc7','continous controller 7bit','',),
            ('rpn14','RPN 14bit','',),
            ('nrpn14','NRPN 14 bit','',),
            ('','','',))
                          
    for l in list:
        MIDI_list_enum.append(l)
    
    class SceneSettingItem(bpy.types.PropertyGroup):
        name = bpy.props.StringProperty(name="Key", default="Unknown")
        channel = bpy.props.IntProperty(name="Channel", min=1, max=16, default=1)
        controller = bpy.props.IntProperty(name="Controller number", min=1, default=1)
        min = bpy.props.IntProperty(name="Min", default=0)
        max = bpy.props.IntProperty(name="Max", default=100)
        cont_type = bpy.props.EnumProperty(name = "Controller type", items = MIDI_list_enum)
    bpy.utils.register_class(SceneSettingItem) #necessary ?
    
    bpy.types.Scene.MIDI_keys = bpy.props.CollectionProperty(type=SceneSettingItem)
 
    def execute(self, context):
 
        ks = bpy.context.scene.keying_sets.active
        my_item = bpy.context.scene.MIDI_keys.clear()
        tvar2 = ""
        id_n = 0

        if str(ks) != "None":
            for items in ks.paths:               
                if str(items.id) != "None":     #workaround to avoid bad ID Block (Nodes)
                    
                    if items.data_path[0:2] == '["' and items.data_path[-2:] == '"]':
                        tvar = repr(items.id)[9:] + items.data_path
                         
                    else:
                        tvar = repr(items.id)[9:] + "." + items.data_path
                       
                    
                    tvar_ev = "bpy.data." + tvar
                                  
                    if repr(type(eval(tvar_ev)))!="<class 'str'>":
                        try:
                            l=len(eval(tvar_ev)) 
                            if items.use_entire_array==True: 
                                j = 0
                                k = l                                
                            else:
                                j = items.array_index
                                k = j+1
                            for i in range(j,k):
                                tvar2 += tvar + "[" + str(i) + "]"+"\n"                                
                        except:
                            tvar2 = tvar
                    else:
                        tvar2 = tvar
                                      
                    for i in tvar2.split("\n")[:-1]:
                        my_item = bpy.context.scene.MIDI_keys.add()
                        my_item.name = i
                        tvar2 = ""
                        #my_item.ID = id_n
                        #id_n += 1
                        #my_item.address = bpy.context.scene.defaultaddr 
                        #my_item.osc_type = repr(type(eval("bpy.data."+i)))[8:-2]
                        print("Imported keys:\n"+i)
                else:
                    self.report({'INFO'}, "Missing ID block !")
                                                         
        else:
            self.report({'INFO'}, "None found !")         
        
        return{'FINISHED'}        

  

@persistent
def addmidi_handler(scene):
    autorun = bpy.context.scene.autorun
    if autorun == True:
        bpy.ops.addmidi.start()
    init_settings()

def register():
    bpy.utils.register_module(__name__)
    bpy.app.handlers.load_post.append(addmidi_handler)
    
def unregister():
    bpy.utils.unregister_module(__name__)
 
if __name__ == "__main__": 
    register()
 
 

