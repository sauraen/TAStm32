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

def sibling(f, s):
    return f[:(f.rfind('/')+1)] + s

def roundup16(n):
    return ((n + 15) >> 4) << 4

class InjectionMain():
    def __init__(self, runfilepath):
        self.crc = CRC()
        self.dataaddr = 0x80420000
        assert(runfilepath.endswith('.run'))
        self.runfilepath = runfilepath
        self.runfile = open(runfilepath, 'r')
        print('Opened runfile ' + runfilepath)
        dmaoutldpath = sibling(self.runfilepath, '../loader/dma_patcher/dma_patcher.out.ld')
        self.dmapatcher_replacefile_fp = self.get_addr_from_linker(dmaoutldpath, 'DmaPatcher_ReplaceFile')
        self.dmapatcher_addpatch_fp = self.get_addr_from_linker(dmaoutldpath, 'DmaPatcher_AddPatch')
        tableldpath = sibling(self.runfilepath, '../statics/tables.ld')
        self.ram_map_vrom = 0x04000000
        self.objecttable_addr = self.get_addr_from_linker(tableldpath, 'gObjectTable')
        self.actortable_addr = self.get_addr_from_linker(tableldpath, 'gActorOverlayTable')
        self.scenetable_addr = self.get_addr_from_linker(tableldpath, 'gSceneTable')
        
    def __del__(self):
        self.runfile.close()

    def map_vrom(self, ram):
        return self.ram_map_vrom + (ram & 0x7FFFFFFF)
    
    def get_addr_from_linker(self, ldpath, func):
        with open(ldpath) as ld:
            for ldl in ld:
                ldtoks = [t for t in ldl.strip().split(' ') if t]
                assert(len(ldtoks) == 3)
                assert(ldtoks[1] == '=')
                assert(ldtoks[2][-1] == ';')
                if ldtoks[0] == func:
                    return int(ldtoks[2][:-1], 16)
        raise RuntimeError('Could not find symbol ' + func + ' in ' + ldpath)
    
    def read_conf(self, origfile, dic):
        confpath = sibling(origfile, 'conf.txt')
        with open(confpath, 'r') as conf:
            for confl in conf:
                conftoks = [t for t in confl.strip().split(' ') if t]
                if len(conftoks) != 2: continue
                k = conftoks[0].lower().replace('-', '_')
                if k in dic:
                    dic[k] = int(conftoks[1], 0)
        if None in dic.values():
            print('Could not find one or more values in actor/scene config file')
            print(dic)
            raise RuntimeError('read_conf failed')
    
    def get_next_file(self):
        while True:
            l = self.runfile.readline()
            if not l:
                return None
            l = l.strip()
            if len(l) == 0:
                continue
            if l[0] == '#' or l[0:2] == '//':
                continue
            break
        toks = [t for t in l.split(' ') if t]
        if toks[0] == 'FIXED' or toks[0] == 'FIXED_AND_CALL_START':
            self.injector = FixedInjector(self, toks)
        elif toks[0] == 'REPLACEFILE':
            self.injector = ReplaceFileInjector(self, toks)
        elif toks[0] == 'PATCH':
            self.injector = PatchInjector(self, toks)
        elif toks[0] == 'WRITE':
            self.injector = WriteInjector(self, toks)
        elif toks[0] == 'OBJECT':
            self.injector = ObjectInjector(self, toks)
        elif toks[0] == 'ACTOR':
            self.injector = ActorInjector(self, toks)
        elif toks[0] == 'SCENE':
            self.injector = SceneInjector(self, toks)
        else:
            raise ValueError('Unknown run file type: ' + toks[0])
        return True
    
    def get_next_command(self):
        return self.injector.get_next_command()
    
    def reset_file(self):
        self.injector.reset()


