import os
import shutil
import json
from fontTools.ttLib import TTFont
from fontTools.subset import Subsetter, Options
import utils.fontgen
from utils.pbpack import ResourcePack

lang_dir = './lang/'
fonts_dir = './fonts/'
build_dir = './build/'
trans_dir = './translation/'
fontfile = 'GoNotoKurrent-Regular.ttf'
outfile = 'langpack.pbl'

print("Generating codepoints")

# Read all *.txt files in lang directory, ignore lines starting with '#', capture Unicode codepoints of other chars
all_codepoints = set()
for filename in os.listdir(lang_dir):
    if filename.endswith('.txt'):
        with open(os.path.join(lang_dir, filename), 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#'):
                    continue
                for ch in line:
                    all_codepoints.add(ord(ch))

# Read unicodes.json and process unicode ranges
unicodes_path = os.path.join(lang_dir, 'unicodes.json')
with open(unicodes_path, 'r', encoding='utf-8') as f:
    unicode_specs = json.load(f)

for spec in unicode_specs:
    start_cp = int(spec['start'], 16)
    end_cp = int(spec['end'], 16)

    for cp in range(start_cp, end_cp + 1):
        all_codepoints.add(cp)

# Save combined.json with sorted codepoints
combined_data = {"codepoints": sorted(all_codepoints)}
os.makedirs(build_dir, exist_ok=True)
with open(os.path.join(build_dir, 'combined.json'), 'w', encoding='utf-8') as f:
    json.dump(combined_data, f, ensure_ascii=False, indent=2)
      
# Save combined.txt with character sequence of codepoints
with open(os.path.join(build_dir, 'combined.txt'), 'w', encoding='utf-8') as f:
    count = 0
    for cp in sorted(all_codepoints):
        try:
            f.write(chr(cp))
            count += 1
            if count == 64:
                f.write('\n')
                count = 0
        except Exception:
            pass  # skip invalid codepoints

print("Built codepoints. Count: " + str(len(all_codepoints)))

# Subset fonts to only include referenced glyphs and save
font_path = os.path.join(fonts_dir, fontfile)
font = TTFont(font_path)
cmap = font.getBestCmap()
glyphs = set()
for cp in all_codepoints:
    if cp in cmap:
        glyphs.add(cmap[cp])

options = Options()
options.set(layout_features='*')
subsetter = Subsetter(options=options)
subsetter.populate(glyphs=glyphs)
subsetter.subset(font)

subset_path = os.path.join(build_dir, fontfile)
font.save(subset_path)
font.close()

print("Font file subset")

# Build the character set
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
    f = utils.fontgen.Font(subset_path, values[0], 32640, False)
    f.set_heightoffset(values[1])
    f.convert_to_pfo(os.path.join(build_dir, key))

for file_name in [str(i).zfill(3) for i in range(9, 19)]:
    with open(os.path.join(build_dir, file_name), 'w') as f:
        pass  # Empty file

shutil.copy(os.path.join(trans_dir, '000'), os.path.join(build_dir, '000'))

print("Built resources")

# Pack all files
pack = ResourcePack()
for f in [str(i).zfill(3) for i in range(0, 19)]:
    pack.add_resource(open(os.path.join(build_dir, f), 'rb').read())
with open(os.path.join(build_dir, outfile), 'wb') as pack_file:
    pack.serialize(pack_file)

print("Packing completed. Output: " + os.path.join(build_dir, outfile))
