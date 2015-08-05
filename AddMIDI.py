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

#------------------For next release:-----------------
#ameliorer le refresh de la liste des ports midi, cacher les rtmidi visibles 

#send Note events from Blender

#faire un parsing pour qu'en fonction de la liste de cont_type la boucle ne teste que les classes d'events retenues par l'user.

#en cas de rewind flusher le tableau MIDI_sent_values ? mettre un frame handler ? Potential pbm with loop, defacto midi thru

#pbm des properties list, qui peuvent se tester qu'indirectement quand on leur envoi une mauvaise valeur. en MIDI impossible de donner une string.
#ou alors avec bl_rna, par exemple: bpy.types.Material.bl_rna.properties['diffuse_shader'].enum_items[0].name

#------------------Later:----------------------------
#MIDI SYNC
#ne pas skipper les frames mais faire un systeme de lecture avec test de synchro sinon le son du VSE sera caca
#en mode slave evaluer la clock a la fin de la boucle while  

#send null rpn/nrpn 127/127 ?
#monotoring the values in the GUI with a switch
#break the script into several files
#implement program change and pitchbend ?
#object per midi channel list of properties or by routing properties to object selection for user with some knobs ?
#import Midifiles facility using an external module ?
#(general question) why C.window_manager.midi_in_device cannot be referenced ?
#(general question) why update function need or not self,context as arguments
#(general question) why modal timer stop sometimes (see pbm with physics once), attach it to a window or not, pbm with CTRL+C in the console
#(general question) hint for an operator when mouse pass over it, howto ?

bl_info = {
    "name": "AddMIDI",
    "author": "JPfeP",
    "version": (0, 7),
    "blender": (2, 7, 1),
    "location": "",
    "description": "MIDI for Blender",
    "warning": "",
    "wiki_url": "http://www.jpfep.net/en-us/pages/addmidi/",
    "tracker_url": "",
    "category": "System"}


import bpy
from sys import exit
from select import select
from bpy.utils import register_module, unregister_module
from bpy.app.handlers import persistent
import time
import rtmidi
from rtmidi.midiutil import open_midiport                                                                                                                                   

#Some global variables
tempo = 120
fps = 24
clock = 0 
running_status = 0
startpos = 0
 
MIDI_list_enum = []
midi_in_list = []
midi_out_list = []
MIDI_sent_values = [0 for i in range(1000)]
error_device = False

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
    midiin = None
    midiin = rtmidi.MidiIn()
    if port != "None":
        midiin, portname = open_midiport(port=port, type_="input")
        print ("Input: "+portname)

def set_midiout(port):
    global midiout
    midiout = None
    midiout = rtmidi.MidiOut()
    if port != "None":
        midiout, portname = open_midiport(port=port, type_="output")
        print ("Output: "+portname)

def upd_settings_sub(n):
    text_settings = None
    for text in bpy.data.texts:
        if text.name == '.addmidi_settings':
            text_settings = text
    if text_settings == None:
        bpy.ops.text.new()
        text_settings = bpy.data.texts[-1]
        text_settings.name = '.addmidi_settings'   
        text_settings.write("\n\n\n\n")
    if n==0:
        text_settings.lines[0].body = str(int(bpy.context.window_manager.autorun))
    elif n==1:
        text_settings.lines[1].body = bpy.context.window_manager.midi_in_device
    elif n==2:
        text_settings.lines[2].body = bpy.context.window_manager.midi_out_device
    elif n==3:
        text_settings.lines[3].body = str(int(bpy.context.window_manager.rate))

def upd_setting_0():
    upd_settings_sub(0)
    
def upd_setting_1():
    upd_settings_sub(1)
        
def upd_setting_2():
    upd_settings_sub(2)
    
def upd_setting_3():
    upd_settings_sub(3)    

