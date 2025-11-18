# Source: https://gist.github.com/medicalwei/c9fdcd9ec19b0c363ec1

import argparse
import freetype
import os
import re
import struct
import sys
import itertools
import json
from math import ceil

sys.path.append(os.path.join(os.path.dirname(__file__), '../'))
# import generate_c_byte_array

MIN_CODEPOINT = 0x20
MAX_2_BYTES_CODEPOINT = 0xffff
MAX_EXTENDED_CODEPOINT = 0x10ffff
FONT_VERSION_1 = 1
FONT_VERSION_2 = 2
WILDCARD_CODEPOINT = 0x25AF  # White vertical rectangle
ELLIPSIS_CODEPOINT = 0x2026

HASH_TABLE_SIZE = 255
OFFSET_TABLE_MAX_SIZE = 128
MAX_GLYPHS_EXTENDED = HASH_TABLE_SIZE * OFFSET_TABLE_MAX_SIZE
MAX_GLYPHS = 256
OFFSET_SIZE_BYTES = 4


def grouper(n, iterable, fillvalue=None):
    """grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"""
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)


def hasher(codepoint, num_glyphs):
    return (codepoint % num_glyphs)


def bits(x):
    data = []
    for i in range(8):
        data.insert(0, int((x & 1) == 1))
        x = x >> 1
    return data