class Injector():
    def __init__(self, parent, ifilefirst):
        self.parent = parent
        self.ifilefirst = ifilefirst
        self.ifile = None
        self.ifileaddr = None
        self.ifilepos = 0
        self.state = 0
        
    def reset(self):
        # print('--Injecting to ' + hex(self.ifileaddr))
        self.ifilepos = 0
        self.state = 0
    
    def get_next_command(self):
        cmd_without_crc = None
        if self.ifilefirst:
            cmd_without_crc = self.next_cmd_file()
        if cmd_without_crc is None:
            cmd_without_crc = self.next_cmd()
        if cmd_without_crc is None:
            return None
        # cmd_without_crc =   b'\xBB\xAA\x99\x88\x77\x66\x55\x44\x33\x22\x11\x00' + \
        #     b'\x00\x11\x22\x33\x44\x55\x66\x77\x88\x99\xAA\xBB\xCC\xDD\xEE\xFF' + \
        #     b'\x01\x23\x45\x67\x89\xAB\xCD\xEF\xFE\xDC\xBA\x98\x76\x54\x32\x10' + \
        #     b'\xA5\xA5\xA5\xA5\x5A\x5A\x5A\x5A\x00\x00\x00\x00\xFF\xFF\xFF\xFF' + \
        #     b'\x69\x69\x69\x69\x13\x37\x13\x37\x04\x20\x04\x20\x04\x20\x04\x20' + \
        #     b'\xDE\xAD\xBE\xEF\xB0\x0B\xFA\xCE\xDE\xAD'
        assert(len(cmd_without_crc) == 86)
        return struct.pack('>I86s', self.parent.crc.crc(cmd_without_crc), cmd_without_crc)
    
    def next_cmd_file(self):
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
        return cmd_without_crc
        
    def load_ifile(self, ifilepath, autoaddr):
        with open(ifilepath, 'rb') as i:
            self.ifile = i.read()
        self.ifilelenalign = roundup16(len(self.ifile))
        self.ifilepos = 0
        if autoaddr:
            self.ifileaddr = self.parent.dataaddr
            self.parent.dataaddr += self.ifilelenalign
        
class FixedInjector(Injector):
    def __init__(self, parent, toks):
        super().__init__(parent, True)
        assert(len(toks) == 2)
        ifilepath = sibling(self.parent.runfilepath, toks[1])
        basepath = ifilepath[:-4]
        basename = basepath[basepath.rfind('/')+1:]
        self.load_ifile(ifilepath, False)
        self.ifileaddr = self.parent.get_addr_from_linker(basepath + '.out.ld', basename + '_START')
        self.callstart = toks[0] == 'FIXED_AND_CALL_START'
        print('Injecting ' + ifilepath + ' to ' + hex(self.ifileaddr))
        
    def next_cmd(self):
        if self.state == 0 and self.callstart:
            self.state = 1
            return struct.pack('>5I65xB', self.ifileaddr, 0, 0, 0, 0, 7)
        return None

class ReplaceFileInjector(Injector):
    def __init__(self, parent, toks):
        super().__init__(parent, True)
        assert(len(toks) == 3)
        self.replacenum = int(toks[1], 0)
        self.load_ifile(sibling(self.parent.runfilepath, toks[2]), True)
        print('Replacing ROM file ' + str(self.replacenum) + ' with injection to ' 
            + hex(self.ifileaddr) + ' len ' + str(len(self.ifile)))
            
    def next_cmd(self):
        if self.state == 0:
            self.state = 1
            return struct.pack('>5I65xB', self.parent.dmapatcher_replacefile_fp, 
                self.replacenum, self.ifileaddr, len(self.ifile), 0, 7)
        return None

class PatchInjector(Injector):
    def __init__(self, parent, toks):
        super().__init__(parent, True)
        assert(len(toks) == 3)
        self.patchaddr = int(toks[1], 16)
        patchpath = sibling(self.parent.runfilepath, toks[2])
        assert(patchpath.endswith('.pat'))
        self.load_ifile(patchpath, True)
        print('Patching ROM @vrom ' + hex(self.patchaddr) + ' patch len ' + str(len(self.ifile)))
        
    def next_cmd(self):
        if self.state == 0:
            self.state = 1
            return struct.pack('>5I65xB', self.parent.dmapatcher_addpatch_fp, 
                self.patchaddr, self.ifileaddr, 0, 0, 7)
        return None
        
class WriteInjector(Injector):
    def __init__(self, parent, toks):
        super().__init__(parent, True)
        assert(len(toks) >= 4)
        numBytes = int(toks[1], 0)
        self.ifileaddr = int(toks[2], 16)
        assert(len(toks) == 3 + numBytes)
        self.ifile = b''
        for i in range(numBytes):
            self.ifile += bytes([int(toks[3+i], 16)])
        assert(len(self.ifile) == numBytes)
        self.ifilepos = 0
        print('Setting ' + str(numBytes) + ' bytes at ' + hex(self.ifileaddr))
        
    def next_cmd(self):
        return None