#This to limit the sent values in a proper range
def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))        

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
        
        #This for applying the scale given by the user for each key
        def rescale(val,min,max,quant):
            result = (val/quant) * (max - min) + min
            return str(result)
        
        if context.window_manager.addmidi_running == "Stopped":
            return self.cancel(context)
        
        if event.type == 'TIMER':	
            timer = time.time()	  
            
            ###################################RECEIVING######################################## 
            if midiin is not None:
                msg = midiin.get_message()
                while msg != None:
                    message, deltatime = msg
                    
                    #Uncomment to debug incoming messages
                    #timer += deltatime
                    #print("In :"+"@%0.6f %r" % (timer, message))
                    
                    msg = midiin.get_message()   #why this line is necessary (if not, infinite loop) ?
                    
                    ''' LATER, MIDI Sync mode:           
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
                    '''
                
                    #For the MIDI controllers
                    for item in bpy.context.scene.MIDI_keys:

                        #New code for CC_7 and CC_14
                        chan = message[0]-175
                        cc   = message[1]
                        if len(message) > 2: 
                            val  = message[2]
                        else:
                            val = 0
                        
                        if chan == item.channel:
                            
                            #For classic CC_7
                            if cc == item.controller: 
                                strtoexec = "bpy.data."+item.name + "=" + rescale(message[2],item.min,item.max,127)
                                exec(strtoexec)
                                                    
                            elif cc == 6 :
                                CC_6[chan] = val

                            elif cc == 38 :
                                CC_38[chan] = val
                            
                            #For NRPN
                            elif cc == 99:
                                CC_99[chan] = val
                            elif cc == 98:
                                if CC_99[chan]*127 + val == item.controller14:
                                    if  item.cont_type == 'nrpn14':
                                        strtoexec = "bpy.data."+item.name + "=" + rescale(CC_6[chan]*127 + CC_38[chan],item.min,item.max,16383)
                                        exec(strtoexec)
                                    elif item.cont_type == 'nrpn':
                                        strtoexec = "bpy.data."+item.name + "=" + rescale(CC_6[chan],item.min,item.max,127)
                                        exec(strtoexec)
                            
                            #For RPN
                            elif cc == 101:
                                CC_101[chan] = val
                            elif cc == 100:
                                if CC_101[chan]*127 + val == item.controller14: 
                                    if item.cont_type == 'rpn14':
                                        strtoexec = "bpy.data."+item.name + "=" + rescale(CC_6[chan]*127 + CC_38[chan],item.min,item.max,16383)
                                        exec(strtoexec)
                                    elif item.cont_type == 'rpn':
                                        strtoexec = "bpy.data."+item.name + "=" + rescale(CC_6[chan],item.min,item.max,127) 
                                        exec(strtoexec)    
                        
                        #for the notes 
                        elif (message[0]-143) == item.channel:
                            if item.cont_type == 'note_on' and message[2] != 0:
                                strtoexec = "bpy.data."+item.name + "=" + rescale(message[1],item.min,item.max,127)
                                exec(strtoexec)
                            if item.cont_type == 'note_off' and message[2] == 0:
                                strtoexec = "bpy.data."+item.name + "=" + rescale(message[1],item.min,item.max,127)
                                exec(strtoexec)                               
                            if item.cont_type == 'on_off':
                                strtoexec = "bpy.data."+item.name + "=" + rescale(message[1],item.min,item.max,127)
                                exec(strtoexec)
                            if item.cont_type == 'vel':
                                strtoexec = "bpy.data."+item.name + "=" + rescale(message[2],item.min,item.max,127)
                                exec(strtoexec)
                        #support for the native Note Off message        
                        elif (message[0]-127) == item.channel:
                            if item.cont_type == 'note_off' or item.cont_type == 'on_off':
                                strtoexec = "bpy.data."+item.name + "=" + rescale(message[1],item.min,item.max,127)
                                exec(strtoexec)
                
            #if running_status == 1:
                #frame = startpos + (clock / 48) * fps 
                #bpy.ops.screen.animation_play()
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
            
           
         
            
         
            ###########################SENDING###############################################
            if midiout is not None:
                counter = 0
                for item in bpy.context.scene.MIDI_keys:
                    prop = eval("bpy.data."+item.name)
                    if prop != MIDI_sent_values[counter]:
                        if item.cont_type == 'cc7':
                            chan = item.channel + 175 #  1011nnnn = 176 to 191 from the midi specs and -1 since we don't say channel 0
                            cont = item.controller
                            diff = item.max - item.min
                            diff2 = prop - item.min
                            value = clamp(0,int( (diff2 / diff) * 127),127) 
                            midiout.send_message([chan,cont,value])
                
                        elif item.cont_type == 'rpn':
                            chan = item.channel + 175 #  1011nnnn = 176 to 191 from the midi specs and -1 since we don't say channel 0
                            cont_101 = int(item.controller14 / 128)
                            cont_100 = item.controller14 % 128
                            diff = item.max - item.min
                            diff2 = prop - item.min
                            value = clamp(0,int((diff2 / diff) * 127),127) 
                            midiout.send_message([chan,100,cont_101])
                            midiout.send_message([chan,101,cont_100])
                            midiout.send_message([chan,6,value])
                                                
                        elif item.cont_type == 'nrpn':
                            chan = item.channel + 175 #  1011nnnn = 176 to 191 from the midi specs and -1 since we don't say channel 0
                            cont_99 = int(item.controller14 / 128)
                            cont_98 = item.controller14 % 128
                            diff = item.max - item.min
                            diff2 = prop - item.min
                            value = clamp(0,int((diff2 / diff) * 127),127) 
                            midiout.send_message([chan,99,cont_99])
                            midiout.send_message([chan,98,cont_98])
                            midiout.send_message([chan,6,value])

                        elif item.cont_type == 'rpn14':
                            chan = item.channel + 175 #  1011nnnn = 176 to 191 from the midi specs and -1 since we don't say channel 0
                            cont_101 = int(item.controller14 / 128)
                            cont_100 = item.controller14 % 128
                            diff = item.max - item.min
                            diff2 = prop - item.min
                            value    = clamp(0,int( (diff2 / diff) * 16383),16383) 
                            value_6  = int (value / 127)
                            value_38 = value % 127
                            midiout.send_message([chan,101,cont_101])
                            midiout.send_message([chan,100,cont_100])
                            midiout.send_message([chan,6,value_6])                                              
                            midiout.send_message([chan,38,value_38])    
                                                
                        elif item.cont_type == 'nrpn14':
                            chan = item.channel + 175 #  1011nnnn = 176 to 191 from the midi specs and -1 since we don't say channel 0
                            cont_99 = int(item.controller14 / 128)
                            cont_98 = item.controller14 % 128
                            diff = item.max - item.min
                            diff2 = prop - item.min
                            value    = clamp(0,int( (diff2 / diff) * 16383),16383) 
                            value_6  = int (value / 127)
                            value_38 = value % 127
                            midiout.send_message([chan,99,cont_99])
                            midiout.send_message([chan,98,cont_98])
                            midiout.send_message([chan,6,value_6])                                              
                            midiout.send_message([chan,38,value_38])  
                                    
                                                                                            
                    MIDI_sent_values[counter] = prop    
                    counter = counter + 1
             
        return {'PASS_THROUGH'}            


    def execute(self, context):
        context.window_manager.modal_handler_add(self)
        self._timer = context.window_manager.event_timer_add(bpy.context.window_manager.rate/1000, context.window)
        context.window_manager.addmidi_running = "Running"
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        context.window_manager.event_timer_remove(self._timer)
        context.window_manager.addmidi_running = "Stopped"
        return {'CANCELLED'}
  
    
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
        layout.prop(bpy.context.window_manager, "addmidi_running", text="Status")
        layout.prop(bpy.context.window_manager , "midi_in_device", text="Midi In")
        layout.prop(bpy.context.window_manager , "midi_out_device", text="Midi Out")
        layout.operator("addmidi.refresh_devices", text='Refresh the MIDI Devices List')
        layout.prop(bpy.context.window_manager , "rate", text="Update rate(ms)")
        layout.prop(bpy.context.window_manager , "autorun", text="Start at launch")
        layout.separator()
        layout.operator("addmidi.importks", text='Import Keying Set')   
        col2 = layout.column(align=True)
        row2 = col2.row(align=True)
        row2.operator("addmidi.list2text", text='Save list as text')
        row2.operator("addmidi.text2list", text='Import keys from text')       
        layout.separator()
        for item in bpy.context.scene.MIDI_keys:
            row = layout.row()
            box = row.box()
            box.prop(item, 'name')
            box.prop(item, 'channel')
            box.prop(item, 'cont_type')
            if item.cont_type != 'note_off' and item.cont_type != 'note_on' and item.cont_type != 'vel':
                if item.cont_type == 'rpn14' or item.cont_type == 'nrpn14':
                    box.prop(item, 'controller14')
                else:
                    box.prop(item, 'controller')
            col3 = box.column(align=True)
            row3 = col3.row(align=True)
            row3.prop(item, 'min')
            row3.prop(item, 'max')

    def upd_trick_autorun(self,context):
        upd_setting_0()
    def upd_trick_rate(self,context):
        upd_setting_3()
    
    bpy.types.WindowManager.autorun = bpy.props.BoolProperty(update=upd_trick_autorun)    
    bpy.types.WindowManager.rate    = bpy.props.IntProperty(min=1,update=upd_trick_rate)         
        
