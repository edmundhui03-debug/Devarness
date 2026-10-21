"""Amend an i18n page's English without losing its Cantonese dictionary.

`i18n inject --zh` replaces the page's whole dictionary and moves the style block
above the doctype, so a hand edit followed by inject loses every old translation.

usage:
  amend.py edit PAGE pairs.json      apply [old, new] English replacements, each exactly once
  amend.py missing PAGE              after `i18n extract`: keys with no translation, with their English
  amend.py merge PAGE zh.json OUT    the page's dictionary (keys still used) plus zh.json -> OUT
  amend.py head PAGE                 put the doctype and charset back on lines 1-2 after inject

The loop: edit (a replaced element drops its data-i18n so extract gives it a fresh
key), `i18n extract`, missing, translate into zh.json, merge, `i18n inject --zh OUT`,
head, `i18n check`.
"""
import json
import re
import sys

DICTIONARY = re.compile(r'<script id="i18n-zh" type="application/json">(.*?)</script>', re.S)
TAGGED = re.compile(r'data-i18n="([^"]+)"[^>]*>(.*?)</(?:td|li|p|b|span|h\d)>')
HEAD = ("<!doctype html>\n", '<meta charset="utf-8">\n')
HEAD_TAG = re.compile(r'(?i)\n?(<!doctype html>|<meta charset="utf-8"\s*/?>)\n?')


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def dictionary(text):
    found = DICTIONARY.search(text)
    if not found:
        raise SystemExit("amend: the page has no i18n-zh dictionary; run i18n inject first")
    return json.loads(found.group(1))


def edit(text, pairs):
    for old, new in pairs:
        if text.count(old) != 1:
            raise SystemExit("amend: not found exactly once: " + old[:80])
        text = text.replace(old, new)
    return text


def missing(text):
    zh = dictionary(text)
    return {key: english for key, english in TAGGED.findall(text) if key not in zh}


def merge(text, new_zh):
    """The page's translations for keys it still uses, plus new_zh; and how many keys stay untranslated."""
    used = set(re.findall(r'data-i18n="([^"]+)"', text))
    merged = {k: v for k, v in dictionary(text).items() if k in used}
    merged.update(new_zh)
    return merged, len(used - set(merged))


def head(text):
    # inject re-serialises the page and leaves a <meta charset/> and <!DOCTYPE html> pair after the toggle.
    return "".join(HEAD) + HEAD_TAG.sub("", text)


def main(argv):
    stage, page = argv[:2]
    text = read(page)
    if stage == "edit":
        write(page, edit(text, json.loads(read(argv[2]))))
    elif stage == "missing":
        for key, english in missing(text).items():
            print(json.dumps({key: english}, ensure_ascii=False))
    elif stage == "merge":
        merged, untranslated = merge(text, json.loads(read(argv[2])))
        write(argv[3], json.dumps(merged, ensure_ascii=False, indent=0))
        print(len(merged), "strings;", untranslated, "still missing")
    elif stage == "head":
        write(page, head(text))
    else:
        raise SystemExit("amend: unknown stage " + stage + "; use edit, missing, merge or head")


if __name__ == "__main__":
    main(sys.argv[1:])
