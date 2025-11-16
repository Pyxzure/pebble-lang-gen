# Pebble Language Pack Creator

Python utility to help create a custom language pack file for the Pebble watch (.pbl)

## Usage

### 1. Build the character list

The script will perform 2 scans:

1.1 (Easy way) If the character set you want to add is small, locate the Unicode block of the character set you wish to add and edit the `lang/unicodes.json` by following the existing example. Remove any default character set you do not need. The `name` property is only for reference. The `start` and `end` properties are the start and end address in Base 16 of the Unicode character range to be imported. Leave an empty array if you do not use this file.

1.2 If the character set you want to add would be too large to import in full, identify the subset of those characters that you want to import. The script will scan the `lang/` directory for all `*.txt` file and import every characters that appear. Lines that start with `#` are ignored, and so are new-lines. The provided `lang/kanji.txt` is an example of the 3000 most used Kanji based on `scripin/aozora` dataset.

### 2. Modify the meta data and provide interface translation (optional)

The `translation/000` holds the meta data and interface translation data. If you do not need to modify these, you can skip this step and use the default file. 

2.1 `translation/000.po` file provides a template to start. The first few lines are the meta data. If you don't need to translate the interface, delete the rest of the `msgid ... msgstr ...` that follows.

2.2 For interface translation, replace all `msgstr` lines with the desired translation.

2.3 Build the `000.po` file into a `000` file (MO format) using GNU `msgfmt` utility then replace the existing `translation/000` with the built file.

### 3. Run `python build.py`

The final language pack fill be output to `build/langpack.pbl`. Example includes Japanese and Thai character added to the main English interface (`EN_JP_TH.pbl`).

### 4. Upload this file to the watch via the app

## Note

If you want to use a different font, place it in the `./font/` directory then modify the `fontfile` variable at the top of `build.py`. Note that the font must contain all glyphs of all the target languages. Noto Universal font has been chosen to cover all the normal glyphs.

## References
- Noto Universal font -- https://github.com/satbyy/go-noto-universal
- `fontgen.py` -- https://gist.github.com/medicalwei/c9fdcd9ec19b0c363ec1
- `pbpack.py` and `stm32_crc.py` -- Couldn't locate source, but likely Pebble SDK

<a href="https://ko-fi.com/pyxzure" target="_blank">
  <img src="https://storage.ko-fi.com/cdn/kofi3.png?v=3" alt="Buy Me a Coffee" width="100" height="25"/>
</a>