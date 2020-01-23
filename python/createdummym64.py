import struct
import sys
import random

def m64_create_header(nplayers, nframes):
    return struct.pack('<4sIIIIBBHIHHI160s32sIH56s64s64s64s64s222s256s',
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
        b'Dummy N64 ROM', #'rom name'
        0, #'rom crc32'
        69, #'rom country code'
        b'\x00', #'unused 0xEA'
        b'Nintendo/SGI RDP', #'video plugin'
        b'Nintendo/SGI RSP', #'sound plugin'
        b'Nintendo PIF', #'input plugin'
        b'Nintendo/SGI RSP', #'rsp plugin'
        b'Sauraen', #'author'
        b'lol' #'description'
        )

def m64_wait(nplayers, nframes):
    return b'\x00\x00\x00\x00' * nplayers * nframes
    
def m64_mash_button(nplayers, nframes, buttonmask):
    assert(nframes % 2 == 0)
    return ((buttonmask * nplayers) + (b'\x00\x00\x00\x00' * nplayers)) * int(nframes / 2)

def m64_mariokart64_drive(nplayers, nframes):
    #Hold A, move control stick left/right, press Z occasionally
    playerstick = [random.randrange(-40, 40)] * nplayers
    playerstickdir = [bool(random.randrange(2))] * nplayers
    ret = bytearray()
    for f in range(nframes):
        for p in range(nplayers):
            b1 = 0x80 #A
            if random.randrange(60) == 0:
                b1 |= 0x20 #Z
            b2 = 0
            b3 = playerstick[p]
            b4 = 0
            ret.extend(bytes([b1, b2, b3 if b3 >= 0 else b3 + 256, b4]))
            if playerstick[p] >= random.randrange(40, 60):
                playerstickdir[p] = True
            elif playerstick[p] <= random.randrange(-70, -50):
                playerstickdir[p] = False
            if playerstickdir[p]:
                playerstick[p] -= 1
            else:
                playerstick[p] += 1
    return ret

def m64_mariokart64_run(nplayers):
    run = m64_wait(nplayers, 30)
    run += m64_mash_button(nplayers, 60, bytes([0x10, 0, 0, 0]))
    run += m64_mash_button(nplayers, 90, bytes([0x80, 0, 0, 0]))
    run += m64_mariokart64_drive(nplayers, 5000)
    totalframes = len(run) // (4*nplayers)
    return m64_create_header(nplayers, totalframes) + run
    
def main():
    if len(sys.argv) != 3:
        print('Usage: createdummym64.py path/to/output.m64 n_players')
        sys.exit(1)
    nplayers = int(sys.argv[2])
    f = open(sys.argv[1], 'wb')
    f.write(m64_mariokart64_run(nplayers))
    f.close()

if __name__ == '__main__':
    main()