class AddMIDI_StartButton(bpy.types.Operator):
    bl_idname = "addmidi.start"
    bl_label = "Start AddMidi"
     
    def execute(self, context):
        if bpy.context.window_manager.addmidi_running != "Running":
            self.report({'INFO'}, "Starting MIDI...")
            set_midiin(bpy.context.window_manager.midi_in_device)
            set_midiout(bpy.context.window_manager.midi_out_device)
            bpy.ops.addmidi.modal_timer_operator()
        else:
            self.report({'INFO'}, "Already running !")
        return{'FINISHED'}

    
class AddMIDI_StopButton(bpy.types.Operator):
    bl_idname = "addmidi.stop"
    bl_label = "Stop AddMidi"
     
    def execute(self, context):
        if bpy.context.window_manager.addmidi_running == "Stopped":
            self.report({'INFO'}, "Stopping MIDI...")
        context.window_manager.addmidi_running = "Stopped"
        return{'FINISHED'}


class AddMIDI_StopButton(bpy.types.Operator):
    bl_idname = "addmidi.refresh_devices"
    bl_label = "Refresh the list of MIDI devices"
     
    def upd_midiin(self, context):     
        set_midiin(bpy.context.window_manager.midi_in_device)
        upd_setting_1()
    
    def upd_midiout(self, context):
        set_midiout(bpy.context.window_manager.midi_out_device)
        upd_setting_2()

    def refresh_midi_in_devices(self,context):
        b = midi_in_list
        return b

    def refresh_midi_out_devices(self,context):    
        b = midi_out_list
        return b
       
    def refresh_devices(self):   
        global midi_in_list, midi_out_list, midiin, midiout
                             
        b=[]
        a=("None","None", "None")
        b.append(a)
        for i in midiin.get_ports():
            a = (i,i,i)
            b.append(a)
        midi_in_list = b
        
        b=[]
        a=("None","None", "None")
        b.append(a)
        for i in midiout.get_ports():
            a = (i,i,i)
            b.append(a)
        midi_out_list = b

   
    refresh_devices(0) #trick to be able to call the function
    bpy.types.WindowManager.midi_in_device = bpy.props.EnumProperty(name="MIDI In Ports", items=refresh_midi_in_devices, update=upd_midiin)   
    bpy.types.WindowManager.midi_out_device = bpy.props.EnumProperty(name = "MIDI Out Ports", items = refresh_midi_out_devices, update=upd_midiout)

    def execute(self, context):
        self.refresh_devices()          
        return{'FINISHED'}



