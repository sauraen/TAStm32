import struct
import sys
import random

import createm64 as m64

def jumpcmd(addr):
    return ((addr >> 2) | 0x08000000).to_bytes(4, byteorder='big')

def bootstrapper1(data, s1startoffset, jrraaddr):
    assert(len(data) % 2 == 0)
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
