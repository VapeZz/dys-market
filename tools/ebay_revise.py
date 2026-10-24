"""Apply listing edits to the connected eBay store (Trading API ReviseFixedPriceItem).

    python tools/ebay_revise.py STORE tools/ebay-edits/<file>.json

Each edit: {"id": item id, "title"?: new title (max 80), "specifics"?: {name: [values]}}.
"specifics" replaces the listing's item specifics, so pass the full set you want to keep.
"""
import json
import sys
from xml.sax.saxutils import escape

import ebay_store
import ebay_user


def body(e):
    parts = [f"<ItemID>{escape(e['id'])}</ItemID>"]
    if e.get("title"):
        assert len(e["title"]) <= 80, "title over 80 characters"
        parts.append(f"<Title>{escape(e['title'])}</Title>")
    if e.get("specifics"):
        nvl = "".join(f"<NameValueList><Name>{escape(k)}</Name>{''.join(f'<Value>{escape(v)}</Value>' for v in vs)}</NameValueList>"
                      for k, vs in e["specifics"].items())
        parts.append(f"<ItemSpecifics>{nvl}</ItemSpecifics>")
    return f"<Item>{''.join(parts)}</Item>"


def main(argv):
    store, path = argv[0], argv[1]
    tok = ebay_user.access_token(store)
    ok = 0
    for e in json.load(open(path)):
        try:
            r = ebay_store.trading(tok, "ReviseFixedPriceItem", body(e))
            warns = [w.findtext("e:ShortMessage", namespaces=ebay_store.NS) for w in r.findall("e:Errors", ebay_store.NS)]
            print(f"::notice title=eBay edit {e['id']}::done ({e.get('why', '')}){' · warnings: ' + '; '.join(w for w in warns if w) if warns else ''}")
            ok += 1
        except Exception as ex:
            print(f"::error title=eBay edit {e['id']}::{str(ex)[:300]}")
    print(f"ebay edits: {ok} of {len(json.load(open(path)))} applied")


if __name__ == "__main__":
    main(sys.argv[1:])
