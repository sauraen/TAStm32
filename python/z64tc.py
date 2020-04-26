#!/usr/bin/env python3
import sys
import os
import serial
import struct
import time
import gc
import psutil

import serial_helper
import argparse_helper

DEBUG = False

int_buffer = 1000 # internal buffer size on replay device

class CRC():
    def __init__(self):
        self.table = []
        for i in range(256):
            r = i
            for counter in range(8):
                r = (0 if (r & 1) else 0xEDB88320) ^ (r >> 1)
                self.table.append(r ^ 0xFF000000)
    
    def crc(self, data):
        state = 0
        for i in range(len(data)):
            state = self.table[(state & 0xFF) ^ data[i]] ^ (state >> 8)
            return state

class Z64TC():
    def __init__(self, ser, runfilepath):
        att = 0
        while att < 5:
            try:
                self.ser = serial.Serial(ser, 115200, timeout=0)
                break
            except serial.SerialException:
                att += 1
                self.ser = None
                continue
        if self.ser == None:
            print ('ERROR: the specified interface (' + ser + ') is in use')
            sys.exit(0)
        assert(runfilepath.endswith('.txt'))
        self.runfilepath = runfilepath
        self.runfile = open(runfilepath, 'r')
        print('Opened runfile ' + runfilepath)
        self.ifile = None
        self.ifileaddr = None
        self.ifilepos = 0
        self.crc = CRC()
    
    def __del__(self):
        print('Exiting')
        self.ser.close()
        self.runfile.close()

    def write(self, data):
        count = self.ser.write(data)
        if DEBUG and data != b'':
            print('S:', data)
        return count

    def read(self, count):
        data = self.ser.read(count)
        if DEBUG and data != b'':
            print('R:', data)
        return data

    def reset(self):
        c = self.read(1)
        if c == '':
            pass
        else:
            numBytes = self.ser.inWaiting()
            if numBytes > 0:
                c += self.read(numBytes)
        self.write(b'R')
        time.sleep(0.1)
        data = self.read(2)
        if data == b'\x01R':
            print('Reset acknowledged')
        else:
            raise RuntimeError('Error during reset')

    def setup_run(self):
        self.write(b'SAZ\x70\x00')
        time.sleep(0.1)
        data = self.read(2)
        if data == b'\x01S':
            print('Setup acknowledged')
        else:
            raise RuntimeError('Error during setup')

    def read_replies(self):
        rumble_replies = []
        c = self.read(1)
        if len(c) == 0:
            return rumble_replies
        numExtraBytes = self.ser.inWaiting()
        if numExtraBytes > 0:
            c += self.read(numExtraBytes)
        #print('Received:', str(c))
        
        unk_cmd_args = ['player', 'sercmd', 'bytes']
        mempak_cmd_args = ['player', 'addr hi', 'addr lo', 'd[0]']
        responses = [
            {'c': 0x41, 'l': 1, 's': 'Poll', 'a': ['player']},
            {'c': 0x80, 'l': 0, 's': 'Acknowledge TC buffer command', 'a': []},
            {'c': 0x81, 'l': 0, 's': 'Acknowledge TC buffered reset', 'a': []},
            {'c': 0xB0, 'l': 0, 's': 'Buffer Overflow', 'a': []},
            {'c': 0xB2, 'l': 0, 's': 'Buffer Underflow', 'a': []},
            {'c': 0xB3, 'l': 0, 's': 'Buffer Empty (normal at end of run)', 'a': []},
            {'c': 0xC0, 'l': 4, 's': 'Ser Cmd Receive Error', 'a': ['player', 'sercmd', 'd0', 'd1']},
            {'c': 0xC1, 'l': 3, 's': 'Ser Cmd Bad Length', 'a': unk_cmd_args},
            {'c': 0xC2, 'l': 3, 's': 'Unsupported Ser Cmd', 'a': unk_cmd_args},
            {'c': 0xC3, 'l': 2, 's': 'Players out of order', 'a': ['player', 'expected player']},
            {'c': 0xC4, 'l': 1, 's': 'Identity', 'a': ['player']},
            {'c': 0xC5, 'l': 1, 's': 'Controller reset', 'a': ['player']},
            {'c': 0xC6, 'l': 3, 's': 'Mempak read', 'a': mempak_cmd_args[:-1]},
            {'c': 0xC7, 'l': 4, 's': 'Mempak write', 'a': mempak_cmd_args},
            {'c': 0x90, 'l': 0, 's': 'Rumble received: 000 (Error)', 'a': []},
            {'c': 0x91, 'l': 0, 's': 'Rumble received: 001 (CRC Fail)', 'a': []},
            {'c': 0x92, 'l': 0, 's': 'Rumble received: 010 (Q False)', 'a': []},
            {'c': 0x93, 'l': 0, 's': 'Rumble received: 011 (Q True)', 'a': []},
            {'c': 0x94, 'l': 0, 's': 'Rumble received: 100 (Cmd Invalid)', 'a': []},
            {'c': 0x95, 'l': 0, 's': 'Rumble received: 101 (Nop OK)', 'a': []},
            {'c': 0x96, 'l': 0, 's': 'Rumble received: 110 (Cmd OK)', 'a': []},
            {'c': 0x97, 'l': 0, 's': 'Rumble received: 111 (Error)', 'a': []},
            {'c': 0x98, 'l': 0, 's': 'New TC command when last not finished', 'a': []},
            {'c': 0x99, 'l': 0, 's': 'TC command buffer overflow', 'a': []},
            {'c': 0x9A, 'l': 0, 's': 'Mempak read cmd wrong len', 'a': []},
            {'c': 0x9B, 'l': 0, 's': 'Mempak write cmd wrong len', 'a': []},
            {'c': 0x9C, 'l': 0, 's': 'Mempak cmd bad addr CRC', 'a': []},
            {'c': 0x9D, 'l': 0, 's': 'Received rumble not 0/1', 'a': []},
            {'c': 0xFF, 'l': 0, 's': 'Unknown serial command', 'a': []},
        ]
        i = 0
        while i < len(c):
            cmd = c[i]
            i += 1
            resp = next((r for r in responses if r['c'] == cmd), None)
            if resp is None:
                print('Byte ', hex(cmd))
                continue
            if len(c) - i < resp['l']:
                print('Incomplete', resp['s'])
                continue
            if cmd >= 0x90 and cmd <= 0x97:
                rumble_replies.append(cmd)
            print(resp['s'], *[resp['a'][j] + '=' + hex(c[i+j]) + ',' for j in range(resp['l'])])
            i += resp['l']
        return rumble_replies

    def get_next_file(self):
        l = self.runfile.readline()
        if not l:
            return None
        l = l.strip()
        toks = [t for t in l.split(' ') if t]
        if toks[0] == 'FIXED':
            ifilepath = self.runfilepath[:self.runfilepath.rfind('/')] + '/' + toks[1]
            with open(ifilepath, 'rb') as i:
                self.ifile = i.read()
            self.ifileaddr = None
            with open(ifilepath[:-4] + '.out.ld') as ld:
                for ldl in ld:
                    ldtoks = [t for t in ldl.strip().split(' ') if t]
                    assert(len(ldtoks) == 3)
                    assert(ldtoks[1] == '=')
                    assert(ldtoks[2][-1] == ';')
                    if ldtoks[0].endswith('_START'):
                        self.ifileaddr = int(ldtoks[2][:-1], 16)
                        break
            if not self.ifileaddr:
                raise RuntimeError('Could not find start address for fixed injection data file')
            self.ifilepos = 0
            print('Injecting ' + ifilepath + ' to ' + hex(self.ifileaddr))
            return True
        else:
            raise ValueError('Unknown run file type: ' + toks[0])
            
    def get_next_command(self):
        sendbytes = len(self.ifile) - self.ifilepos
        if sendbytes == 0:
            return None
        elif sendbytes >= 81:
            sendbytes = 81
            cmd_without_crc = struct.pack('>I81sB', self.ifileaddr + self.ifilepos, 
                self.ifile[self.ifilepos:self.ifilepos+81], 1)
        else:
            cmd_without_crc = struct.pack('>I80sBB', self.ifileaddr + self.ifilepos,
                self.ifile[self.ifilepos:], sendbytes, 2)
        self.ifilepos += sendbytes
        return struct.pack('>I86s', self.crc.crc(cmd_without_crc), cmd_without_crc)
        
    def ifile_reset():
        print('Resetting injection of ' + self.ifileaddr)
        self.ifilepos = 0

    def command_to_controllers(self, cmd):
        assert(len(cmd) == 90)
        d = bytearray(cmd + b'\0\0\0\0\0\0')
        temp = 0
        for j in range(92>>2, -1, -1):
            temp <<= 2
            b = d[(j<<2)+1]
            temp |= b >> 6
            d[(j<<2)+1] = b & 0x3F
        for j in range(95, 89, -1):
            d[j] = temp & (0x3F if j == 93 else 0xFF)
            temp >>= (6 if j == 93 else 8)
        return b'\x80' + bytes(d)
        #return b'\x80' + b'\x00' * 96

    def main_loop(self):
        try:
            while True:
                if not self.get_next_file():
                    print('End of injection')
                    return
                def reset_file():
                    nonlocal in_flight, nothing_happened, cmd
                    self.ifilepos = 0
                    in_flight = 0
                    nothing_happened = 0
                    cmd = self.get_next_command()
                    self.write(b'\x81')
                reset_file()
                while True:
                    if cmd is not None and in_flight < int_buffer:
                        ctrl_cmd = self.command_to_controllers(cmd)
                        print('Multipoll:', ctrl_cmd)
                        self.write(ctrl_cmd)
                        cmd = self.get_next_command()
                        in_flight += 1
                    rumble_replies = self.read_replies()
                    for rr in rumble_replies:
                        if rr == 0x95:
                            # Nop
                            pass
                        elif rr == 0x96:
                            # OK
                            in_flight -= 1
                            nothing_happened = 0
                        else:
                            # Bad cmd / error / etc.
                            print('Injection error, restarting file!')
                            reset_file()
                    nothing_happened += 1
                    if nothing_happened >= 100000:
                        print('Nothing happened for too long, restarting file!')
                        reset_file()
                    if cmd is None and in_flight == 0:
                        break
        except serial.SerialException:
            print('ERROR: Serial Exception caught!')
        except KeyboardInterrupt:
            print('^C Exiting')

def main():
    global DEBUG

    if(os.name == 'nt'):
        psutil.Process().nice(psutil.REALTIME_PRIORITY_CLASS)
    else:
        psutil.Process().nice(20) #it's -20, you bozos
    gc.disable()
    
    assert(sys.argv[1].endswith('.txt'))
    dev = Z64TC(serial_helper.select_serial_port(), sys.argv[1])
    
    dev.reset()
    dev.setup_run()
    print('Main Loop Start')
    dev.main_loop()
    dev.reset()
    sys.exit(0)

if __name__ == '__main__':
    main()
