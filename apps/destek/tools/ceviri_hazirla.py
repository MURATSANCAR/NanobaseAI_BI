#!/usr/bin/env python3
"""cevir.py için Türkçe çalışma dosyalarını hazırlar (test sunucusunda koşar).

Girdi klasörü (imajdan çıkarılır, bkz. README «Türkçe»):
    in/flow.pot, in/telephony.pot, in/frappe.tr.po
    work/helpdesk.tr.po, work/nanobase_brand.tr.po   (depodaki hâlleri)
Çıktı: work/flow.tr.po (şablondan), work/nanobase_brand.tr.po (çatı ve telephony'nin
boş metinleri eklenmiş). Dolu çeviriye ve elle yazılmış marka girdilerine dokunulmaz;
yeniden koşturmak aynı girdiyi iki kez eklemez.
"""

import sys
from pathlib import Path

import polib

HEADER = {
	"Language": "tr",
	"MIME-Version": "1.0",
	"Content-Type": "text/plain; charset=UTF-8",
	"Content-Transfer-Encoding": "8bit",
	"Plural-Forms": "nplurals=2; plural=(n != 1);",
}


def main(root: str) -> int:
	base = Path(root)
	inp, work = base / "in", base / "work"

	flow_po = work / "flow.tr.po"
	existing = polib.pofile(str(flow_po), wrapwidth=0) if flow_po.exists() else None
	done = {(e.msgctxt, e.msgid): e.msgstr for e in existing or [] if e.msgstr}
	po = polib.POFile(wrapwidth=0)
	po.metadata = {"Project-Id-Version": "flow", **HEADER}
	for e in polib.pofile(str(inp / "flow.pot"), wrapwidth=0):
		if e.msgid_plural:
			continue
		po.append(polib.POEntry(msgid=e.msgid, msgctxt=e.msgctxt, msgstr=done.get((e.msgctxt, e.msgid), ""),
								occurrences=e.occurrences))
	po.save(str(flow_po))

	brand_path = work / "nanobase_brand.tr.po"
	brand = polib.pofile(str(brand_path), wrapwidth=0)
	have = {(e.msgctxt, e.msgid) for e in brand}
	sources = [e for e in polib.pofile(str(inp / "frappe.tr.po"), wrapwidth=0)
			   if not e.obsolete and not e.msgstr and not e.msgid_plural]
	sources += [e for e in polib.pofile(str(inp / "telephony.pot"), wrapwidth=0) if not e.msgid_plural]
	added = 0
	for e in sources:
		key = (e.msgctxt, e.msgid)
		if not e.msgid.strip() or key in have:
			continue
		have.add(key)
		brand.append(polib.POEntry(msgid=e.msgid, msgctxt=e.msgctxt, msgstr=""))
		added += 1
	brand.save(str(brand_path))

	for name in ("helpdesk.tr.po", "flow.tr.po", "nanobase_brand.tr.po"):
		p = polib.pofile(str(work / name), wrapwidth=0)
		empty = sum(1 for x in p if not x.msgstr and not x.msgid_plural and x.msgid.strip())
		print(f"{name}: {len(p)} girdi, {empty} boş", flush=True)
	print(f"markaya eklenen çatı/telephony girdisi: {added}", flush=True)
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
