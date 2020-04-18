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
            return True
        else:
            raise RuntimeError('Error during reset')

    def setup_run(self):
        self.write(b'SAZ\x70\x00')
        time.sleep(0.1)
        data = self.read(2)
        if data == b'\x01S':
            return True
        else:
            raise RuntimeError('Error during setup')

    def main_loop(self):
        while True:
            try:
                c = self.read(1)
                if len(c) == 0:
                    continue
                numBytes = self.ser.inWaiting()
                if numBytes > 0:
                    c += self.read(numBytes)
                
                unk_cmd_args = ['x', 'x', 'x', 'x', 'x']
                mempak_cmd_args = ['player', 'sercmd', 'addrhi', 'addrlo', 'd0']
                responses = [
                    {'c': 0xB0, 'l': 0, 's': 'Buffer Overflow', 'a': []},
                    {'c': 0xB2, 'l': 0, 's': 'Buffer Underflow', 'a': []},
                    {'c': 0xB3, 'l': 0, 's': 'Buffer Empty (normal at end of run)', 'a': []},
                    {'c': 0xC0, 'l': 5, 's': 'Ser Cmd Receive Error', 'a': unk_cmd_args},
                    {'c': 0xC1: 'l': 5, 's': 'Ser Cmd Bad Length', 'a': unk_cmd_args},
                    {'c': 0xC2: 'l': 5, 's': 'Unsupported Ser Cmd', 'a': unk_cmd_args},
                    {'c': 0xC3: 'l': 2, 's': 'Players out of order', 'a': ['player', 'expected player']},
                    {'c': 0xC4: 'l': 1, 's': 'Identity', 'a': ['player']},
                    {'c': 0xC5: 'l': 1, 's': 'Controller reset', 'a': ['player']},
                    {'c': 0xC6: 'l': 4, 's': 'Mempak read', 'a': mempak_cmd_args[:-1]},
                    {'c': 0xC7: 'l': 5, 's': 'Mempak write', 'a': mempak_cmd_args},
                    {'c': 0x90: 'l': 0, 's': 'Rumble received: 000 (Invalid)', 'a': []},
                    {'c': 0x91: 'l': 0, 's': 'Rumble received: 001 (CRC Fail)', 'a': []},
                    {'c': 0x92: 'l': 0, 's': 'Rumble received: 010 (Q False)', 'a': []},
                    {'c': 0x93: 'l': 0, 's': 'Rumble received: 011 (Q True)', 'a': []},
                    {'c': 0x94: 'l': 0, 's': 'Rumble received: 100 (Invalid)', 'a': []},
                    {'c': 0x95: 'l': 0, 's': 'Rumble received: 101 (Nop OK)', 'a': []},
                    {'c': 0x96: 'l': 0, 's': 'Rumble received: 110 (Cmd OK)', 'a': []},
                    {'c': 0x97: 'l': 0, 's': 'Rumble received: 111 (Invalid)', 'a': []},
                    {'c': 0x98: 'l': 0, 's': 'New TC command when last not finished', 'a': []},
                    {'c': 0x99, 'l': 0, 's': 'TC command buffer overflow', 'a': []},
                    {'c': 0x9A, 'l': 0, 's': 'Mempak read cmd wrong len', 'a': []},
                    {'c': 0x9B, 'l': 0, 's': 'Mempak write cmd wrong len', 'a': []},
                    {'c': 0x9C, 'l': 0, 's': 'Mempak cmd bad addr CRC', 'a': []},
                    {'c': 0x9D, 'l': 0, 's': 'Received rumble not 0/1', 'a': []}
                ]
                i = 0
                while i < numBytes:
                    pass #TODO
                
                for latch in range(latches):
                    try:
                        data = run_id + buffer[fn]
                        self.write(data)
                        if fn % 100 == 0:
                            print('Sending Latch: {}'.format(fn))
                    except IndexError:
                        pass
                    fn += 1
                    frame += 1
                for cmd in range(bulk):
                    for packet in range(packets):
                        command = []
                        for latch in range(latches_per_bulk_command//packets):
                            try:
                                command.append(run_id + buffer[fn])
                                fn += 1
                                frame += 1
                                if fn % 100 == 0:
                                    print('Sending Latch: {}'.format(fn))
                            except IndexError:
                                pass
                        data = b''.join(command)
                        self.write(data)
                    self.write(run_id.lower())
                if frame >= frame_max:
                    break
            except serial.SerialException:
                print('ERROR: Serial Exception caught!')
                break
            except KeyboardInterrupt:
                print('^C Exiting')
                break

def main():
    global DEBUG
    global buffer
    global run_id
    global fn

    if(os.name == 'nt'):
        psutil.Process().nice(psutil.REALTIME_PRIORITY_CLASS)
    else:
        psutil.Process().nice(20) #it's -20, you bozos

    gc.disable()

    parser = argparse_helper.setup_parser_full()

    args = parser.parse_args()
    
    if args.hardreset or args.softreset:
        dev.power_off()
        if args.hardreset:
            time.sleep(2.0)

    if args.transition != None:
        for transition in args.transition:
            transition[0] = int(transition[0])
            if transition[1] == 'A':
                transition[1] = b'A'
            elif transition[1] == 'N':
                transition[1] = b'N'
            elif transition[1] == 'S':
                transition[1] = b'S'
            elif transition[1] == 'H':
                transition[1] = b'H'

    if args.latchtrain != '':
        args.latchtrain = [int(x) for x in args.latchtrain.split(',')]

    DEBUG = args.debug

    args.players = args.players.split(',')
    for x in range(len(args.players)):
        args.players[x] = int(args.players[x])

    if args.serial == None:
        dev = TAStm32(serial_helper.select_serial_port())
    else:
        dev = TAStm32(args.serial)
    
    if args.clock != None:
        args.clock = int(args.clock)
        if args.clock < 0 or args.clock > 63:
            print('ERROR: The clock value must be in the range [0,63]! Exiting.')
            sys.exit(0)

    try:
        with open(args.movie, 'rb') as f:
            if args.movie.endswith('.bk2'):
                data = None
            else:
                data = f.read()
    except:
        print('ERROR: the specified file (' + args.movie + ') failed to open')
        sys.exit(0)

    dev.reset()
    run_id = dev.setup_run(args.console, args.players, args.dpcm, args.overread, args.clock)
    if run_id == None:
        raise RuntimeError('ERROR')
        sys.exit()
    if args.console == 'n64':
        if args.movie.endswith('.bk2'):
            buffer = bk2.read_input(args.movie, args.players)
            if buffer is None:
                sys.exit(1)
        else:
            buffer = m64.read_input(data, args.players)
        blankframe = b'\x00\x00\x00\x00' * len(args.players)
    elif args.console == 'snes':
        buffer = r16m.read_input(data, args.players)
        blankframe = b'\x00\x00' * len(args.players)
    elif args.console == 'nes':
        buffer = r08.read_input(data, args.players)
        blankframe = b'\x00' * len(args.players)
    elif args.console == 'gc':
        buffer = dtm.read_input(data)
        blankframe = b'\x00\x00\x00\x00\x00\x00\x00\x00' * len(args.players)

    # Send Blank Frames
    for blank in range(args.blank):
        data = run_id + blankframe
        dev.write(data)
    print(f'Sending Blank Latches: {args.blank}')
    fn = 0
    for latch in range(int_buffer-args.blank):
        try:
            data = run_id + buffer[fn]
            dev.write(data)
            if fn % 100 == 0:
                print(f'Sending Latch: {fn}')
            fn += 1
        except IndexError:
            pass
    err = dev.read(int_buffer)
    fn -= err.count(b'\xB0')
    if err.count(b'\xB0') != 0:
        print('Buffer Overflow x{}'.format(err.count(b'\xB0')))
    if args.transition != None:
        for transition in args.transition:
            dev.send_transition(run_id, *transition)
    if args.latchtrain != '':
        dev.send_latchtrain(run_id, args.latchtrain)
    print('Main Loop Start')
    dev.power_on()
    dev.main_loop()
    print('Exiting')
    dev.ser.close()
    sys.exit(0)

if __name__ == '__main__':
    main()
