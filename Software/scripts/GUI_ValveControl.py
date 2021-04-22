import tkinter as tk
from tkinter import ttk
from tkinter import font as tkFont
import datetime
import time
import os
import math
import collections
import gc

import PlotCanvas
import ExtraWidgets
import DataBuffer
import configLoader
import support
import const

colors = configLoader.load_confDict("../config/default/colors.cfg")

MAX_VALVES_PER_COLUMN = const.MAX_VALVES_PER_COLUMN


def check_valveCfg(cfg):
    # make sure that a group and state is assigned (even if not specified in cfg file)
    for ID in cfg["ID"].keys():
        if not "group" in cfg["ID"][ID].keys():
            cfg["ID"][ID]["group"] = "A"

        if not "state" in cfg["ID"][ID].keys():
            cfg["ID"][ID]["state"] = 1

    if not "sequence" in cfg.keys():            
        cfg["sequence"] = [cfg["ID"][key]["name"] for key in cfg["valve"].keys()]
    else:
        sequence = []
        for item in cfg["sequence"]:
            if item in cfg["ID"].keys():
                sequence.append(item)
            else:
                print("Sequence element '%s' is missing in ID-table and will be ignored"%item)
        cfg["sequence"] = sequence

    if "initialID" in cfg.keys():
        if not cfg["initialID"] in cfg["ID"]:
            del cfg["initialID"]

    return cfg

class Valve():
    def __init__(self, ID, slot, probeType, button, stateVar, group="A"):

        self.ID = ID

        try:
            splitSlot = slot.split('#')
            self.box  = int(splitSlot[0])
            self.slot = int(splitSlot[1])
        except:
            self.box  = 0
            self.slot =int(slot)

        self.probeType = probeType
        self.button = button        
        self.stateVar = stateVar        
        self.group = group

        toolTip = ExtraWidgets.ToolTip(button, text = "%s (%s)\n"%(ID,probeType)+
                                                      "slot %d of box %d\n"%(self.slot,self.box)+
                                                      "Left click: flush/measure\n"+
                                                      "Right click: enable/disable")
        

    def grid(self, row, column, columnspan=1):
        self.button.grid(row=row, column=column, columnspan=columnspan, sticky = "nsew")        

    def __repr__(self):
        return("<\"%s\"(%s)>"%(self.ID, self.probeType))
        