class Font:
    def __init__(self, ttf_path, height, max_glyphs, legacy=False):
        self.version = FONT_VERSION_2
        self.ttf_path = ttf_path
        self.max_height = int(height)
        self.legacy = legacy
        if self.ttf_path != '':
            self.face = freetype.Face(self.ttf_path)
            self.face.set_pixel_sizes(0, self.max_height)
            self.name = self.face.family_name + b'_' + self.face.style_name
        self.wildcard_codepoint = WILDCARD_CODEPOINT
        self.number_of_glyphs = 0
        self.table_size = HASH_TABLE_SIZE
        self.tracking_adjust = 0
        self.regex = None
        self.codepoints = range(MIN_CODEPOINT, MAX_EXTENDED_CODEPOINT)
        self.codepoint_bytes = 2
        self.max_glyphs = max_glyphs
        self.glyph_table = []
        self.hash_table = [0] * self.table_size
        self.offset_tables = [[] for _ in range(self.table_size)]
        self.heightoffset = 0
        self.fauxbold = False

    def set_tracking_adjust(self, adjust):
        self.tracking_adjust = adjust

    def set_heightoffset(self, offset):
        self.heightoffset = offset

    def set_fauxbold(self, fauxbold):
        self.fauxbold = fauxbold

    def set_regex_filter(self, regex_string):
        if regex_string != ".*":
            try:
                self.regex = re.compile(str(regex_string), re.UNICODE)
            except Exception:
                raise Exception("Supplied filter argument was not a valid regular expression.")
        else:
            self.regex = None

    def set_codepoint_list(self, list_path):
        with open(list_path, "r", encoding="utf-8") as codepoints_file:
            codepoints_json = json.load(codepoints_file)
            self.codepoints = [int(cp) for cp in codepoints_json["codepoints"]]

    def is_supported_glyph(self, codepoint):
        return (self.face.get_char_index(codepoint) > 0 or (codepoint == self.wildcard_codepoint))

    def glyph_bits(self, gindex):
        flags = (freetype.FT_LOAD_RENDER if self.legacy else
                 freetype.FT_LOAD_RENDER | freetype.FT_LOAD_MONOCHROME | freetype.FT_LOAD_TARGET_MONO)
        self.face.load_glyph(gindex, flags)
        bitmap = self.face.glyph.bitmap
        advance = self.face.glyph.advance.x / 64  # Convert 26.6 fixed float format to px
        advance += self.tracking_adjust
        width = bitmap.width
        if self.fauxbold:
            width += 1
        fauxbold_additional_byte = (bitmap.width % 8 == 0)
        height = bitmap.rows
        left = self.face.glyph.bitmap_left
        bottom = self.max_height - self.face.glyph.bitmap_top + self.heightoffset
        pixel_mode = self.face.glyph.bitmap.pixel_mode

        glyph_structure = ''.join((
            '<',  # little_endian
            'B',  # bitmap_width
            'B',  # bitmap_height
            'b',  # offset_left
            'b',  # offset_top
            'b'   # horizontal_advance
        ))
        glyph_header = struct.pack(glyph_structure, width, height, left, bottom, int(advance))

        glyph_bitmap = []

        if pixel_mode == 1 and self.fauxbold:  # faux bold monochrome font, 1 bit per pixel
            for i in range(bitmap.rows):
                row = []
                previousbyte = 0
                for j in range(bitmap.pitch):
                    byte = bitmap.buffer[i * bitmap.pitch + j] | previousbyte
                    fauxboldbyte = byte | byte >> 1
                    row.extend(bits(fauxboldbyte))
                    previousbyte = byte << 8  # shift 8 bits for next
                if fauxbold_additional_byte:
                    byte = previousbyte
                    fauxboldbyte = byte | byte >> 1
                    row.extend(bits(fauxboldbyte))
                glyph_bitmap.extend(row[:width])
        elif pixel_mode == 1:  # monochrome font, 1 bit per pixel
            for i in range(bitmap.rows):
                row = []
                for j in range(bitmap.pitch):
                    row.extend(bits(bitmap.buffer[i * bitmap.pitch + j]))
                glyph_bitmap.extend(row[:bitmap.width])
        elif pixel_mode == 2:  # grey font, 255 bits per pixel
            for val in bitmap.buffer:
                glyph_bitmap.extend([1 if val > 127 else 0])
        else:
            raise Exception("Unsupported pixel mode: {}".format(pixel_mode))

        glyph_packed = []
        for word in grouper(32, glyph_bitmap, 0):
            w = 0
            for index, bit in enumerate(word):
                w |= bit << index
            glyph_packed.append(struct.pack('<I', w))

        return glyph_header + b''.join(glyph_packed)

    def fontinfo_bits(self):
        return struct.pack('<BBHHBB',
                           self.version,
                           self.max_height,
                           self.number_of_glyphs,
                           self.wildcard_codepoint,
                           self.table_size,
                           self.codepoint_bytes)

    def build_tables(self):
        def build_hash_table(bucket_sizes):
            acc = 0
            for i in range(self.table_size):
                bucket_size = bucket_sizes[i]
                self.hash_table[i] = struct.pack('<BBH', i, bucket_size, acc)
                acc += bucket_size * (OFFSET_SIZE_BYTES + self.codepoint_bytes)

        def build_offset_tables(glyph_entries):
            offset_table_format = '<LL' if self.codepoint_bytes == 4 else '<HL'
            bucket_sizes = [0] * self.table_size
            for entry in glyph_entries:
                codepoint, offset = entry
                glyph_hash = hasher(codepoint, self.table_size)
                self.offset_tables[glyph_hash].append(struct.pack(offset_table_format, codepoint, offset))
                bucket_sizes[glyph_hash] += 1
                if bucket_sizes[glyph_hash] > OFFSET_TABLE_MAX_SIZE:
                    print(f"error: {bucket_sizes[glyph_hash]} > 127")
            return bucket_sizes

        def add_glyph(codepoint, next_offset, gindex, glyph_indices_lookup):
            offset = next_offset
            if gindex not in glyph_indices_lookup:
                glyph_bits = self.glyph_bits(gindex)
                glyph_indices_lookup[gindex] = offset
                self.glyph_table.append(glyph_bits)
                next_offset += len(glyph_bits)
            else:
                offset = glyph_indices_lookup[gindex]

            if codepoint > MAX_2_BYTES_CODEPOINT:
                self.codepoint_bytes = 4

            self.number_of_glyphs += 1
            return offset, next_offset, glyph_indices_lookup

        def codepoint_is_in_subset(codepoint):
            if codepoint not in (WILDCARD_CODEPOINT, ELLIPSIS_CODEPOINT):
                if self.regex is not None:
                    if self.regex.match(chr(codepoint)) is None:
                        return False
                if codepoint not in self.codepoints:
                    return False
            return True

        glyph_entries = []
        self.glyph_table.append(struct.pack('<I', 0))
        self.number_of_glyphs = 0
        glyph_indices_lookup = dict()
        codepoint, gindex = self.face.get_first_char()

        offset, next_offset, glyph_indices_lookup = add_glyph(WILDCARD_CODEPOINT, 4, 0, glyph_indices_lookup)
        glyph_entries.append((WILDCARD_CODEPOINT, offset))

        next_offset = 4 + len(self.glyph_table[-1])

        while gindex:
            if self.number_of_glyphs > self.max_glyphs:
                break

            if codepoint == WILDCARD_CODEPOINT:
                raise Exception('Wildcard codepoint is used for something else in this font')

            if gindex == 0:
                raise Exception('0 index is reused by a non wildcard glyph')

            if codepoint_is_in_subset(codepoint):
                offset, next_offset, glyph_indices_lookup = add_glyph(codepoint, next_offset, gindex, glyph_indices_lookup)
                glyph_entries.append((codepoint, offset))

            codepoint, gindex = self.face.get_next_char(codepoint, gindex)

        sorted_entries = sorted(glyph_entries, key=lambda entry: entry[0])
        hash_bucket_sizes = build_offset_tables(sorted_entries)
        build_hash_table(hash_bucket_sizes)

    def bitstring(self):
        btstr = self.fontinfo_bits()
        btstr += b''.join(self.hash_table)
        for table in self.offset_tables:
            btstr += b''.join(table)
        btstr += b''.join(self.glyph_table)
        return btstr

    # def convert_to_h(self):
    #     to_file = os.path.splitext(self.ttf_path)[0] + '.h'
    #     with open(to_file, 'wb') as f:
    #         f.write(b"#pragma once\n\n")
    #         f.write(b"#include <stdint.h>\n\n")
    #         f.write(b"// TODO: Load font from flash...\n\n")
    #         self.build_tables()
    #         bytes_ = self.bitstring()
    #         # generate_c_byte_array.write expects file object and bytes string
    #         generate_c_byte_array.write(f, bytes_, self.name)
    #     return to_file
    def convert_to_h(self):
        to_file = os.path.splitext(self.ttf_path)[0] + '.h'
        with open(to_file, 'wb') as f:
            f.write(b"#pragma once\n\n")
            f.write(b"#include <stdint.h>\n\n")
            f.write(b"// TODO: Load font from flash...\n\n")
            f.write(b"static const uint8_t %b[] = {\n\t" % self.name.encode('utf-8'))
            self.build_tables()
            bytes_ = self.bitstring()
            for index, byte in enumerate(bytes_):
                if index != 0 and index % 16 == 0:
                    f.write(b"/* bytes %d - %d */\n\t" % (index-16, index))
                f.write(b"0x%02x, " % byte)
            f.write(b"\n};\n")
        return to_file
    
    def convert_to_pfo(self, pfo_path=None):
        to_file = pfo_path if pfo_path else (os.path.splitext(self.ttf_path)[0] + '.pfo')
        with open(to_file, 'wb') as f:
            self.build_tables()
            f.write(self.bitstring())
        return to_file


