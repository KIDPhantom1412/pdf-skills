# OCR language

Do not hardcode a language. Before `ocr`:

1. Guess the primary script from the cover, filename, user, or `meta.language_guess` (scans are often `unknown`).
2. Read `rapidocr_lang_rec` from `check-deps` (RapidOCR's own `rapidocr --help` does **not** list language codes).
3. Map the guess onto a `LangRec` value from that list. Use the [RapidOCR model list](https://rapidai.github.io/RapidOCRDocs/main/model_list/) if the enum is ambiguous (e.g. German → `latin`).
4. **Bilingual / mixed text (RapidOCR limitations)**:
   - RapidOCR's recognition engine (`PP-OCRv6_rec`) is a single model: it accepts only **one** `Rec.lang_type` per instance. There is no built-in multi-language ensemble or automatic cross-language switching.
   - For language-learning materials and bilingual books (Chinese-Japanese, English-Chinese):
     - **CJK:** The `japan` recognition model contains Hiragana, Katakana, and standard Kanji (Kanji overlaps with Chinese Hanzi). For Japanese textbooks (`标日`), `--language japan` is the best fit for Japanese titles and still reads Chinese acceptably.
     - **Chinese / English mix:** The default `ch` model recognizes Simplified Chinese, punctuation, and Latin/English characters.
     - **TOC title formatting:** If a heading is bilingual (e.g. `第16课 雇用 ①求人案内`), prefer the section's primary book language, or the language used in the printed 目次.
5. Pass the chosen code to `ocr --language`.