class ValveControlFrame(tk.Frame):
    def __init__(self, master, vc, valveConfigFile = "../config/valve.cfg", *args, **kwargs):
        super(ValveControlFrame,self).__init__(master, *args, **kwargs)

        self.master = master
        self.vc=vc
        
        self.switchCode = const.SWITCH_START

        self.activeID = ""
        self.sequencePosition = -1
        self.flowMode = "measure"
        self.sequMode = "inactive"
        self.startTime = 0 

        self.conf = check_valveCfg(configLoader.load_confDict(valveConfigFile))

        # ----- prepare valve log file ----

        parActiveValve = DataBuffer.Parameter(name = "ID", unit = "active valve")
        parMeasurement = DataBuffer.Parameter(name = "measurement", unit = "state")
        parSwitchCode = DataBuffer.Parameter(name = "switchCode", unit = "%d = manual | %d = timeout | %d = optimal | %d = alert"\
                                                                          %(const.SWITCH_MANUAL, const.SWITCH_TIMEOUT,
                                                                            const.SWITCH_OPTIMUM, const.SWITCH_ALERT))
        
        self.valveBuffer = DataBuffer.Buffer(100, self.conf["logFile"], parameters = [parActiveValve, parMeasurement, parSwitchCode])

        #--------------------------------------------------------------
        if not vc.check_status():
            self.infoFrame = tk.Frame(master)
            self.infoFrame.place(relheight=1, relwidth=1, x=0, y=0)
            self.infoFrame.config(bg="#fbb")
            tk.Button(self.infoFrame, command=self.hide_infoFrame,
                      text="No valve controller connected\n Click to proceed without functional valve controller").pack(side=tk.TOP)
            

        # create basic frames for layout
        self.buttonFrame = tk.Frame(self)
        self.buttonFrame.grid(row=0, column=0, sticky="nsew")

        self.rightFrame = tk.Frame(self)       
        self.rightFrame.grid(row=0, column=1, sticky="nsew")

        self.rowconfigure(0, weight=1)        
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)

        # ---- right frame (mainly valve sequence)------------- -----------

        self.rightFrame.rowconfigure(0, weight=0)
        self.rightFrame.rowconfigure(1, weight=5)        
        self.rightFrame.columnconfigure(0, weight=1)        

        self.upperRightFrame = tk.Frame(self.rightFrame)
        self.upperRightFrame.grid(row=0, column=0, sticky="nsew")
        self.upperRightFrame.rowconfigure(0, weight=1)
        self.upperRightFrame.columnconfigure(0, weight=1)
        self.upperRightFrame.columnconfigure(1, weight=3)
        self.upperRightFrame.columnconfigure(2, weight=1)

        self.lowerRightFrame = tk.Frame(self.rightFrame)
        self.lowerRightFrame.grid(row=1, column=0, sticky="nsew")
        self.lowerRightFrame.rowconfigure(0, weight=1)        
        self.lowerRightFrame.columnconfigure(0, weight=0)
        self.lowerRightFrame.columnconfigure(1, weight=1)

        self.progressFrame = tk.Frame(self.lowerRightFrame)        
        self.progressFrame.grid(row=0, column=0, sticky="nsew")

        self.sequenceFrame = tk.Frame(self.lowerRightFrame)
        self.sequenceFrame.grid(row=0, column=1, sticky="nsew")        
        self.sequenceFrame.rowconfigure(1, weight=1)
        self.sequenceFrame.columnconfigure(0, weight=1)

        self.sequenceControlFrame = tk.Frame(self.sequenceFrame)
        self.sequenceControlFrame.grid(row=0, column=0, sticky="nsew")
        self.sequenceControlFrame.columnconfigure(0, weight=1)
        self.sequenceControlFrame.columnconfigure(1, weight=2)

        self.sequenceButtonFrame = tk.Frame(self.sequenceFrame)
        self.sequenceButtonFrame.grid(row=1, column=0, sticky="nsew")

        # ------------ create valve control buttons -------------------
        self.valveDict = self.fill_buttonFrame()      

        #-------- schedule, status and refresh -----------------------------
        self._scheduleButtonImage = tk.PhotoImage(file="../images/time_24.gif")
        self.scheduleButton = tk.Button(self.upperRightFrame, text="Schedule", image= self._scheduleButtonImage, command=self.schedule, width=24)
        self.scheduleButton.grid(row=0, column=0, sticky="nsew")
        ExtraWidgets.ToolTip(self.scheduleButton, u"To be implemented...")

        self.extraLabel = tk.Label(self.upperRightFrame, text="~~~~~~~~~~~", bg='#ddd')
        self.extraLabel.grid(row=0, column=1, sticky='nsew')
        self.extraLabel.bind("<Button-1>", self.extraLabel_click)

        self._refreshButtonImage = tk.PhotoImage(file="../images/refresh_16.gif")
        self.refreshButton = tk.Button(self.upperRightFrame, text="Refresh", image= self._refreshButtonImage, command=self.refresh_configuration)
        self.refreshButton.grid(row=0, column=2, sticky="nsew")
        ExtraWidgets.ToolTip(self.refreshButton, u"Reload flow profiles (from flow.cfg) and H\u2082O thresholds (from valve.cfg)\n"+\
                                                  "Changing the logfile path requires a restart")

        #-------- progress bars ------------------------------------------
        
        self.progBars = {}

        for mode, side, anchor in [("flush", 'bottom','n'),("measure", 'top', 's')]:            
            style = ttk.Style()
            style.configure("%s.Vertical.TProgressbar"%mode, background=colors[mode])
            progBar = ttk.Progressbar(self.progressFrame, style="%s.Vertical.TProgressbar"%mode, orient=tk.VERTICAL, maximum = 50, mode = 'determinate')
            label   = tk.Label(progBar, text=u"\u221e", bg=colors[mode],wraplength=1)
            label.place(relx=0.2,rely=0.5)            
            progBar.pack(side=side,anchor=anchor, expand=2, fill=tk.BOTH)

            self.progBars[mode] = {"bar": progBar, "label":label}

        #----- sequence buttons --------------------------------------

        self.valveSequence = self.fill_sequenceButtonFrame()                       

        #------ sequence control buttons--------------------------------
        self._sequenceButtonImages = []
        for name in ["start_32", "stop_32", "next_32", "hourglass_32"]:
            try:
                image = tk.PhotoImage(file="../images/"+name+".gif")
            except:
                image = None
            self._sequenceButtonImages.append(image)
            
        buttonFont = tkFont.Font(family="Sans", weight="bold")
        self.sequenceButton = tk.Button(self.sequenceControlFrame, command=self.toggle_sequence, 
                                        text="start\nsequence" , font=buttonFont,
                                        image=self._sequenceButtonImages[0])
        

        self.sequenceButton_skip = tk.Button(self.sequenceControlFrame, command= lambda: self.continueSequence(skip=True),
                                        text="start\nsequence" , font=buttonFont,
                                        image=self._sequenceButtonImages[2])
        
        self.sequenceButton.grid(row=0, column=0, sticky="nsew")
        self.sequenceButton_skip.grid(row=0, column=1, sticky="nsew")
            
        ExtraWidgets.ToolTip(self.sequenceButton, text="Start/Stop the valve sequence\nThe seuquence goes from left to right and from top to bottom")
        ExtraWidgets.ToolTip(self.sequenceButton_skip, text="Skip current valve and continue with the next one in the sequence")

        colors["neutralButton"] = self.sequenceButton.cget("bg")

        self.set_probeProfile()

        self._job = None
        self.sequencePaused = False        

        print("Giving the valve controller some time...")
        self.after(2500, self.startup)

    #---------------------------------------------    
    def startup(self):
        # open first valve
        
        for ID in self.valveDict.keys():            
            self.valveDict[ID].stateVar = self.conf["ID"][ID]["state"] > 0

        self.update_valveButtons()

        if "initialID" in self.conf.keys():
            self.sequencePosition = -0            
            for i, ID in enumerate(self.valveDict.keys()):
                if self.conf["initialID"] == ID:
                    self.activeID = ID
                    self.valveButton_click(i)
                    break

            self.switchCode = const.SWITCH_MANUAL
            
        else:            
            self.sequencePosition = -1
            i = self.get_nextValve()
            self.toggle_sequence()
            self.sequenceButton_click(i, withinSequence=True)
            self.switchCode = const.SWITCH_TIMEOUT
           
        self.set_probeProfile()
        self.update_progressBars()
        self.update_valveButtons()

    #---------------------------------------------   
    def fill_buttonFrame(self):

        for button in self.buttonFrame.grid_slaves():            
            button.destroy()       

        valveDict = collections.OrderedDict()        

        N = len(self.conf["ID"].keys())
        columnCount = math.ceil(N/MAX_VALVES_PER_COLUMN)
        rowCount = math.ceil(N/columnCount)

        
        for i, ID in enumerate(self.conf["ID"].keys()):
            button = tk.Button(self.buttonFrame, command = lambda j = i: self.valveButton_click(j),
                               font = tkFont.Font(family="Sans", size=9, weight="bold"), state = tk.DISABLED,
                               text = ID, bg=colors["group_"+self.conf["ID"][ID]["group"]], disabledforeground="#866")
            button.bind('<Button-3>', self.rightClick)


            stateVar = True          
                        
            valveDict[ID] = Valve(ID, self.conf["ID"][ID]["slot"],
                                      self.conf["ID"][ID]["profile"],
                                      button, stateVar, self.conf["ID"][ID]["group"])

            row = math.floor(i/columnCount)
            column = i-math.floor(row*columnCount)
            valveDict[ID].grid(row = row, column=column)
            self.buttonFrame.rowconfigure(row, weight=1)
            self.buttonFrame.columnconfigure(column, weight=1)        

        return valveDict

    #---------------------------------------------
    def fill_sequenceButtonFrame(self):

        for button in self.sequenceButtonFrame.grid_slaves():            
            button.destroy()

        valveSequence = []
        
        N = len(self.conf["sequence"])
        columnCount = math.ceil(N/MAX_VALVES_PER_COLUMN)
        rowCount = math.ceil(N/columnCount)

        
        for i, ID in enumerate(self.conf["sequence"]):           

            button = (tk.Button(self.sequenceButtonFrame, command = lambda j = i: self.sequenceButton_click(j),
                                font = tkFont.Font(family="Sans", size=9, weight="bold"), state = tk.DISABLED,
                                text = ID, bg = colors["group_"+self.conf["ID"][ID]["group"]]))
            button.bind('<Button-3>', self.rightClick)

            stateVar = True
            
            valveSequence.append(Valve(ID, self.conf["ID"][ID]["slot"],
                                           self.conf["ID"][ID]["profile"],
                                           button, stateVar, self.conf["ID"][ID]["group"]))

            row = math.floor(i/columnCount)
            column = i-math.floor(row*columnCount)
            valveSequence[-1].grid(row=row, column=column)
            self.sequenceButtonFrame.rowconfigure(row, weight=1)
            self.sequenceButtonFrame.columnconfigure(column, weight=1)

        return valveSequence
        
    #===============================================================================

    def extraLabel_click(self, event=None):
        print("No method defined for clicking on this label...")

    def schedule(self, dummy = None):
        print("no method defined for clicking on this button")

    def refresh_configuration(self):

        activeSlot = self.conf["ID"][self.activeID]["slot"]        
        
        self.conf = check_valveCfg(configLoader.load_confDict(self.conf["confFile"]))


        self.valveDict     = self.fill_buttonFrame()
        self.valveSequence = self.fill_sequenceButtonFrame()

        # these lines take care of cases where the previously active slot has been given to a new ID
        for ID in self.valveDict.keys():       
            if '%d#%d'%(self.valveDict[ID].box,self.valveDict[ID].slot) == activeSlot:
                self.activeID = ID
            self.valveDict[ID].stateVar = self.conf["ID"][ID]["state"] > 0

        self.update_valveButtons()


    def rightClick(self, event):

        origin = str(event.widget).split('.')[-2:]        

        origin[0] = origin[0].replace("!frame","")

        if not len(origin[0]):
            frame = "valves"
            offset = str(self.buttonFrame.winfo_children()[0]).split('.')[-1]            
        else:
            frame = "sequence"
            offset = str(self.sequenceButtonFrame.winfo_children()[0]).split('.')[-1]
                
        origin[1] = origin[1].replace("!button","")
        index = 0 if not len(origin[1]) else int(origin[1])-1

        offset = offset.replace("!button","")
        offset = 0 if not len(offset) else int(offset)-1

        index = index - offset

        ID = list(self.valveDict.keys())[index]
        
        if frame == "valves":           
            self.valveDict[ID].stateVar = not self.valveDict[ID].stateVar
        else:
            self.valveSequence[index].stateVar = not self.valveSequence[index].stateVar

        self.update_valveButtons()

    def hide_infoFrame(self, event=None):
        self.infoFrame.place_forget()

    def set_probeProfile(self, ID=None):

        if ID is None:
            ID = self.activeID
           
        if ID in self.conf["ID"].keys():
            try:
                probeType = self.conf["ID"][ID]["profile"]
                x=self.conf["profile"][probeType]
            except:
                print("Missing specifications for probe type \"%s\", resorting to default specifications"%probeType)
                x=self.conf["profile"]["default"]
        else:
            x=self.conf["profile"]["default"]
            

        for key in ["fRateA","fRateB","mRateA","mRateB"]:
            if not key in x.keys():
                x[key] = 0        

        self.currentProbeProfile = x.copy()
        self.currentProbeProfile["duration"] = self.currentProbeProfile["fDuration"] + self.currentProbeProfile["mDuration"]


    def toggle_flowMode(self, newMode=None):
        if newMode is None:
            newMode = ["measure","flush"] [self.flowMode=="measure"]

        change =  not self.flowMode == newMode       

        self.flowMode = newMode
        
        self.valveBuffer.add([self.activeID, [0,1][self.flowMode=="measure"], self.switchCode])

        self.switchCode = const.SWITCH_MANUAL if self.sequMode == "inactive" else const.SWITCH_TIMEOUT

        if change:            
            if newMode == "flush":
                self.startTime = time.time()

        self.update_valveButtons()

    def toggle_sequence(self, event=None):

        if not self._job is None:
            self.after_cancel(self._job)
            self._job = None

        if not self.sequMode == "active":
            self.sequMode = "active"
            self.sequenceButton.config(image=self._sequenceButtonImages[1], text="stop\nsequence")
            self._job = self.after(10, self.continueSequence)
            self.startTime = time.time()
        else:
            self.sequMode = "inactive"
            self.sequenceButton.config(image=self._sequenceButtonImages[0], text="start\nsequence")

        print("---toggle sequence---")
        self.update_valveButtons()
        self.update_progressBars()


    def currentDuration(self):
        return time.time()-self.startTime + 0.0001

    def flushedEnough(self):        
        return self.currentDuration() >= self.currentProbeProfile["fDuration"]

    def measuredEnough(self):
        return self.currentDuration() >= self.currentProbeProfile["mDuration"]


    def get_nextValve(self):
        remainingPart = list(range(self.sequencePosition+1, len(self.valveSequence)))
        passedPart = list(range(0, self.sequencePosition)) + [self.sequencePosition]        
        for nextPos in (remainingPart + passedPart):            
            ID = self.valveSequence[nextPos].ID
            baseValveState = self.valveDict[ID].stateVar.get()            
            
            if self.valveSequence[nextPos].stateVar.get() and baseValveState:
                break
        return nextPos

    def continueSequence(self, skip=False):

        nowTime = time.time()

        if self.flowMode == "flush" and self.flushedEnough():
            self.toggle_flowMode()            
            self.startTime = time.time()            

        if (self.flowMode == "measure" and self.measuredEnough()) or skip:
            self.sequenceButton_click(self.get_nextValve(), True)

        if skip:
            self.startTime = time.time()
        else:
            self._job = self.after(500, self.continueSequence)
            self.update_progressBars(self.currentDuration())      
        

    def sequenceButton_click(self, sequencePos, withinSequence=False):
        noChange = self.sequencePosition==sequencePos
        self.sequencePosition = sequencePos        
        self.activeID = self.valveSequence[sequencePos].ID
        self.open_valve(self.activeID, noChange, withinSequence)

    def valveButton_click(self, position):
        sequencePos = -1 # clicking directly on a valve button discards the current position within the sequence

        ID = list(self.valveDict.keys())[position]
        
        noChange = self.activeID == ID and self.sequencePosition == sequencePos
        self.activeID = ID
        self.sequencePosition = sequencePos        
        self.open_valve(ID, noChange)


    def update_valveButtons(self):

        buttonColors = [colors["neutralButton"], colors[self.flowMode]]
        
        masterButtonList = [self.valveDict[ID] for ID in self.valveDict.keys()]
        
        for n, buttonList in enumerate([masterButtonList, self.valveSequence]):            
            for i, button in enumerate(buttonList):

                buttonColors[0] = colors["group_"+button.group]
                
                index = [button.ID == self.activeID, i==self.sequencePosition][n]
                
                newCol = buttonColors[index]

                if button.button['bg'] != newCol:
                    button.button.config(bg=newCol, relief = [tk.RAISED, tk.GROOVE][index])                
                
                # deactivate button on the valveSequence level, when the corresponding valve button
                # has been deactivated
                if n == 1:                    
                    baseValveState = self.valveDict[button.ID].stateVar                
                else:
                    baseValveState = True               

                button.button.config(state = [tk.DISABLED, tk.NORMAL][baseValveState and button.stateVar])                

    def update_progressBars(self,duration=0):


        flushDuration = self.currentProbeProfile["fDuration"]        
        measureDuration = self.currentProbeProfile["mDuration"]        

        if duration:           
            self.progBars[self.flowMode]["bar"].configure(value=duration)
            maxDuration = self.currentProbeProfile[["mDuration","fDuration"][self.flowMode=="flush"]]
            self.progBars[self.flowMode]["label"].configure(text = "%.0f/%.0f"%(duration,maxDuration))
        else:            
            self.master.update()
            w = self.master.winfo_width()
            r = self.currentProbeProfile["fDuration"]/self.currentProbeProfile["duration"]            
            for flowMode, length in [("flush", w*r),("measure",w*(1-r))]:                
                maxDuration = self.currentProbeProfile[["mDuration","fDuration"][flowMode=="flush"]]
                self.progBars[flowMode]["bar"].configure(value=0, max=maxDuration, length=length)
                self.progBars[flowMode]["label"].configure(text = "%.0f/%.0f"%(duration,maxDuration))

    def open_valve(self, ID, noChange=False, withinSequence=False):

        if self.sequMode == "active" and not withinSequence:
            self.toggle_sequence()

        if noChange:
            self.toggle_flowMode()            
            
        else:
            print("------------------\nactive probe: "+ ID)
            self.vc.set_valve("%d#%d"%(self.valveDict[ID].box,self.valveDict[ID].slot))
            self.set_probeProfile(ID)
            self.toggle_flowMode("flush")
            
        self.update_valveButtons()
        self.update_progressBars()

        return


if __name__ == "__main__":
    import SerialDevices
    dInfo = SerialDevices.find_device("IsWISaS_Controller", [9600], cachePath = "../temp/serial.cch")   
    try:
        vc = SerialDevices.IsWISaS_Controller(dInfo["port"], dInfo["baudRate"])
    except:
        vc = SerialDevices.IsWISaS_Controller("foobar", 0)

    root = tk.Tk()
    root.title("ValveController")
    root.geometry("%dx%d+%d+%d"%(250,800,1,0))    
    g = ValveControlFrame(root, vc, valveConfigFile = "../config/valve.cfg", relief=tk.RAISED)
    g.pack(fill=tk.BOTH, expand=1)
    root.mainloop()
        
        
