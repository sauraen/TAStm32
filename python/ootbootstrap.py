import struct
import sys
import random

import createm64 as m64

def jumpcmd(addr):
    assert(addr % 4 == 0)
    j = ((addr >> 2) & 0x03FFFFFF) | 0x08000000
    return j.to_bytes(4, byteorder='big')

def bootstrapper1(data, s1startoffset, jrraaddr):
    assert(len(data) % 2 == 0)
    if(s1startoffset < 0):
        s1startoffset += 0x10000
    c3data = jumpcmd(jrraaddr)
    ret = bytearray()
    d = 0
    while d < len(data):
        #addi $gp, $r0, 0xIIII
        #00100000 00011100 IIIIIIII IIIIIIII
        ret.extend(b'\x20\x1C' + bytes([data[d], data[d+1]])) 
        ret.extend(bytes([0]*4) + c3data + bytes([0]*4))
        #sh $gp, 0xKKKK($s1)
        #10100110 00111100 KKKKKKKK KKKKKKKK
        ret.extend(b'\xA6\x3C' + s1startoffset.to_bytes(2, byteorder='big'))
        ret.extend(bytes([0]*4) + c3data + bytes([0]*4))
        d += 2
        s1startoffset += 2
    return ret

def jumpsingle(addr):
    zeros = bytes([0, 0, 0, 0])
    return zeros + zeros + jumpcmd(addr) + zeros
    
def dataforbootstrapper4(data, bs4addr):
    assert(len(data) % 8 == 0)
    c1data = jumpcmd(bs4addr)
    ret = bytearray()
    d = 0
    while d < len(data):
        c3data = bytes([data[d  ], data[d+1] & 0x3F, data[d+2], data[d+3]])
        c4data = bytes([data[d+4], data[d+5] & 0x3F, data[d+6], data[d+7]])
        c2data = bytes([0, 0, (data[d+5] & 0xC0) >> 6, data[d+1] & 0xC0])
        ret.extend(c1data + c2data + c3data + c4data)
        d += 8
    return ret

def walk_into_bs1(jrraaddr):
    #Need c1 to be a NOP opcode, and also Link walking forward.
    c1data = bytes([0, 0, 0, 0x40]) #If this ends up being walking down, change to 0xC0
    return c1data + bytes([0]*4) + jumpcmd(jrraaddr) + bytes([0]*4)

def ootbootstraprun(bs2data, bs4data, maindata):
    jrraaddr = 0x80000490
    s1 = 0x801C84A0 #global context
    bs24loc = 0x801C7E70 #must be within 0x8000 of global context
    kargaroc_loader_entry = 0x80401000
    ret = bytearray()
    ret.extend(walk_into_bs1(jrraaddr) * 20) #frames of walking
    ret.extend(bootstrapper1(bs2data, bs24loc - s1, jrraaddr))
    ret.extend(jumpsingle(bs24loc))
    ret.extend(bootstrapper1(bs4data, bs24loc - s1, jrraaddr))
    ret.extend(dataforbootstrapper4(maindata, bs24loc))
    ret.extend(jumpsingle(kargaroc_loader_entry) * 100) #frames of running K's loader
    return m64.create_header(4, len(ret) // 16) + ret
    
if __name__ == '__main__':
    try:
        bs2data = open('bootstrapper2.bin', 'rb').read()
        bs4data = open('bootstrapper4.bin', 'rb').read()
        maindata = open('kargaroc_loader.bin', 'rb').read()
        out = open(sys.argv[1], 'wb')
    except Exception as e:
        print('Could not open data files: ' + str(e))
        sys.exit(1)
    out.write(ootbootstraprun(bs2data, bs4data, maindata))
    out.close()
