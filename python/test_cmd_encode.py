from z64tc import Z64TC
import sys

with open('test_in.bin', 'rb') as f, open('test_out.bin', 'wb') as fo:
    c = Z64TC.command_to_controllers(f.read())[1:]
    print(c)
    fo.write(c)
