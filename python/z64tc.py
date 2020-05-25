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
        self.ifilemode = None
        self.replacenum = None
        self.patchaddr = None
        self.dataaddr = 0x80410000
        dmaoutldpath = self.get_rel_path('../loader/dma_patcher/dma_patcher.out.ld')
        self.dmapatcher_replacefile_fp = self.get_addr_from_outld(dmaoutldpath, 'DmaPatcher_ReplaceFile')
        self.dmapatcher_addpatch_fp = self.get_addr_from_outld(dmaoutldpath, 'DmaPatcher_AddPatch')
        self.crc = CRC()
    
    def __del__(self):
        print('Exiting')
        self.ser.close()
        self.runfile.close()
    
    def get_rel_path(self, p):
        return self.runfilepath[:self.runfilepath.rfind('/')] + '/' + p

    def get_addr_from_outld(self, outldpath, func):
        with open(outldpath) as ld:
            for ldl in ld:
                ldtoks = [t for t in ldl.strip().split(' ') if t]
                assert(len(ldtoks) == 3)
                assert(ldtoks[1] == '=')
                assert(ldtoks[2][-1] == ';')
                if ldtoks[0] == func:
                    return int(ldtoks[2][:-1], 16)
        raise RuntimeError('Could not find function ' + func + ' in ' + outldpath)
        
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
            {'c': 0xC8, 'l': 1, 's': 'Normal poll', 'a': ['player']},
            {'c': 0xC9, 'l': 1, 's': 'Poll starting new command', 'a': ['d0']},
            {'c': 0xCA, 'l': 1, 's': 'Poll finished command', 'a': ['d95']},
            {'c': 0xCB, 'l': 0, 's': 'Poll wrong player', 'a': []},
            {'c': 0xCC, 'l': 0, 's': 'Poll no commands available', 'a': []},
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
        def load_ifile(ifilepath):
            with open(ifilepath, 'rb') as i:
                self.ifile = i.read()
            self.ifilepos = 0
        def next_addr():
            self.ifileaddr = self.dataaddr
            self.dataaddr = ((self.dataaddr + len(self.ifile) + 15) >> 4) << 4
        if toks[0] == 'FIXED' or toks[0] == 'FIXED_AND_CALL_START':
            assert(len(toks) == 2)
            ifilepath = self.get_rel_path(toks[1])
            basepath = ifilepath[:-4]
            basename = basepath[basepath.rfind('/')+1:]
            load_ifile(ifilepath)
            self.ifileaddr = self.get_addr_from_outld(basepath + '.out.ld', basename + '_START')
            self.ifilemode = 'callstart' if toks[0] == 'FIXED_AND_CALL_START' else 'normal'
            print('Injecting ' + ifilepath + ' to ' + hex(self.ifileaddr))
        elif toks[0] == 'REPLACEFILE':
            assert(len(toks) == 3)
            self.replacenum = int(toks[1])
            load_ifile(self.get_rel_path(toks[2]))
            next_addr()
            self.ifilemode = 'replacefile'
            print('Replacing ROM file ' + str(self.replacenum) + ' with injection to ' 
                + hex(self.ifileaddr) + ' len ' + str(len(self.ifile)))
        elif toks[0] == 'PATCH':
            assert(len(toks) == 3)
            self.patchaddr = int(toks[1], 16)
            patchpath = self.get_rel_path(toks[2])
            assert(patchpath.endswith('.pat'))
            load_ifile(patchpath)
            next_addr()
            self.ifilemode = 'patch'
            print('Patching ROM @vrom ' + hex(self.patchaddr) + ' patch len ' + str(len(self.ifile)))
        else:
            raise ValueError('Unknown run file type: ' + toks[0])
        return True
            
    def get_next_command(self):
        sendbytes = len(self.ifile) - self.ifilepos
        if sendbytes < 0 or (sendbytes == 0 and self.ifilemode == 'normal'):
            return None
        elif sendbytes == 0:
            sendbytes = 1 # so that 1 is added to ifilepos
            if self.ifilemode == 'callstart':
                cmd_without_crc = struct.pack('>5I65xB', self.ifileaddr, 0, 0, 0, 0, 7)
            elif self.ifilemode == 'replace':
                cmd_without_crc = struct.pack('>5I65xB', self.dmapatcher_replacefile_fp, 
                    self.replacenum, self.ifileaddr, len(self.ifile), 0, 7)
            elif self.ifilemode == 'patch':
                cmd_without_crc = struct.pack('>5I65xB', self.dmapatcher_addpatch_fp, 
                    self.patchaddr, self.ifileaddr, 0, 0, 7)
            else:
                raise RuntimeError('Internal inconsistency in get_next_command!')
        elif sendbytes >= 81:
            sendbytes = 81
            cmd_without_crc = struct.pack('>I81sB', self.ifileaddr + self.ifilepos, 
                self.ifile[self.ifilepos:self.ifilepos+81], 1)
        else:
            cmd_without_crc = struct.pack('>I80sBB', self.ifileaddr + self.ifilepos,
                self.ifile[self.ifilepos:], sendbytes, 2)
        self.ifilepos += sendbytes
        # cmd_without_crc =   b'\xBB\xAA\x99\x88\x77\x66\x55\x44\x33\x22\x11\x00' + \
        #     b'\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99\xAA\xBB\xCC\xDD\xEE\xFF' + \
        #     b'\x01\x23\x45\x67\x89\xAB\xCD\xEF\xFE\xDC\xBA\x98\x76\x54\x32\x10' + \
        #     b'\xA5\xA5\xA5\xA5\x5A\x5A\x5A\x5A\x00\x00\x00\x00\xFF\xFF\xFF\xFF' + \
        #     b'\x69\x69\x69\x69\x13\x37\x13\x37\x04\x20\x04\x20\x04\x20\x04\x20' + \
        #     b'\xDE\xAD\xBE\xEF\xB0\x0B\xFA\xCE\xDE\xAD'
        return struct.pack('>I86s', self.crc.crc(cmd_without_crc), cmd_without_crc)
        
        
    def ifile_reset(self):
        print('Resetting injection of ' + self.ifileaddr)
        self.ifilepos = 0

    def command_to_controllers(cmd):
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
        # Reverse to be controllers 3, 2, 1
        for j in range(8):
            for k in range(4):
                d[12*j+k], d[12*j+k+8] = d[12*j+k+8], d[12*j+k]
        # d = b'\x00' * 96
        assert(len(d) == 96)
        return b'\x80' + bytes(d)
            

    def main_loop(self):
        try:
            while True:
                if not self.get_next_file():
                    print('End of injection')
                    return
                def reset_file():
                    nonlocal in_flight, nothing_happened, ready, cmd
                    self.ifilepos = 0
                    in_flight = 0
                    nothing_happened = 0
                    ready = False
                    cmd = self.get_next_command()
                    self.write(b'\x81')
                reset_file()
                while True:
                    if cmd is not None and ready and in_flight < int_buffer:
                        ctrl_cmd = Z64TC.command_to_controllers(cmd)
                        #print('Multipoll:', ctrl_cmd)
                        self.write(ctrl_cmd)
                        cmd = self.get_next_command()
                        in_flight += 1
                    rumble_replies = self.read_replies()
                    for rr in rumble_replies:
                        if rr == 0x95:
                            # Nop
                            if not ready:
                                print('Received nop, starting injection')
                            ready = True
                        elif rr in (0x92, 0x93, 0x94, 0x96):
                            # Q False, Q True, Bad cmd, OK
                            in_flight -= 1
                            nothing_happened = 0
                        else:
                            # CRC fail or rumble comm fail
                            if ready:
                                print('Injection error, restarting file!')
                                reset_file()
                            else:
                                print('Ignoring CRC fail because not yet ready')
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