class ObjectInjector(Injector):
    def __init__(self, parent, toks):
        super().__init__(parent, True)
        assert(len(toks) == 3)
        self.objnum = int(toks[1], 0)
        self.load_ifile(sibling(self.parent.runfilepath, toks[2]), True)
        print('Adding/replacing object ' + str(self.objnum) + ' with injection to ' 
            + hex(self.ifileaddr) + ' len ' + str(len(self.ifile)))
            
    def next_cmd(self):
        if self.state == 0:
            self.state = 1
            vrom = self.parent.map_vrom(self.ifileaddr)
            return struct.pack('>3I72xBB', 
                self.parent.objecttable_addr + 0x08 + (0x08 * self.objnum),
                vrom, vrom + self.ifilelenalign, 8, 2)
        return None

class ActorInjector(Injector):
    def __init__(self, parent, toks):
        super().__init__(parent, True)
        assert(len(toks) == 3)
        self.actornum = int(toks[1], 0)
        actorpath = sibling(self.parent.runfilepath, toks[2])
        self.load_ifile(actorpath, True)
        self.conf = {'vram': None, 'allocation': None}
        self.parent.read_conf(actorpath, self.conf)
        ss = None
        for i in range(len(self.ifile) - 12):
            if self.ifile[i:i+2] == b'\xDE\xAD' and self.ifile[i+10:i+12] == b'\xBE\xEF':
                if ss is not None:
                    raise RuntimeError('More than one DEAD...BEEF in .zovl')
                ss = i
        if ss is None:
            raise RuntimeError('Could not find DEAD...BEEF in .zovl')
        self.ifile = (self.ifile[:ss] + struct.pack('>H', self.actornum)
            + self.ifile[ss+2:ss+10] + b'\x00\x00' + self.ifile[ss+12:])
        self.vars_vram = ss + self.conf['vram']
        print('Adding/replacing actor ' + str(self.actornum) + ' with injection to ' 
            + hex(self.ifileaddr) + ' len ' + str(len(self.ifile)))
        print('Base VRAM ' + hex(self.conf['vram']) + ' vars ' + hex(self.vars_vram) 
            + ' allocation ' + hex(self.conf['allocation']))
            
    def next_cmd(self):
        if self.state == 0:
            self.state = 1
            vrom = self.parent.map_vrom(self.ifileaddr)
            print('VROM ' + hex(vrom))
            return struct.pack('>8IHBB48xBB', 
                self.parent.actortable_addr + (0x20 * self.actornum),
                vrom, vrom + self.ifilelenalign, 
                self.conf['vram'], self.conf['vram'] + self.ifilelenalign,
                0, self.vars_vram, 0, self.conf['allocation'], 0, 0, 32, 2)
        return None
        
