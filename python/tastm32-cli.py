#!/usr/bin/env python3
import gc
import os
import psutil
import time
import sys
import glob
import threading
import serial_helper
import argparse_helper
import tastm32
import r08, r16m, m64
import rundata
import cmd
import signal # Handle InteruptSignals

# import the proper readline module based on the user's operating system
if(os.name == 'nt'):
    from pyreadline import Readline
    readline = Readline()
else:
    import readline
    
dev = None
runStatuses = [] # list of currently active runs and their statuses
selected_run = -1

CONTROLLER_NORMAL = 0  # 1 controller
CONTROLLER_Y = 1  #: y-cable [like half a multitap]
CONTROLLER_MULTITAP = 2  #: multitap (Ports 1 and 2 only) [snes only]
CONTROLLER_FOUR_SCORE = 3  #: four-score [nes-only peripheral that we don't do anything with]

# Default Options for new runs
DEFAULTS = {'contype': 'normal',
            'overread': 0,
            'dpcmfix': 'False',
            'windowmode': 0,
            'dummyframes': 0}

# Readline Config
def complete(text, state):
    return (glob.glob(text + '*') + [None])[state]
def complete_nostate(text, *ignored):
    return glob.glob(text + '*') + [None]
    
def isConsolePortAvailable(port, type):
    return True  # passed all checks
    
    # types implemented int,str,float,bool
# constraints only work on int and float
def get_input(type, prompt, default='', constraints={}):
    while True:
        try:
            data = input(prompt)
            if data == default == None:
                print('ERROR: No Default Configured')
                continue
            if data == '' and default != '':
                return default
            if type == 'int':
                data = int(data)
            if type == 'float':
                data = float(data)
            if 'min' in constraints:
                if data < constraints['min']:
                    print('ERROR: Input less than Minimium of ' + str(constraints['min']))
                    continue
            if 'max' in constraints:
                if data > constraints['max']:
                    print('ERROR: Input greater than maximum of ' + str(constraints['max']))
                    continue
            if 'interval' in constraints:
                if data % constraints['interval'] != 0:
                    print('ERROR: Input does not match interval of ' + str(constraints['max']))
                    continue
            if type == 'int':
                try:
                    return int(data)
                except ValueError:
                    print('ERROR: Expected integer')
            if type == 'float':
                try:
                    return float(data)
                except ValueError:
                    print('ERROR: Expected float')
            if type == 'str':
                try:
                    return str(data)
                except ValueError:
                    print('ERROR: Expected string')
            if type == 'bool':
                if data.lower() in (1,'true','y','yes'):
                    return True
                elif data.lower() in (0,'false','n','no'):
                    return False
                else:
                    print('ERROR: Expected boolean')
        except EOFError:
            # print('EOF')
            return None
            
class RunStatus(object):
    tasRun = None
    inputBuffer = None
    customCommand = None
    isRunModified = None
    dpcmState = None
    windowState = None
    frameCount = 0
    defaultSave = None
    isLoadedRun = False
    runOver = False

