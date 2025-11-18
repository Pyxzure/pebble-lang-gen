import os
import shutil
import json
import struct
from pathlib import Path
from typing import List
from utils.fontgen import Font
import utils.fontgen as fg
from utils.pbpack import ResourcePack

LANG_DIR = Path('./lang/')
FONTS_DIR = Path('./fonts/')
BUILD_DIR = Path('./build/')
TRANS_DIR = Path('./translation/')
OUTPUT_FILE = 'langpack.pbl'
USE_EXTENDED = True
USE_LEGACY = False

os.makedirs(BUILD_DIR, exist_ok=True)

def build_font_objects(json_files, font_height, font_offset = None) -> List[Font]:
    font_objects = []
    
    for json_path in json_files:
        font_name = json_path.name.replace(".json", "")
        ttf_path = str(FONTS_DIR / font_name)
        max_glyphs = 32640 if USE_EXTENDED else 256
        font_obj = Font(ttf_path, font_height, max_glyphs, USE_LEGACY)
        font_obj.set_codepoint_list(json_path)
        if(font_offset is not None):
            font_obj.set_heightoffset(font_offset)
        
        font_objects.append(font_obj)
    
    return font_objects

# Function to merge multiple Fonts
def merge_fonts(fonts: List[Font]) -> Font:
        def build_hash_table(m:Font, bucket_sizes):
            acc = 0
            for i in range(m.table_size):
                bucket_size = bucket_sizes[i]
                m.hash_table[i] = struct.pack('<BBH', i, bucket_size, acc)
                acc += bucket_size * (fg.OFFSET_SIZE_BYTES + m.codepoint_bytes)

        def build_offset_tables(m:Font, glyph_entries):
            offset_table_format = '<LL' if m.codepoint_bytes == 4 else '<HL'
            bucket_sizes = [0] * m.table_size
            for entry in glyph_entries:
                codepoint, offset = entry
                glyph_hash = fg.hasher(codepoint, m.table_size)
                m.offset_tables[glyph_hash].append(struct.pack(offset_table_format, codepoint, offset))
                bucket_sizes[glyph_hash] += 1
                if bucket_sizes[glyph_hash] > fg.OFFSET_TABLE_MAX_SIZE:
                    print(f"error: {bucket_sizes[glyph_hash]} > 127")
            return bucket_sizes

        def add_glyph(m:Font, f:Font, codepoint, next_offset, gindex, glyph_indices_lookup):
            offset = next_offset
            if (id(f), gindex) not in glyph_indices_lookup:
                glyph_bits = f.glyph_bits(gindex)
                glyph_indices_lookup[(id(f), gindex)] = offset
                m.glyph_table.append(glyph_bits)
                next_offset += len(glyph_bits)
            else:
                offset = glyph_indices_lookup[(id(f), gindex)]

            if codepoint > fg.MAX_2_BYTES_CODEPOINT:
                m.codepoint_bytes = 4

            m.number_of_glyphs += 1
            return offset, next_offset, glyph_indices_lookup

        def codepoint_is_in_subset(f:Font, codepoint):
            if codepoint not in (fg.WILDCARD_CODEPOINT, fg.ELLIPSIS_CODEPOINT):
                if f.regex is not None:
                    if f.regex.match(chr(codepoint)) is None:
                        return False
                if codepoint not in f.codepoints:
                    return False
            return True
        
        if not fonts:
            raise ValueError("No fonts to merge")
        
        # Validate all fonts share same settings
        ref_height = fonts[0].max_height
        ref_legacy = fonts[0].legacy
        for f in fonts:
            if f.max_height != ref_height:
                raise ValueError(f"Font height mismatch: {f.max_height} != {ref_height}")
            if f.legacy != ref_legacy:
                raise ValueError(f"Font legacy mode mismatch")
        
        # Create merged font with placeholder ttf_path
        merged = Font("", fonts[0].max_height, fonts[0].max_glyphs, fonts[0].legacy)
        merged.name = b"merged_font"
        merged.heightoffset = fonts[0].heightoffset
        
        glyph_entries = []
        merged.glyph_table.append(struct.pack('<I', 0))
        merged.number_of_glyphs = 0
        glyph_indices_lookup = dict()
        offset, next_offset, glyph_indices_lookup = add_glyph(merged, fonts[0], fg.WILDCARD_CODEPOINT, 4, 0, glyph_indices_lookup)
        glyph_entries.append((fg.WILDCARD_CODEPOINT, offset))
        next_offset = 4 + len(merged.glyph_table[-1])

        for thisfont in fonts:
            codepoint, gindex = thisfont.face.get_first_char()

            while gindex:
                if merged.number_of_glyphs > merged.max_glyphs:
                    break

                if codepoint == fg.WILDCARD_CODEPOINT:
                    raise Exception('Wildcard codepoint is used for something else in this font')
                    # continue

                if gindex == 0:
                    raise Exception('0 index is reused by a non wildcard glyph')

                if codepoint_is_in_subset(thisfont, codepoint):
                    offset, next_offset, glyph_indices_lookup = add_glyph(merged, thisfont, codepoint, next_offset, gindex, glyph_indices_lookup)
                    glyph_entries.append((codepoint, offset))

                codepoint, gindex = thisfont.face.get_next_char(codepoint, gindex)

        sorted_entries = sorted(glyph_entries, key=lambda entry: entry[0])
        hash_bucket_sizes = build_offset_tables(merged, sorted_entries)
        build_hash_table(merged, hash_bucket_sizes)
        return merged