class SceneInjector(Injector):
    def __init__(self, parent, toks):
        super().__init__(parent, True)
        assert(len(toks) == 3)
        self.scenenum = int(toks[1], 0)
        scenepath = sibling(self.parent.runfilepath, toks[2])
        assert scenepath.endswith('_scene.zscene')
        scenebasename = scenepath[scenepath.rfind('/')+1:-13]
        self.load_ifile(scenepath, True)
        def round_up_data(d):
            l = len(d)
            l16 = roundup16(l)
            return d + bytes([0] * (l16 - l)) if l16 > l else d
        self.ifile = round_up_data(self.ifile)
        self.scenelen = len(self.ifile)
        self.conf = {'unk_a': None, 'unk_b': None, 'shader': None, 'save': 0, 'restrict': 0}
        self.parent.read_conf(scenepath, self.conf)
        self.roomsaddrs = b''
        nrooms = 0
        while True:
            try:
                with open(sibling(scenepath, scenebasename + '_room_' + str(nrooms) + '.zmap'), 'rb') as map:
                    d = round_up_data(map.read())
                    self.ifile += d
                    addr = self.parent.dataaddr
                    self.parent.dataaddr += len(d)
                    vrom = self.parent.map_vrom(addr)
                    self.roomsaddrs += struct.pack('>II', vrom, vrom + len(d))
                    nrooms += 1
            except FileNotFoundError:
                break
        assert(1 <= nrooms <= 127)
        # Based on oot_build.rtl by z64.me
        def find_list_addr(start, cmd, nentries):
            a = start
            while True:
                c = self.ifile[a]
                if c == cmd:
                    break
                if c == 0x14 or c >= 0x20:
                    print('Did not find command ' + hex(cmd) + ' in list')
                    return None
                a += 8
            if self.ifile[a+1] != nentries or self.ifile[a+2] != 0 or self.ifile[a+3] != 0:
                print('Invalid command')
                return None
            (addr,) = struct.unpack('>I', self.ifile[a+4:a+8])
            if addr >> 24 != 0x02 or (addr & 3) != 0 or (addr & 0xFFFFFF) > self.scenelen:
                print('Invalid address ' + hex(addr))
                return None
            return addr & 0xFFFFFF
        def scene_header_rooms(headeraddr):
            if headeraddr == 0:
                return True
            rseg = headeraddr >> 24
            ofs = headeraddr & 0xFFFFFF
            if rseg != 0x02 or (ofs & 3) != 0 or ofs + 8 > self.scenelen:
                print('Invalid scene header')
                return False #raise RuntimeError('Invalid scene header requested!')
            roomlist = find_list_addr(ofs, 0x04, nrooms)
            if roomlist is None:
                print('Could not find room list')
                return False
            print('Replacing room list at ' + hex(roomlist) + ' for header ' + hex(headeraddr))
            self.ifile = self.ifile[:roomlist] + self.roomsaddrs + self.ifile[roomlist+len(self.roomsaddrs):]
            return True
        if not scene_header_rooms(0x02000000):
            print(self.ifile[:80])
            raise RuntimeError('Invalid first scene header!')
        # Find alternate header command
        altheader = find_list_addr(0, 0x18, 0)
        if altheader is not None:
            while scene_header_rooms(altheader):
                altheader += 4
        print('Injecting scene ' + hex(self.ifileaddr) + ' ' + str(nrooms) + ' rooms')
    
    def next_cmd(self):
        if self.state == 0:
            self.state = 1
            vrom = self.parent.map_vrom(self.ifileaddr)
            return struct.pack('>5I4B60xBB', 
                self.parent.scenetable_addr + (0x14 * self.scenenum),
                vrom, vrom + self.scenelen, 0, 0, 
                self.conf['unk_a'], self.conf['shader'], self.conf['unk_b'], 0, 0x14, 2)
        return None
            

