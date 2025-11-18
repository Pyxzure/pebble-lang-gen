# Pebble Language Pack Creator

Python utility to help create a custom language pack file for the Pebble watch (.pbl). Generates the required source files from a custom input list of display characters, which can include multiple languages and font files, and packages them into an import-ready language pack.

## Usage

### 1. Build the character list

The script will perform 2 scans. Edit the files in the `lang/` directory to configure the character set to import. Place the font file to build from into the `font/` directory.

1.1 (Easy way) If the character set you want to add is small, locate the Unicode block of the character set you wish to add and edit the `lang/unicodes.json` by following the existing template. Remove any default character set you do not need. The `name` property is only for reference. The `start` and `end` properties are the start and end address in Base 16 of the Unicode character range to be imported. Specify the font file to import from with the `font` property. Leave an empty array if you do not use this file.

1.2 If the character set you want to add would be too large to import in full, identify the subset of those characters that you want to import and input them into text files. The script will scan the `lang/` directory for all `*.txt` files and import every characters that appear. Lines that start with `#` are ignored. The characters can be a long continuous string or separated by new-lines. Specify the font file to import from with a `#font:` comment, which must precede the first non-comment line. The provided `lang/kanji.txt` is an example of the 3000 most used Kanji based on `scriptin/aozora` dataset.

### 2. Modify the meta data and provide interface translation (optional)

The `translation/000` holds the meta data and interface translation data. If you do not need to modify these, you can skip this step and use the default file. 

2.1 `translation/000.po` file provides a template to start. The first few lines are the meta data. If you don't need to translate the interface, delete the rest of the `msgid ... msgstr ...` that follows.

2.2 For interface translation, replace all `msgstr` lines with the desired translation.

2.3 Build the `000.po` file into a `000` file (MO format) using GNU `msgfmt` utility then replace the existing `translation/000` with the built file.

### 3. Run `python build.py`

The final language pack will be output to `build/langpack.pbl`. Example includes Japanese and Thai display character support added to the main English interface (`EN_JP_TH.pbl`).

### 4. Upload this file to the watch via the app

## References
- Noto Universal font -- https://github.com/satbyy/go-noto-universal
- `fontgen.py` -- https://gist.github.com/medicalwei/c9fdcd9ec19b0c363ec1
- `pbpack.py` and `stm32_crc.py` -- Couldn't locate source, but likely Pebble SDK
- Kanji frequency list -- https://scriptin.github.io/kanji-frequency

<a href="https://ko-fi.com/pyxzure" target="_blank">
  <img src="https://storage.ko-fi.com/cdn/kofi3.png?v=3" alt="Buy Me a Coffee" width="100" height="25"/>
</a>
