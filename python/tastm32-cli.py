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
from pyreadline import Readline

readline = Readline()
selected_run = -1

# Readline Config
def complete(text, state):
    return (glob.glob(text + '*') + [None])[state]
def complete_nostate(text, *ignored):
    return glob.glob(text + '*') + [None]

# return false exits the function
# return true exits the whole CLI
class CLI(cmd.Cmd):
    def __init__(self):
        cmd.Cmd.__init__(self)
        self.setprompt()
        self.intro = "\nWelcome to the TASLink command-line interface!\nType 'help' for a list of commands.\n"
    
    def setprompt(self):
        if selected_run == -1:
            self.prompt = "TAStm32> "
        else:
            if runStatuses[selected_run].isRunModified:
                self.prompt = "TAStm32[#" + str(selected_run + 1) + "][" + str(
                    runStatuses[selected_run].tasRun.dummyFrames) + "f][UNSAVED]> "
            else:
                self.prompt = "TAStm32[#" + str(selected_run + 1) + "][" + str(
                    runStatuses[selected_run].tasRun.dummyFrames) + "f]> "

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

def startup():
    if(os.name == 'nt'):
        psutil.Process().nice(psutil.REALTIME_PRIORITY_CLASS)
    else:
        psutil.Process().nice(20)

    gc.disable()

    readline.set_completer_delims(' \t\n')
    readline.parse_and_bind('tab: complete')
    readline.set_completer(complete)
    
    return tastm32.TAStm32(serial_helper.select_serial_port())

def main():
    dev = startup()
    
    # reset the device to ensure it is ready
    dev.reset()
    
    # Catch Ctrl+C from interupting the mainloop
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    # start CLI in its own thread
    cli = CLI()
    t = threading.Thread(target=cli.cmdloop)  # no parens on cmdloop is important... otherwise it blocks
    t.start()
    
    while t.isAlive():
        time.sleep(0.1)
        pass
    
    dev.ser.close()
    sys.exit(0)

if __name__ == '__main__':
    main()