################################################################################

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
        self.inj = InjectionMain(runfilepath)
    
    def __del__(self):
        print('Exiting')
        self.ser.close()
    
    def write(self, data):
        count = self.ser.write(data)
        # if DEBUG and data != b'':
        #     print('S:', data)
        return count

    def read(self, count):
        data = self.ser.read(count)
        # if DEBUG and data != b'':
        #     print('R:', data)
        return data

    def reset(self):
        for i in range(10):
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
                return True
            print('Retrying TAStm32 reset...')
            time.sleep(0.05)
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
            {'p':  True, 'c': 0x80, 'l': 0, 's': 'Acknowledge TC buffer command', 'a': []},
            {'p': False, 'c': 0x81, 'l': 0, 's': 'Acknowledge TC buffered reset', 'a': []},
            {'p':  True, 'c': 0xB0, 'l': 0, 's': 'Buffer Overflow', 'a': []},
            {'p':  True, 'c': 0xB2, 'l': 0, 's': 'Buffer Underflow', 'a': []},
            {'p':  True, 'c': 0xB3, 'l': 0, 's': 'Buffer Empty (normal at end of run)', 'a': []},
            {'p':  True, 'c': 0xC0, 'l': 4, 's': 'Ser Cmd Receive Error', 'a': ['player', 'sercmd', 'd0', 'd1']},
            {'p':  True, 'c': 0xC1, 'l': 3, 's': 'Ser Cmd Bad Length', 'a': unk_cmd_args},
            {'p':  True, 'c': 0xC2, 'l': 3, 's': 'Unsupported Ser Cmd', 'a': unk_cmd_args},
            {'p':  True, 'c': 0xC3, 'l': 2, 's': 'Players out of order', 'a': ['player', 'expected player']},
            {'p':  True, 'c': 0xC4, 'l': 1, 's': 'Identity', 'a': ['player']},
            {'p':  True, 'c': 0xC5, 'l': 1, 's': 'Controller reset', 'a': ['player']},
            {'p':  True, 'c': 0xC6, 'l': 3, 's': 'Mempak read', 'a': mempak_cmd_args[:-1]},
            {'p':  True, 'c': 0xC7, 'l': 4, 's': 'Mempak write', 'a': mempak_cmd_args},
            {'p':  True, 'c': 0xC8, 'l': 1, 's': 'Normal poll', 'a': ['player']},
            {'p': False, 'c': 0xC9, 'l': 1, 's': 'Poll starting new command', 'a': ['d0']},
            {'p': False, 'c': 0xCA, 'l': 1, 's': 'Poll finished command', 'a': ['d95']},
            {'p':  True, 'c': 0xCB, 'l': 0, 's': 'Poll wrong player', 'a': []},
            {'p': False, 'c': 0xCC, 'l': 0, 's': 'Poll no commands available', 'a': []},
            {'p':  True, 'c': 0x90, 'l': 0, 's': 'Rumble received: 000 (Error)', 'a': []},
            {'p':  True, 'c': 0x91, 'l': 0, 's': 'Rumble received: 001 (CRC Fail)', 'a': []},
            {'p':  True, 'c': 0x92, 'l': 0, 's': 'Rumble received: 010 (Q False)', 'a': []},
            {'p':  True, 'c': 0x93, 'l': 0, 's': 'Rumble received: 011 (Q True)', 'a': []},
            {'p':  True, 'c': 0x94, 'l': 0, 's': 'Rumble received: 100 (Cmd Invalid)', 'a': []},
            {'p': False, 'c': 0x95, 'l': 0, 's': 'Rumble received: 101 (Nop OK)', 'a': []},
            {'p': False, 'c': 0x96, 'l': 0, 's': 'Rumble received: 110 (Cmd OK)', 'a': []},
            {'p':  True, 'c': 0x97, 'l': 0, 's': 'Rumble received: 111 (Error)', 'a': []},
            {'p':  True, 'c': 0x98, 'l': 0, 's': 'New TC command when last not finished', 'a': []},
            {'p':  True, 'c': 0x99, 'l': 0, 's': 'TC command buffer overflow', 'a': []},
            {'p':  True, 'c': 0x9A, 'l': 0, 's': 'Mempak read cmd wrong len', 'a': []},
            {'p':  True, 'c': 0x9B, 'l': 0, 's': 'Mempak write cmd wrong len', 'a': []},
            {'p':  True, 'c': 0x9C, 'l': 0, 's': 'Mempak cmd bad addr CRC', 'a': []},
            {'p':  True, 'c': 0x9D, 'l': 0, 's': 'Received rumble not 0/1', 'a': []},
            {'p':  True, 'c': 0xFF, 'l': 0, 's': 'Unknown serial command', 'a': []},
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
            if resp['p'] or DEBUG:
                print(resp['s'], *[resp['a'][j] + '=' + hex(c[i+j]) + ',' for j in range(resp['l'])])
            i += resp['l']
        return rumble_replies
    
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
                if not self.inj.get_next_file():
                    print('Done with whole runfile')
                    return
                def reset_file():
                    nonlocal in_flight, nothing_happened, ready, cmd
                    self.inj.reset_file()
                    in_flight = 0
                    nothing_happened = 0
                    ready = False
                    cmd = self.inj.get_next_command()
                    self.write(b'\x81')
                reset_file()
                while True:
                    if cmd is not None and ready and in_flight < int_buffer:
                        ctrl_cmd = Z64TC.command_to_controllers(cmd)
                        #print('Multipoll:', ctrl_cmd)
                        self.write(ctrl_cmd)
                        cmd = self.inj.get_next_command()
                        in_flight += 1
                    rumble_replies = self.read_replies()
                    for rr in rumble_replies:
                        if rr == 0x95:
                            # Nop
                            if not ready:
                                # print('----Received nop, starting injection')
                                pass
                            ready = True
                        elif rr in (0x92, 0x93, 0x94, 0x96):
                            # Q False, Q True, Bad cmd, OK
                            in_flight -= 1
                            nothing_happened = 0
                            filled = int(in_flight * 100.0 / int_buffer)
                            print('\rBuf ' + str(filled) + '%: ' + ('=' * (filled//2)) + '>  ', end='')
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
                        print('\r', end='')
                        break
        except serial.SerialException:
            print('ERROR: Serial Exception caught!')
        except KeyboardInterrupt:
            print('^C Exiting')

def main():
    #global DEBUG

    # if(os.name == 'nt'):
    #     psutil.Process().nice(psutil.REALTIME_PRIORITY_CLASS)
    # else:
    #     psutil.Process().nice(20) #it's -20, you bozos, and you can't do this without sudo
    gc.disable()
    
    assert(sys.argv[1].endswith('.run'))
    dev = Z64TC(serial_helper.select_serial_port(), sys.argv[1])
    
    dev.reset()
    dev.setup_run()
    print('Main Loop Start')
    dev.main_loop()
    dev.reset()
    sys.exit(0)

if __name__ == '__main__':
    main()
