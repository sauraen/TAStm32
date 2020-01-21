import struct
import sys

def create_header(nplayers, nframes):
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