class AddMIDI_list_as_text(bpy.types.Operator):
    bl_idname = "addmidi.list2text"
    bl_label = "Save a list of keys as text"
     
    def execute(self, context):
        #Check if our text file already exists if not create it
        text = None
        for t in bpy.data.texts:
            if t.name == 'AddMIDI_items_list':
                text = t
                text.clear()
        if text == None:
            bpy.ops.text.new()
            text = bpy.data.texts[-1]
            text.name = 'AddMIDI_items_list'
        
        #Serialize the data
        for item in bpy.context.scene.MIDI_keys:
            text.write(item.name+"\n")
            text.write(str(item.channel)+"\n")
            text.write(item.cont_type+"\n")
            if item.cont_type != 'note_off' and item.cont_type != 'note_on' and item.cont_type != 'vel':
                if item.cont_type == 'rpn14' or item.cont_type == 'nrpn14':
                    text.write(str(item.controller14)+"\n")
                else:
                    text.write(str(item.controller)+"\n")
            text.write(str(item.min)+"\n")
            text.write(str(item.max)+"\n")
            text.write("\n")
        
        return{'FINISHED'}

    
class AddMIDI_text_to_list(bpy.types.Operator):
    bl_idname = "addmidi.text2list"
    bl_label = "Import keys from text"
    
    def execute(self, context):
        #Check if our text file already exists if not warn and quit
        text_items_list = None
        for t in bpy.data.texts:
            if t.name == 'AddMIDI_items_list':
                text_items_list = t
        if text_items_list == None:
            self.report({'INFO'}, "Missing Text File !")
            return{'FINISHED'}
        
        #Parse the file
        bpy.context.scene.MIDI_keys.clear()
        counter = 0
        try:
            for l in text_items_list.lines:
                #Counter reset
                if l.body == '':
                    counter = 0
                #Property Name    
                if counter == 0 and l.body != '':
                    keys_list = bpy.context.scene.MIDI_keys.add()
                    keys_list.name = l.body
                    counter = counter + 1
                #Channel
                elif counter == 1:
                    keys_list.channel = int(l.body)
                    counter = counter + 1
                #Property type
                elif counter == 2:
                    keys_list.cont_type = l.body
                    if l.body == 'note_off' or l.body == 'note_on' or l.body == 'vel':
                        counter = counter + 2
                    else:
                        counter = counter + 1   
                #Controller value
                elif counter == 3:
                    if keys_list.cont_type == 'rpn14' or keys_list.cont_type == 'nrpn14':
                        keys_list.controller14 = int(l.body)
                    else:
                        keys_list.controller = int(l.body)
                    counter = counter + 1
                #Min
                elif counter == 4:  
                    keys_list.min = int(l.body)
                    counter = counter + 1
                #Max
                elif counter == 5:  
                    keys_list.max = int(l.body)
                    counter = counter + 1      
                #Try to catch some errors
                elif counter > 5:
                    raise ValueError('Invalid section found')
        except:
            self.report({'INFO'}, "Error found !")
                
        return{'FINISHED'}
            


     
