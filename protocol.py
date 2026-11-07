"""Wire v1: big-endian 8-byte header + 12-byte fixed records."""
import struct

VERSION = 1
HEADER = struct.Struct('!BBHI')  # version, flags, count, sequence
RECORD = struct.Struct('!BBHHHhh')  # kind, buttons, x, y, pressure, tilt X/Y *100
KINDS = ('enter', 'leave', 'down', 'move', 'up', 'cancel',
         'touch_down', 'touch_move', 'touch_up', 'touch_cancel')
TOUCH_FIRST = 6  # touch records carry the contact slot (0-9) in the buttons byte
MAX_EVENTS = 256


def decode_packet(packet):
    if len(packet) < HEADER.size:
        raise ValueError('数据包头不完整')
    version, flags, count, sequence = HEADER.unpack_from(packet)
    if version != VERSION or flags != 0 or count > MAX_EVENTS:
        raise ValueError('不支持的数据包版本、标志或长度')
    if len(packet) != HEADER.size + count * RECORD.size:
        raise ValueError('数据包长度不匹配')
    events = []
    for kind, buttons, x, y, pressure, tx, ty in RECORD.iter_unpack(packet[HEADER.size:]):
        if kind >= len(KINDS) or buttons > (9 if kind >= TOUCH_FIRST else 63) or abs(tx) > 9000 or abs(ty) > 9000:
            raise ValueError('无效的输入事件字段')
        events.append(dict(type=KINDS[kind], buttons=buttons, x=x/65535, y=y/65535,
                           pressure=pressure/65535, tiltX=tx/100, tiltY=ty/100))
    return sequence, events


def acknowledgement(sequence):
    return HEADER.pack(VERSION, 1, 0, sequence)