def cmd_pfo(args):
    max_glyphs = MAX_GLYPHS_EXTENDED if args.extended else MAX_GLYPHS
    f = Font(args.input_ttf, args.height, max_glyphs, args.legacy)
    if args.tracking:
        f.set_tracking_adjust(args.tracking)
    if args.heightoffset:
        f.set_heightoffset(args.heightoffset)
    if args.fauxbold:
        f.set_fauxbold(args.fauxbold)
    if args.filter:
        f.set_regex_filter(args.filter)
    if args.list:
        f.set_codepoint_list(args.list)
    f.convert_to_pfo(args.output_pfo)


def cmd_header(args):
    f = Font(args.input_ttf, args.height, MAX_GLYPHS, args.legacy)
    if args.filter:
        f.set_regex_filter(args.filter)
    f.convert_to_h()


def process_all_fonts():
    font_directory = "ttf"
    font_paths = []
    for _, _, filenames in os.walk(font_directory):
        for filename in filenames:
            if os.path.splitext(filename)[1] == '.ttf':
                font_paths.append(os.path.join(font_directory, filename))

    header_paths = []
    for font_path in font_paths:
        f = Font(font_path, 14, MAX_GLYPHS)
        print(f"Rendering {f.name}...")
        f.convert_to_pfo()
        to_file = f.convert_to_h()
        header_paths.append(os.path.basename(to_file))

    with open(os.path.join(font_directory, 'fonts.h'), 'w') as f:
        f.write('#pragma once\n')
        for h in header_paths:
            f.write(f'#include "{h}"\n')


def process_cmd_line_args():
    parser = argparse.ArgumentParser(description="Generate pebble-usable fonts from ttf files")
    subparsers = parser.add_subparsers(help="commands", dest='which')

    pbi_parser = subparsers.add_parser('pfo', help="make a .pfo (pebble font) file")
    pbi_parser.add_argument('--extended', action='store_true', help="Whether or not to store > 256 glyphs")
    pbi_parser.add_argument('height', metavar='HEIGHT', type=int, help="Height at which to render the font")
    pbi_parser.add_argument('--tracking', type=int, help="Optional tracking adjustment of the font's horizontal advance")
    pbi_parser.add_argument('--filter', help="Regex to match the characters that should be included in the output")
    pbi_parser.add_argument('--list', help="json list of characters to include")
    pbi_parser.add_argument('--legacy', action='store_true', help="use legacy rasterizer (non-mono) to preserve font dimensions")
    pbi_parser.add_argument('--fauxbold', action='store_true', help="generate faux bold font")
    pbi_parser.add_argument('--heightoffset', type=int, help="height offset")
    pbi_parser.add_argument('input_ttf', metavar='INPUT_TTF', help="The ttf to process")
    pbi_parser.add_argument('output_pfo', metavar='OUTPUT_PFO', help="The pfo output file")
    pbi_parser.set_defaults(func=cmd_pfo)

    pbh_parser = subparsers.add_parser('header', help="make a .h (pebble fallback font) file")
    pbh_parser.add_argument('height', metavar='HEIGHT', type=int, help="Height at which to render the font")
    pbh_parser.add_argument('input_ttf', metavar='INPUT_TTF', help="The ttf to process")
    pbh_parser.add_argument('output_header', metavar='OUTPUT_HEADER', help="The .h output file")
    pbh_parser.add_argument('--filter', help="Regex to match the characters that should be included in the output")
    pbh_parser.set_defaults(func=cmd_header)

    args = parser.parse_args()
    args.func(args)


def main():
    if len(sys.argv) < 2:
        process_all_fonts()
    else:
        process_cmd_line_args()


if __name__ == "__main__":
    main()