# return false exits the function
# return true exits the whole CLI
class CLI(cmd.Cmd):
    def __init__(self):
        cmd.Cmd.__init__(self)
        self.setprompt()
        self.intro = "\nWelcome to the TAS command-line interface!\nType 'help' for a list of commands.\n"
    
    def setprompt(self):
        if selected_run == -1:
            self.prompt = "TAStm32> "
        else:
            if runStatuses[selected_run].isRunModified:
                self.prompt = "TAStm32[#" + str(selected_run + 1) + "][" + str(
                    runStatuses[selected_run].dummyFrames) + "f][UNSAVED]> "
            else:
                self.prompt = "TAStm32[#" + str(selected_run + 1) + "][" + str(
                    runStatuses[selected_run].dummyFrames) + "f]> "

    def postcmd(self, stop, line):
        self.setprompt()
        return stop

    def complete(self, text, state):
        if state == 0:
            origline = readline.get_line_buffer()
            line = origline.lstrip()
            stripped = len(origline) - len(line)
            begidx = readline.get_begidx() - stripped
            endidx = readline.get_endidx() - stripped
            compfunc = self.custom_comp_func
            self.completion_matches = compfunc(text, line, begidx, endidx)
        try:
            return self.completion_matches[state]
        except IndexError:
            return None
    
    def custom_comp_func(self, text, line, begidx, endidx):
        return self.completenames(text, line, begidx, endidx) + self.completedefault(text, line, begidx, endidx)

    # complete local directory listing
    def completedefault(self, text, *ignored):
        return complete_nostate(text)  # get directory when it doesn't know how to autocomplete

    # do not execute the previous command! (which is the default behavior if not overridden
    def emptyline(self):
        return False
        
    def do_exit(self, data):
        """Not 'goodbyte' but rather so long for a while"""
        return True
        
    def do_new(self, data):
        """Create a new run with parameters specified in the terminal"""
        global selected_run

        # get input file
        while True:
            fileName = get_input(type = 'str',
                prompt = 'What is the input file (path to filename) ? ')
            if fileName == None:
                return False
            if not os.path.isfile(fileName):
                print('ERROR: File does not exist!')
                continue
            else:
                break

        # get ports to use
        while True:
            try:
                breakout = True
                portsList = get_input(type = 'str',
                    prompt = 'Which physical controller port numbers will you use (1-4, commas between port numbers)? ')
                if portsList == None:
                    return False
                portsList = list(map(int, portsList.split(",")))  # splits by commas or spaces, then convert to int
                numControllers = len(portsList)
                for port in portsList:
                    if port not in range(1, 5):  # Top of range is exclusive
                        print("ERROR: Port out of range... " + str(port) + " is not between (1-4)!\n")
                        breakout = False
                        break
                    if not isConsolePortAvailable(port, CONTROLLER_NORMAL):  # check assuming one lane at first
                        print("ERROR: The main data lane for port " + str(port) + " is already in use!\n")
                        breakout = False
                        break
                if any(portsList.count(x) > 1 for x in portsList):  # check duplciates
                    print("ERROR: One of the ports was listed more than once!\n")
                    continue
                if breakout:
                    break
            except ValueError:
                print("ERROR: Please enter integers!\n")

        # get controller type
        while True:
            breakout = True
            controllerType = get_input(type = 'str',
                prompt = 'What controller type does this run use ([n]ormal, [y], [m]ultitap, [f]our-score) [def=' + DEFAULTS['contype'] + ']? ',
                default = DEFAULTS['contype'])
            if controllerType == None:
                return False
            if controllerType.lower() not in ["normal", "y", "multitap", "four-score", "n", "m", "f"]:
                print("ERROR: Invalid controller type!\n")
                continue
            if controllerType.lower() == "normal" or controllerType.lower() == "n":
                controllerType = CONTROLLER_NORMAL
            elif controllerType.lower() == "y":
                controllerType = CONTROLLER_Y
            elif controllerType.lower() == "multitap" or controllerType.lower() == "m":
                controllerType = CONTROLLER_MULTITAP
            elif controllerType.lower() == "four-score" or controllerType.lower() == "f":
                controllerType = CONTROLLER_FOUR_SCORE
            for x in range(len(portsList)):
                if not isConsolePortAvailable(portsList[x], controllerType):  # check ALL lanes
                    print("ERROR: One or more lanes is in use for port " + str(portsList[x]) + "!\n")
                    breakout = False
            if breakout:
                break

        # 8, 16, 24, or 32 bit
        while True:
            # determine default controller bit by checking input file type
            ext = os.path.splitext(fileName)[1]
            cbd = ""
            if ext == ".r08":
                cbd = 8
            if ext == ".r16m":
                cbd = 16
            controllerBits = get_input(type = 'int',
                prompt = 'How many bits of data per controller (8, 16, 24, or 32) [def=' + str(cbd) + ']? ',
                default = cbd,
                constraints = {'min': 8, 'max': 32, 'interval': 8})
            if controllerBits == None:
                    return False
            if controllerBits != 8 and controllerBits != 16 and controllerBits != 24 and controllerBits != 32:
                print("ERROR: Bits must be either 8, 16, 24, or 32!\n")
            else:
                break

        # overread value
        overread = get_input(type = 'int',
            prompt = 'Overread value (0 or 1) [def=' + str(DEFAULTS['overread']) + ']? ',
            default = DEFAULTS['overread'],
            constraints = {'min': 0, 'max': 1})
        if overread == None:
            return False

        # DPCM fix
        dpcmFix = get_input(type = 'bool',
            prompt = 'Apply DPCM fix (y/n) [def=' + str(DEFAULTS['dpcmfix']) + ']? ',
            default = DEFAULTS['dpcmfix'])
        if dpcmFix == None:
            return False

        # window mode 0-15.75ms
        window = get_input(type = 'float',
            prompt = 'Window value (0 to disable, otherwise enter time in ms. Must be multiple of 0.25ms. Must be between 0 and 15.75ms) [def=' + str(DEFAULTS['windowmode']) + ']? ',
            default = DEFAULTS['windowmode'],
            constraints = {'min': 0, 'max': 15.75, 'interval': 0.25})
        if window == None:
            return False

        # dummy frames
        dummyFrames = get_input(type = 'int',
            prompt = 'Number of blank input frames to prepend [def=' + str(DEFAULTS['dummyframes']) + ']? ',
            default = DEFAULTS['dummyframes'],
            constraints = {'min': 0})
        if dummyFrames == None:
            return False

        # create TASRun object and assign it to our global, defined above
        #tasrun = TASRun(numControllers, portsList, controllerType, controllerBits, overread, window, fileName, dummyFrames, dpcmFix)

        # create the RunStatus object
        rs = RunStatus()
        rs.customCommand = None
        rs.inputBuffer = None
        rs.dummyFrames = dummyFrames
        rs.isRunModified = True
        rs.dpcmState = dpcmFix
        rs.windowState = window
        # Remove Extension from filename 3 times then add ".tcf" to generate a Default Save Name
        rs.defaultSave = os.path.splitext(os.path.splitext(os.path.splitext(fileName)[0])[0])[0] + ".tcf"
        runStatuses.append(rs)

        selected_run = len(runStatuses) - 1
        #send_frames(selected_run, prebuffer)
        print("Run is ready to go!")
        
        # start the device in its own thread
        # TODO: gather all of the necessary information
        ##t = threading.Thread(target=tastm32.main_multi, args=(dev, cli_args, data))
        ##t.start()

