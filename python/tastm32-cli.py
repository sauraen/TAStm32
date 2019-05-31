#!/usr/bin/env python3
import gc
import os
import psutil
import serial_helper
import argparse_helper
import tastm32
import r08, r16m, m64
import rundata


if(os.name == 'nt'):
    psutil.Process().nice(psutil.REALTIME_PRIORITY_CLASS)
else:
    psutil.Process().nice(20)

gc.disable()

parser = argparse_helper.cli_parser()
args = parser.parse_args()

if args.serial == None:
    dev = tastm32.TAStm32(serial_helper.select_serial_port())
else:
    dev = tastm32.TAStm32(args.serial)

