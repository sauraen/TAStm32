import struct
import sys
import random

import createm64 as m64

def jumpcmd(addr):
    assert(addr % 4 == 0)
    j = ((addr >> 2) & 0x03FFFFFF) | 0x08000000
    return j.to_bytes(4, byteorder='big')



def bootstrapper1and3(bsidx, smart, data, regstartoffset, jrraaddr):
    assert(len(data) % 2 == 0)
    assert(bsidx == 1 or bsidx == 3)
    
    def li_cmd(twobytedata):
        print('    addi $gp, $zero, 0x' + twobytedata.hex())
        #00100000 00011100 IIIIIIII IIIIIIII
        return b'\x20\x1C' + twobytedata
    
    def sh_cmd(offset):
        ob = offset.to_bytes(2, byteorder='big')
        print('    sh $gp, 0x' + ob.hex() + '(s' + ('0' if bsidx == 3 else '1') + ')')
        #10100110 00111100 KKKKKKKK KKKKKKKK for bs1
        #10100110 00011100 KKKKKKKK KKKKKKKK for bs3
        byte2 = b'\x1C' if bsidx == 3 else b'\x3C'
        return b'\xA6' + byte2 + ob
    
    def write_frame(c1data):
        frame = c1data + bytes([0]*4) + jumpcmd(jrraaddr) + bytes([0]*4)
        ret.extend(frame if bsidx == 3 else frame * 3)
    
    if(regstartoffset < 0):
        regstartoffset += 0x10000
    ret = bytearray()
    
    if smart:
        smartdata = []
        d = 0
        while d < len(data):
            twobytedata = bytes([data[d], data[d+1]])
            for entry in smartdata:
                if entry['d'] == twobytedata:
                    entry['a'].append(regstartoffset)
                    twobytedata = None
            if twobytedata:
                smartdata.append({'a': [regstartoffset], 'd': twobytedata})
            d += 2
            regstartoffset += 2
        for entry in smartdata:
            write_frame(li_cmd(entry['d']))
            for a in entry['a']:
                write_frame(sh_cmd(a))
    else:
        d = 0
        while d < len(data):
            write_frame(li_cmd(bytes([data[d], data[d+1]])))
            write_frame(sh_cmd(regstartoffset))
            d += 2
            regstartoffset += 2
    print('Bootstrapper' + str(bsidx) + (' smart' if smart else ' naive') 
        + ' is ' + str(float(len(ret)//16)/60) + ' sec.')
    return ret

def jumpsingle(addr):
    return bytes([0]*8) + jumpcmd(addr) + bytes([0]*4)
    
def dataforbootstrapper4(data, bs4addr):
    assert(len(data) % 8 == 0)
    c1data = jumpcmd(bs4addr)
    ret = bytearray()
    d = 0
    while d < len(data):
        c3data = bytes([data[d  ], data[d+1] & 0x3F, data[d+2], data[d+3]])
        c4data = bytes([data[d+4], data[d+5] & 0x3F, data[d+6], data[d+7]])
        c2b4 = ((data[d+5] & 0xC0) >> 4) | ((data[d+1] & 0xC0) >> 6)
        c2data = bytes([0, 0, 0, c2b4])
        ret.extend(c1data + c2data + c3data + c4data)
        d += 8
    print('Kargaroc payload injection is ' + str(float(len(ret)//16)/60) + ' sec.')
    return ret

def walk_into_bs1(jrraaddr):
    #Need c1 to be a NOP opcode, and also Link walking forward.
    c1data = bytes([0, 0, 0, 0x40]) #If this ends up being walking down, change to 0xC0
    return c1data + bytes([0]*4) + jumpcmd(jrraaddr) + bytes([0]*4)

def ootbootstraprun(bs2data, bs4data, maindata):
    jrraaddr = 0x80000490
    bs1s1 = 0x801C84A0 #global context
    bs2loc = 0x801C7E70 #must be within 0x8000 of global context
    bs3s0 = 0x8011D500 #padmgr
    bs4loc = 0x8011E000 #must be within 0x8000 of padmgr
    kargaroc_loader_entry = 0x80401000
    ret = bytearray()
    ret.extend(walk_into_bs1(jrraaddr) * 240) #frames of walking
    bootstrapper1and3(1, False, bs2data, bs2loc - bs1s1, jrraaddr)
    ret.extend(bootstrapper1and3(1, True, bs2data, bs2loc - bs1s1, jrraaddr))
    ret.extend(jumpsingle(bs2loc) * 3)
    bootstrapper1and3(3, False, bs4data, bs4loc - bs3s0, jrraaddr)
    ret.extend(bootstrapper1and3(3, True, bs4data, bs4loc - bs3s0, jrraaddr))
    ret.extend(dataforbootstrapper4(maindata, bs4loc))
    ret.extend(jumpsingle(kargaroc_loader_entry) * 100) #frames of running K's loader
    return m64.create_header(4, len(ret) // 16) + ret
    
if __name__ == '__main__':
    try:
        bs2data = open('newbs2.bin', 'rb').read()
        bs4data = open('bootstrapper4.bin', 'rb').read()
        maindata = open('kargaroc_test_payload.bin', 'rb').read()
        out = open(sys.argv[1], 'wb')
    except Exception as e:
        print('Could not open data files: ' + str(e))
        sys.exit(1)
    out.write(ootbootstraprun(bs2data, bs4data, maindata))
    out.close()
