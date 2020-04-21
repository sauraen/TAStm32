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

int_buffer = 1024 # internal buffer size on replay device

int_to_byte_struct = struct.Struct('B')
def int_to_byte(integer):
    return int_to_byte_struct.pack(integer)

class TAStm32():
    def __init__(self, ser):
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

    def main_loop(self):
        while True:
            try:
                c = self.read(1)
                if len(c) == 0:
                    continue
                numExtraBytes = self.ser.inWaiting()
                if numExtraBytes > 0:
                    c += self.read(numExtraBytes)
                #print('Received:', str(c))
                
                unk_cmd_args = ['player', 'sercmd', 'bytes']
                mempak_cmd_args = ['player', 'addr hi', 'addr lo', 'd[0]']
                responses = [
                    {'c': 0x41, 'l': 1, 's': 'Poll', 'a': ['player']},
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
                    {'c': 0x90, 'l': 0, 's': 'Rumble received: 000 (Invalid)', 'a': []},
                    {'c': 0x91, 'l': 0, 's': 'Rumble received: 001 (CRC Fail)', 'a': []},
                    {'c': 0x92, 'l': 0, 's': 'Rumble received: 010 (Q False)', 'a': []},
                    {'c': 0x93, 'l': 0, 's': 'Rumble received: 011 (Q True)', 'a': []},
                    {'c': 0x94, 'l': 0, 's': 'Rumble received: 100 (Invalid)', 'a': []},
                    {'c': 0x95, 'l': 0, 's': 'Rumble received: 101 (Nop OK)', 'a': []},
                    {'c': 0x96, 'l': 0, 's': 'Rumble received: 110 (Cmd OK)', 'a': []},
                    {'c': 0x97, 'l': 0, 's': 'Rumble received: 111 (Invalid)', 'a': []},
                    {'c': 0x98, 'l': 0, 's': 'New TC command when last not finished', 'a': []},
                    {'c': 0x99, 'l': 0, 's': 'TC command buffer overflow', 'a': []},
                    {'c': 0x9A, 'l': 0, 's': 'Mempak read cmd wrong len', 'a': []},
                    {'c': 0x9B, 'l': 0, 's': 'Mempak write cmd wrong len', 'a': []},
                    {'c': 0x9C, 'l': 0, 's': 'Mempak cmd bad addr CRC', 'a': []},
                    {'c': 0x9D, 'l': 0, 's': 'Received rumble not 0/1', 'a': []}
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
                    print(resp['s'], *[resp['a'][j] + '=' + hex(c[i+j]) + ',' for j in range(resp['l'])])
                    i += resp['l']
                
                pass #TODO send data
            except serial.SerialException:
                print('ERROR: Serial Exception caught!')
                break
            except KeyboardInterrupt:
                print('^C Exiting')
                break

def main():
    global DEBUG

    if(os.name == 'nt'):
        psutil.Process().nice(psutil.REALTIME_PRIORITY_CLASS)
    else:
        psutil.Process().nice(20) #it's -20, you bozos
    gc.disable()

    dev = TAStm32(serial_helper.select_serial_port())
    
    try:
        dev.reset()
        dev.setup_run()
        print('Main Loop Start')
        dev.main_loop()
    finally:
        print('Exiting')
        dev.ser.close()
    sys.exit(0)

if __name__ == '__main__':
    main()