def setup():
    # high priority
    if(os.name == 'nt'):
        psutil.Process().nice(psutil.REALTIME_PRIORITY_CLASS)
    else:
        psutil.Process().nice(20)

    # disable garbate collection for performance reasons
    gc.disable()

    # custom CLI options
    readline.set_completer_delims(' \t\n')
    readline.parse_and_bind('tab: complete')
    readline.set_completer(complete)
    
    # Catch Ctrl+C
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    
def detect_and_choose_device():
    ''' 0 = tastm32, 1 = psoc, 2 = taslink '''
    # TODO: scan and list all available devices. then, let the user choose
    # TAStm32: hardcoded as default into serial_helper
    # TASLink: VID=0x0403, PID=0x6010
    # PSoC5: VID=0x04b4, PID=0xf232
    return 0

def main():
    setup()
    
    devNum = detect_and_choose_device()
    
    if devNum == 0: # tastm32
        dev = tastm32.TAStm32(serial_helper.select_serial_port())
    
        # reset the device to ensure it is ready
        dev.reset()
    elif devNum == 1: # psoc
        pass
    elif devNum == 2: # taslink
        pass
    else: # unknown device
        pass
    
    # start CLI in the main thread
    cli = CLI()
    cli.cmdloop()
    
    # cleanup
    dev.ser.close()
    sys.exit(0)

if __name__ == '__main__':
    main()
