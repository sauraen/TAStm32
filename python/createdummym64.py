import struct
import sys
import random

def m64_create_header(nplayers, nframes):
    return struct.pack('<4sI' + '<IIIBBHIHHI160s32sIH56s64s64s64s64s222s256s',
        b'M64\x1a', 3,
        0, #'movie uid'
        nframes, #'frame count'
        1337, #'rerecord count'
        60, #'fps'
        nplayers, #'controllers'
        0, #'unused 0x16'
        nframes, #'input samples'
        2, #'start type'
        0, #'unused 0x1E'
        1, #'controller flags'
        b'\x00', #'unused 0x24'
        'Dummy N64 ROM', #'rom name'
        0, #'rom crc32'
        69, #'rom country code'
        0, #'unused 0xEA'
        'Nintendo/SGI RDP', #'video plugin'
        'Nintendo/SGI RSP', #'sound plugin'
        'Nintendo PIF', #'input plugin'
        'Nintendo/SGI RSP', #'rsp plugin'
        'Sauraen', #'author'
        'lol' #'description'
        )

def m64_wait(nplayers, nframes):
    return b'\x00\x00\x00\x00' * nplayers * nframes
    
def m64_mash_button(nplayers, nframes, buttonmask):
    assert(nframes % 2 == 0)
    return ((buttonmask * nplayers) + (b'\x00\x00\x00\x00' * nplayers)) * (nframes / 2)

def m64_mariokart64_drive(nplayers, nframes):
    #Hold A, move control stick left/right, press Z occasionally
    playerstick = [random.randrange(-40, 40)] * nplayers
    playerstickdir = [bool(random.randrange(2))] * nplayers
    ret = b''
    for f in range(nframes):
        for p in range(nplayers):
            b1 = 0x80 #A
            if random.randrange(30) == 0:
                b1 |= 0x20 #Z
            b2 = 0
            b3 = playerstick[p]
            b4 = 0
            ret.append(bytes([b1, b2, b3, b4]))
            if playerstick[p] >= random.randrange(50, 70):
                playerstickdir[p] = True
            elif playerstick[p] <= random.randrange(-50, -70):
                playerstickdir[p] = False
            if playerstickdir[p]:
                playerstick[p] -= 1
            else:
                playerstick[p] += 1
    return ret
