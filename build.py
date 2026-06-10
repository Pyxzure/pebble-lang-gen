import os
import shutil
import json
import struct
from pathlib import Path
from typing import Dict, List
from utils.fontgen import Font, FontType
import utils.fontgen as fg
from utils.pbpack import ResourcePack

LANG_DIR = Path('./lang/')
TTFS_DIR = Path('./ttf/')
PBFFS_DIR = Path('./pbff/')
BUILD_DIR = Path('./build/')
TRANS_DIR = Path('./translation/')
OUTPUT_FILE = 'langpack.pbl'
USE_EXTENDED = True
USE_LEGACY = False

os.makedirs(BUILD_DIR, exist_ok=True)

def build_font_objects(json_paths, font_height, font_offset, pbff_type) -> List[Font]:
    font_objects = []
    
    for json_path in json_paths:
        font_or_pbff_name: str = json_path.name.replace(".json", "")
        ttf_path = ""
        pbff_path = ""
        if '.ttf' in font_or_pbff_name:
            font_type = FontType.TTF
            ttf_path = str(TTFS_DIR / font_or_pbff_name)
        elif '.pbff' in font_or_pbff_name:
            font_type = FontType.PBFF
            pbff_path = str(PBFFS_DIR.joinpath(font_or_pbff_name.replace(".pbff", "")).joinpath(f"{pbff_type}.pbff"))

        max_glyphs = 32640 if USE_EXTENDED else 256
        font_obj = Font(font_type, ttf_path, pbff_path, font_height, max_glyphs, USE_LEGACY)
        font_obj.set_codepoint_list(json_path)
        if font_offset is not None:
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
                if f.type == FontType.TTF:
                    glyph_bits = f.glyph_bits_ttf(gindex)
                else:  # assuming PBFF
                    glyph_bits = f.glyph_bits_pbff(codepoint)
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
        merged = Font(FontType.MERGED, "", "", fonts[0].max_height, fonts[0].max_glyphs, fonts[0].legacy)
        merged.name = b"merged_font"
        merged.heightoffset = fonts[0].heightoffset
        
        glyph_entries = []
        merged.glyph_table.append(struct.pack('<I', 0))
        merged.number_of_glyphs = 0
        glyph_indices_lookup: Dict[int, int] = {}
        offset, next_offset, glyph_indices_lookup = add_glyph(merged, fonts[0], fg.WILDCARD_CODEPOINT, 4, 0, glyph_indices_lookup)
        glyph_entries.append((fg.WILDCARD_CODEPOINT, offset))
        next_offset = 4 + len(merged.glyph_table[-1])

        for thisfont in fonts:
            codepoint, gindex = thisfont.get_first_char()

            while gindex:
                if merged.number_of_glyphs > merged.max_glyphs:
                    break

                if codepoint == fg.WILDCARD_CODEPOINT:
                    if thisfont.type == FontType.TTF:
                        raise Exception(f'Wildcard codepoint is used for something else in this font {thisfont.ttf_path or thisfont.pbff_path}')
                    # continue

                if gindex == 0:
                    raise Exception('0 index is reused by a non wildcard glyph')

                if codepoint_is_in_subset(thisfont, codepoint):
                    offset, next_offset, glyph_indices_lookup = add_glyph(merged, thisfont, codepoint, next_offset, gindex, glyph_indices_lookup)
                    glyph_entries.append((codepoint, offset))

                codepoint, gindex = thisfont.get_next_char(codepoint, gindex)

        sorted_entries = sorted(glyph_entries, key=lambda entry: entry[0])
        hash_bucket_sizes = build_offset_tables(merged, sorted_entries)
        build_hash_table(merged, hash_bucket_sizes)
        return merged

glyph_map_ttf = {}
glyph_map_pbff = {}

# Build codepoint -> font map

print("Building codepoint list")

# Read all *.txt files in './lang/'
for filename in os.listdir(LANG_DIR):
    if filename.endswith('.txt'):
        with open(LANG_DIR/filename, 'r', encoding='utf-8') as f:
            ttf_name = None
            pbff_name = None
            for line in f:
                line = line.strip()
                if line.startswith('#') or line == '':
                    if line.startswith('#ttf:'):
                        ttf_name = line.split(':', 1)[1].strip()
                    if line.startswith('#pbff:'):
                        pbff_name = line.split(':', 1)[1].strip()
                    continue
                if ttf_name is None and pbff_name is None:
                    raise Exception('Font file not specified in ' + filename)
                for ch in line:
                    if ttf_name:
                        glyph_map_ttf[ord(ch)] = ttf_name
                    if pbff_name:
                        glyph_map_pbff[ord(ch)] = pbff_name

# Read './lang/unicodes.json'
unicodes_path = LANG_DIR/'unicodes.json'
with open(unicodes_path, 'r', encoding='utf-8') as f:
    unicode_specs = json.load(f)

for spec in unicode_specs:
    start_cp = int(spec['start'], 16)
    end_cp = int(spec['end'], 16)
    ttf_name = spec.get('ttf')
    pbff_name = spec.get('pbff')
    if ttf_name is None and pbff_name is None:
        raise KeyError(f'unicode spec with name {spec.get('name')} must have "font" or "pbff" specified')
    if ttf_name != None and pbff_name != None:
        raise KeyError(f'unicode spec with name {spec.get('name')} must have either "font" or "pbff", not both')

    for cp in range(start_cp, end_cp + 1):
        if ttf_name:
            glyph_map_ttf[cp] = ttf_name
        if pbff_name:
            glyph_map_pbff[cp] = pbff_name

glyph_inv_ttf = {}
glyph_inv_pbff = {}

# Build the inverse mappings
for glyph_map, glyph_inv in [(glyph_map_ttf, glyph_inv_ttf), (glyph_map_pbff, glyph_inv_pbff)]:
    for key, value in glyph_map.items():
        if value not in glyph_inv:
            glyph_inv[value] = []
        glyph_inv[value].append(key)

json_paths = []

# Build font -> codepoint map
for glyph_inv, font_type in [(glyph_inv_ttf, FontType.TTF), (glyph_inv_pbff, FontType.PBFF)]:
    for ttf_name, codepoints in glyph_inv.items():
        # Sort codepoints for consistent output
        sorted_codepoints = sorted(list(codepoints))

        # Convert codepoints to characters
        characters = []
        for codepoint in sorted_codepoints:
            char = chr(codepoint)
            characters.append(char)

        output_data = {
            "font": ttf_name,
            "count": len(sorted_codepoints),
            "chars": ''.join(characters),
            "codepoints": sorted_codepoints
        }

        if font_type == FontType.TTF:
            output_path = BUILD_DIR / f"{ttf_name}.json"
        else:  # PBFF
            output_path = BUILD_DIR / f"{ttf_name}.pbff.json"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        json_paths.append(output_path)
        print(f"Saved: {output_path}")

if len(json_paths) < 1:
    raise Exception("No JSON files found. Exiting.")

# Build the character set

print("Building resource")

builds = {
    # pebble font resource key: (ttf font height, ttf height offset, pbff file name)
    '001': (12, 2, '14'),
    '002': (12, 2, '14_bold'),
    '003': (14, 4, '18'),
    '004': (14, 4, '18_bold'),
    '005': (17, 7, '24'),
    '006': (17, 7, '24_bold'),
    '007': (20, 8, '28'),
    '008': (20, 8, '28_bold'),
}

for key, values in builds.items():
    fonts = build_font_objects(
        json_paths,
        font_height=values[0],
        font_offset=values[1],
        pbff_type=values[2],
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
