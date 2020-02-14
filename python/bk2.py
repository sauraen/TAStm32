import zipfile
import json

def isint(s):
    return s[1:].isdecimal() if s[0] == '-' else s.isdecimal()

def parse_input(il, players):
    try:
        ret = []
        while(True):
            l = il.readline()
            l = l.decode(encoding='UTF-8')
            l = l.strip()
            if not l:
                break
            if l.startswith('[') or l.startswith('LogKey'):
                continue
            if l[0] == '|' and l[3] == '|':
                if l[1:3] != '..':
                    print('Warning, .bk2 contains console power/reset commands, not supported')
                l = l[3:]
            cstrings = l.split('|')
            if len(cstrings) != len(players)+2 or cstrings[0] != '' or cstrings[-1] != '':
                print('Invalid input line in bk2: ' + l + ', parsed as ' + str(cstrings))
                return None
            del cstrings[0]
            del cstrings[-1]
            frame = bytearray()
            sidx = 0
            for c in range(4):
                if c+1 not in players:
                    continue
                segs = cstrings[sidx].split(',')
                try:
                    if len(segs) != 3:
                        raise ValueError('Must be stick X, stick Y, buttons')
                    segs[0] = segs[0].strip()
                    segs[1] = segs[1].strip()
                    if not isint(segs[0]) or not isint(segs[1]):
                        raise ValueError('Stick X/Y must be integer')
                    x = int(segs[0])
                    y = int(segs[1])
                    if x < -128 or x > 127 or y < -128 or y > 127:
                        raise ValueError('Stick X/Y must be signed byte')
                    if x < 0:
                        x += 256
                    if y < 0:
                        y += 256
                    buttons = segs[2]
                    if len(buttons) != 18:
                        raise ValueError('Must be 18 buttons (incl. dummy digital stick)')
                    if not buttons.startswith('....'):
                        raise ValueError('Digital representation of analog input not supported')
                    buttonskey = 'UDLRUDLRSZBAudrllr'
                    buttonsvalues = [0, 0, 0, 0, #dummy digital stick
                        0b0000100000000000, 0b0000010000000000, 0b0000001000000000, 0b0000000100000000, #D-pad UDLR
                        0b0001000000000000, 0b0010000000000000, 0b0100000000000000, 0b1000000000000000, #SZBA
                        0b0000000000001000, 0b0000000000000100, 0b0000000000000001, 0b0000000000000010, #C udrl (R/L!)
                        0b0000000000100000, 0b0000000000010000] #LR
                    buttonsout = 0
                    for b, bk, bv in zip(buttons, buttonskey, buttonsvalues):
                        if b == '.':
                            pass #button not pressed
                        elif b == bk:
                            buttonsout |= bv
                        else:
                            raise ValueError('Got ' + b + ' in ' + bk + ' place')
                    frame.extend(buttonsout.to_bytes(2, byteorder='big') + bytes([x, y]))
                except ValueError as e:
                    print('Invalid controller ' + str(c+1) + ' input in bk2: ' + cstrings[sidx] + ': ' + str(e))
                    return None
                sidx += 1
            ret.append(frame)
        return ret
    except Exception as e:
        print('Error parsing input: ' + str(e))
        return None

def read_input(moviefile, players):
    try:
        with zipfile.ZipFile(moviefile, 'r') as z:
            try:
                with z.open('SyncSettings.json') as ss:
                    try:
                        j = json.load(ss)
                        ctrlrs = j['o']['Controllers']
                        if len(ctrlrs) != 4:
                            raise RuntimeError
                        waserror = False
                        for i in range(4):
                            if ctrlrs[i]['IsConnected']:
                                if i+1 not in players:
                                    print('.bk2 contains controller ' + str(i+1) + ' but not requested')
                                    waserror = True
                            else:
                                if i+1 in players:
                                    print('Controller ' + str(i+1) + ' requested but not in .bk2')
                                    waserror = True
                        if waserror:
                            return None
                    except:
                        print('.bk2 SyncSettings invalid JSON format')
                        return None
            except:
                print('.bk2 does not contain SyncSettings.json')
                return None
            try:
                with z.open('Input Log.txt') as il:
                    return parse_input(il, players)
            except:
                print('.bk2 does not contain Input Log.txt')
                return None
    except Exception as e:
        print('Could not open .bk2 file as ZIP file: ' + str(e))
        return None