glyph_map = {}
json_path = []

# Build codepoint -> font map

print("Building codepoint list")

# Read all *.txt files in './lang/'
for filename in os.listdir(LANG_DIR):
    if filename.endswith('.txt'):
        with open(LANG_DIR/filename, 'r', encoding='utf-8') as f:
            font_name = None
            for line in f:
                line = line.strip()
                if line.startswith('#') or line == '':
                    if line.startswith('#font:'):
                        font_name = line.split(':', 1)[1].strip()
                    continue
                if font_name is None:
                    raise Exception('Font file not specified in ' + filename)
                for ch in line:
                    glyph_map[ord(ch)] = font_name

# Read './lang/unicodes.json'
unicodes_path = LANG_DIR/'unicodes.json'
with open(unicodes_path, 'r', encoding='utf-8') as f:
    unicode_specs = json.load(f)

for spec in unicode_specs:
    start_cp = int(spec['start'], 16)
    end_cp = int(spec['end'], 16)
    font_name = spec['font']

    for cp in range(start_cp, end_cp + 1):
        glyph_map[cp] = font_name

# Build the inverse mapping
glyph_inv = {}
for key, value in glyph_map.items():
    if value not in glyph_inv:
        glyph_inv[value] = []
    glyph_inv[value].append(key)

# Build font -> codepoint map
for font_name, codepoints in glyph_inv.items():
    # Sort codepoints for consistent output
    sorted_codepoints = sorted(list(codepoints))

    # Convert codepoints to characters
    characters = []
    for codepoint in sorted_codepoints:
        char = chr(codepoint)
        characters.append(char)
    
    output_data = {
        "font": font_name,
        "count": len(sorted_codepoints),
        "chars": ''.join(characters),
        "codepoints": sorted_codepoints
    }
    
    output_path = BUILD_DIR / f"{font_name}.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    json_path.append(output_path)
    print(f"Saved: {output_path}")

if len(json_path) < 1:
    raise Exception("No JSON files found. Exiting.")

# Build the character set

print("Building resource")

# [height, offset]
builds = {}
builds['001'] = [12, 2]
builds['002'] = [12, 2]
builds['003'] = [14, 4]
builds['004'] = [14, 4]
builds['005'] = [17, 7]
builds['006'] = [17, 7]
builds['007'] = [20, 8]
builds['008'] = [20, 8]

for key, values in builds.items():
    fonts = build_font_objects(
        json_path,
        font_height=values[0],
        font_offset=values[1]
    )
    if not fonts:
        raise Exception("Failed to create any Font objects. Exiting.")
        
    merged_font = merge_fonts(fonts)
    if merged_font is None:
        raise Exception("Failed to merge fonts. Exiting.")
    
    with open(BUILD_DIR / key, 'wb') as f:
        f.write(merged_font.bitstring())

for file_name in [str(i).zfill(3) for i in range(9, 19)]:
    with open(BUILD_DIR / file_name, 'w') as f:
        pass  # Empty file

shutil.copy(TRANS_DIR / '000', BUILD_DIR / '000')

print("Packing resources")

# Pack all files
pack = ResourcePack()
for f in [str(i).zfill(3) for i in range(0, 19)]:
    pack.add_resource(open(BUILD_DIR / f, 'rb').read())
with open(BUILD_DIR / OUTPUT_FILE, 'wb') as pack_file:
    pack.serialize(pack_file)

print("Completed. Output: " + str(BUILD_DIR / OUTPUT_FILE))