class AddMIDI_Import_KS_button(bpy.types.Operator):
    bl_idname = "addmidi.importks"
    bl_label  = "Import Keying Set for AddMIDI" 
       
    list = (('note_on','Note On',''),
            ('note_off','Note Off',''),
            ('on_off','Note On & Note Off',''),
            ('vel','Velocity','',),
            #('aft','aftertouch','',),
            ('cc7','Continous Controller 7bit','',),
            ('rpn','RPN 7bit','',),
            ('rpn14','RPN 14 bit','',),
            ('nrpn','NRPN 7bit','',),
            ('nrpn14','NRPN 14 bit','',),
            ('','','',))
                          
    for l in list:
        MIDI_list_enum.append(l)
        
        
    class Scene_MIDI_Items(bpy.types.PropertyGroup):
        def upd_min(self, context):    
            if self.min >= self.max:
                self.min = self.max - 1 
        def upd_max(self, context):    
            if self.max <= self.min:
                self.max = self.max + 1 
        name = bpy.props.StringProperty(name="Key", default="Unknown")
        channel = bpy.props.IntProperty(name="Channel", min=1, max=16, default=1)
        controller = bpy.props.IntProperty(name="Controller number", min=1, max=128, default=1)
        controller14 = bpy.props.IntProperty(name="Controller number", min=1, max=16384, default=1)
        min = bpy.props.IntProperty(name="Min", default=0, update=upd_min)
        max = bpy.props.IntProperty(name="Max", default=127, update=upd_max)
        cont_type = bpy.props.EnumProperty(name = "Event type", items = MIDI_list_enum)
    bpy.utils.register_class(Scene_MIDI_Items) #necessary ?
    
    bpy.types.Scene.MIDI_keys = bpy.props.CollectionProperty(type=Scene_MIDI_Items)
 
    def execute(self, context):
 
        ks = bpy.context.scene.keying_sets.active
        bpy.context.scene.MIDI_keys.clear()
        tvar2 = ""
        id_n = 0

        if str(ks) != "None":
            for items in ks.paths:               
                if str(items.id) != "None":     #workaround to avoid bad ID Block (bug with Nodes)
                    
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
                        print("AddMIDI -- Imported keys:\n"+i)
                else:
                    self.report({'INFO'}, "Missing ID block !")
                                                         
        else:
            self.report({'INFO'}, "None found !")         
        
        return{'FINISHED'}        

#Restore saved settings
@persistent
def addmidi_handler(scene):
    global error_device
    for text in bpy.data.texts:
        if text.name == '.addmidi_settings':
            bpy.context.window_manager.autorun = int(text.lines[0].body)
            try:
                bpy.context.window_manager.midi_in_device  = text.lines[1].body
            except:
                error_device = True
                print("AddMIDI Error: MIDI In device not found")
            try:
                bpy.context.window_manager.midi_out_device = text.lines[2].body
            except:
                error_device = True
                print("AddMIDI Error: MIDI Out device not found")
            try:
                bpy.context.window_manager.rate = int(text.lines[3].body) 
            except:
                bpy.context.window_manager.rate = 10
            
            if error_device == True:
                bpy.context.window_manager.autorun = False

            if bpy.context.window_manager.autorun == True:
                bpy.ops.addmidi.start()    

def register():
    bpy.utils.register_module(__name__)
    bpy.app.handlers.load_post.append(addmidi_handler)
    
def unregister():
    bpy.utils.unregister_module(__name__)
 
if __name__ == "__main__": 
    register()
 
 

