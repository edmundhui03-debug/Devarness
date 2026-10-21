"""Copy a PRD/SPEC page for the review box with the shared reader inlined.

usage: inline_reader.py PAGE.html ASSETS_DIR OUT.html
A page links ../assets/reader.css and reader.js; outside dev those relative links
break and the copy renders unstyled, so the copy carries both files inside it.
"""
import re
import sys
from pathlib import Path

CSS_LINK = re.compile(r'<link[^>]*href="\.\./assets/reader\.css"[^>]*>')
JS_SCRIPT = re.compile(r'<script[^>]*src="\.\./assets/reader\.js"[^>]*></script>')


def inline(text, css, js):
    if len(CSS_LINK.findall(text)) != 1 or len(JS_SCRIPT.findall(text)) != 1:
        raise SystemExit("inline_reader: the page does not link reader.css and reader.js exactly once")
    text = CSS_LINK.sub(lambda _: "<style>\n" + css + "\n</style>", text)
    # An inline script ignores defer, so run the reader once the document has parsed.
    return JS_SCRIPT.sub(lambda _: "<script>\ndocument.addEventListener('DOMContentLoaded', function () {\n"
                         + js + "\n});\n</script>", text)


def main(argv):
    page, assets, out = (Path(a) for a in argv[:3])
    text = inline(page.read_text(encoding="utf-8"), (assets / "reader.css").read_text(encoding="utf-8"),
                  (assets / "reader.js").read_text(encoding="utf-8"))
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


if __name__ == "__main__":
    main(sys.argv[1:])
