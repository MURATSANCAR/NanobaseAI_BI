"""Logo ve CRM veri sözlüğü: her tablo ve kolon için bildiğimiz ya da sistemde yazan açıklama."""
import ast, glob, json, os, re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Girdi: ölçüm çıktıları (logo2.json, crm2.json, sozluk_meta.json, crm-sozluk-tam.json)
W = os.environ.get("SOZLUK_GIRDI", "/tmp/kaynak-sozlugu")
OUT = f"{REPO}/docs/kaynak-sozlugu/VERI-SOZLUGU-LOGO-CRM-2026-10-03.xlsx"

L = json.load(open(f"{W}/logo2.json"))
C = json.load(open(f"{W}/crm2.json"))
META = json.load(open(f"{W}/sozluk_meta.json"))
CRMFULL = json.load(open(f"{W}/crm-sozluk-tam.json"))["varliklar"]
SZ = json.load(open(f"{REPO}/docs/kaynak-sozlugu/logo-sozluk.json"))
LDDS = json.load(open(f"{REPO}/configs/schemas/logo-ldds.json"))["tables"]
TTR = json.load(open(f"{REPO}/configs/schemas/logo-table-translations.json"))
TEV = json.load(open(f"{REPO}/configs/schemas/logo-table-description-evidence.json"))["entries"]
EN2TR = {}
for f in sorted(glob.glob(f"{REPO}/configs/schemas/logo-column-translations-*.json")):
    EN2TR.update(json.load(open(f)).get("translations") or {})


AILE_AD = {a["aile"]: a.get("is_adi") for a in SZ["aileler"] if a.get("is_adi")}


def fam_of(physical):
    return re.sub(r"^LG_(XXX_)?(XX_)?", "", physical).upper()


LD = {}
for k, t in LDDS.items():
    LD.setdefault(fam_of(t.get("physical") or k), t)
PROF = {re.sub(r"\{N#\}", "#", k): v for k, v in META["profiles"].items()}
NOTES = {}
for n in META["notes"]:
    NOTES.setdefault((re.sub(r"\{n\d+\}", "#", n["table_pattern"]).upper(), n["column_name"].upper()), []).append(n["text"])


KALIP = {"L_RPLAYS": "Kullanıcıya ait rapor düzeni (Logo arayüz ayarı; iş verisi değil)",
         "L_RPFILTS": "Kullanıcıya ait rapor filtresi (Logo arayüz ayarı; iş verisi değil)",
         "L_TABLELAYS": "Kullanıcıya ait ekran tablosu düzeni (Logo arayüz ayarı; iş verisi değil)",
         "L_LDOCNUM": "Belge numaralama sayaçları (Logo sistem tablosu)",
         "DLG_USERTEMPLIST": "Kullanıcı geçici listesi (Logo arayüz ayarı)", "DLG_USERGBLIST": "Kullanıcı liste ayarı (Logo arayüz ayarı)",
         "DLG_USERPKLIST": "Kullanıcı liste ayarı (Logo arayüz ayarı)"}


def base_family(fam):
    """Belgede olmayan tablo adını belgelenmiş ana tabloya bağlar: yedek/tarih sonekleri ve özel önekler atılır."""
    if fam in LD or fam in SZ["kolon_sozlugu"]:
        return fam, False
    parts = fam.split("_")
    for i in range(len(parts)):
        for j in range(len(parts), i, -1):
            cand = "_".join(parts[i:j])
            if len(cand) >= 4 and not cand.isdigit() and (cand in LD or cand in SZ["kolon_sozlugu"]):
                return cand, True
    return fam, False


def kalip(tab):
    b = re.sub(r"_?\d+$", "", tab.upper())
    return KALIP.get(b)


def pattern(tab):
    return re.sub(r"\d+", "#", tab.upper())


def vals(d):
    return "; ".join(f"{k} = {v}" for k, v in list(d.items())[:40]) + (" …" if len(d) > 40 else "")


def first(*pairs):
    for text, src in pairs:
        if text and str(text).strip():
            return str(text).strip(), src
    return "", ""


TUR = {"dönem": "Dönem hareketi (LG_411_01_)", "firma": "Firma kartı (LG_411_)", "genel": "Genel / sistem (L_)", "özel": "Özel tablo (TİMAŞ)"}

# ------------------------------------------------------------------ Logo
logo_tables, logo_cols = [], []
for t in sorted([t for t in L if t.get("satir")], key=lambda x: -x["satir"]):
    tab = t["tablo"]
    fam, same = base_family(t["aile"])
    ld = LD.get(fam) or {}
    pr = PROF.get(pattern(tab)) or {}
    ours_t = (SZ["kolon_sozlugu"].get(fam) or {}).get("ldds", {}).get("tr") if fam in SZ["kolon_sozlugu"] else None
    desc, src = first((ours_t, "Bizim sözlük"), ((TTR.get(fam) or {}).get("description_tr"), "Logo belgesi (TR çeviri)"),
                      ((TEV.get(fam) or {}).get("description_tr"), "Logo belgesi (TR çeviri)"),
                      (EN2TR.get(ld.get("description") or ""), "Logo belgesi (TR çeviri)"),
                      (pr.get("desc"), "Eski katalog (otomatik)"), (ld.get("description"), "Logo belgesi (İngilizce)"),
                      (AILE_AD.get(fam) or AILE_AD.get(t["aile"]), "Bizim sözlük (aile adı)"), (kalip(tab), "Ad kalıbından çıkarım"))
    if same and desc:
        desc, src = f"{desc} — {t['aile']} adlı kopya/türev", f"{src} (aynı yapı: {fam})"
    measured = {c["kolon"].upper(): c for c in t.get("kolonlar", [])}
    names = list(dict.fromkeys([*(ld.get("columns") or {}).keys(), *(pr.get("all") or {}).keys(), *measured.keys()]))
    known = SZ["kolon_sozlugu"].get(fam, {}).get("kolonlar", {})
    n_desc = 0
    for col in names:
        cu = col.upper()
        lc = (ld.get("columns") or {}).get(col) or (ld.get("columns") or {}).get(cu) or {}
        k = known.get(cu) or {}
        notes = " ".join(NOTES.get((pattern(tab), cu), []))
        ours = " ".join(x for x in (k.get("anlam"), notes) if x)
        tr = lc.get("description_tr") or EN2TR.get(lc.get("description") or "")
        d, s = first((ours, "Bizim sözlük"), (tr, "Logo belgesi"), ((pr.get("cols") or {}).get(cu), "Eski katalog (otomatik)"),
                     (lc.get("description"), "Logo belgesi (İngilizce)"))
        if same and s in ("Bizim sözlük", "Logo belgesi", "Logo belgesi (İngilizce)"):
            s = f"{s} (aynı yapı: {fam})"
        if d:
            n_desc += 1
        kod = (SZ["kod_sozlugu"].get(f"{fam}.{cu}") or {}).get("degerler")
        values = vals({v["deger"]: v.get("anlam") or v.get("ldds_etiketi") for v in kod.values()}) if kod else \
            vals(lc["values_tr"]) if lc.get("values_tr") else vals(k["ldds"]["degerler"]) if (k.get("ldds") or {}).get("degerler") else ""
        m = measured.get(cu)
        logo_cols.append([tab, t["aile"], col, (m or {}).get("tur") or lc.get("type") or (pr.get("all") or {}).get(cu) or "",
                          d, s, values, k.get("guven") or "", (m or {}).get("dolu", 0), (m or {}).get("oran", 0.0),
                          "Evet" if m and m.get("ogrenildi") else "Hayır", lc.get("description") or ""])
    logo_tables.append([tab, t["aile"], TUR.get(t["tur"], t["tur"]), t["satir"], desc, src, len(names), n_desc,
                        len(measured), "Evet" if t["kodda"] else "Hayır"])

# ------------------------------------------------------------------ CRM: bizim tanımlarımız
src = open(f"{REPO}/backend/semantic_bridge/finance_query/relational_contracts.py").read()
reg = {}
for n in ast.parse(src).body:
    if isinstance(n, ast.Assign) and any(getattr(x, "id", "") == "ENTITY_REGISTRY" for x in n.targets):
        reg = ast.literal_eval(n.value)
OURS_T, OURS_C, REL_C = {}, {}, {}
for ent, e in reg.items():
    OURS_T[e["table"]] = "; ".join(e.get("semantic_notes") or [])
    for logical, f in e["fields"].items():
        REL_C.setdefault((e["table"], f["column"].lower()), logical)
cq = open(f"{REPO}/backend/semantic_bridge/finance_query/crm_query.py").read()
FIELDS = TABLES = {}
for n in ast.parse(cq).body:
    if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("FIELDS", "TABLES"):
        v = ast.literal_eval(n.value)
        if n.targets[0].id == "FIELDS":
            FIELDS = v
        else:
            TABLES = v
for logical, (ent, expr, typ, meaning) in FIELDS.items():
    col = expr.split(".")[-1].lower()
    tabs = TABLES.values() if ent == "all" else [TABLES.get(ent) or ("new_markaBase" if expr.startswith("m.") else None)]
    if expr.startswith("m."):
        tabs = ["new_markaBase"]
    for tb in tabs:
        if tb:
            OURS_C[(tb, col)] = meaning
measured_c = {t["tablo"]: {c["kolon"].lower(): c for c in t.get("kolonlar", [])} for t in C}
measured_t = {t["tablo"]: t for t in C}
SINIF = {"kunye": "Künye kartı", "iliski": "İlişki / ara tablo", "surec": "Süreç", "bilinmiyor": "Sınıflanmamış",
         "logo_kopyasi_aday": "Logo kopyası adayı", "hedef_plan": "Hedef / plan", "sozlesme_hak": "Sözleşme / hak",
         "sistem": "Sistem", "entegrasyon_log": "Entegrasyon günlüğü", None: "Sınıflanmamış"}
crm_tables, crm_cols = [], []
for e in sorted([e for e in CRMFULL if e.get("satir")], key=lambda x: -x["satir"]):
    tab = e["tablo"]
    mt = measured_t.get(tab) or {}
    mc = measured_c.get(tab, {})
    olculdu = bool(mt.get("kolonlar") is not None and not mt.get("olculmedi"))
    desc, srcl = first((OURS_T.get(tab), "Bizim tanım"), (e.get("aciklama"), "CRM açıklaması"))
    n_desc = 0
    fields = e.get("alanlar") or []
    for a in fields:
        col = a.get("fiziksel_kolon") or a.get("alan") or ""
        ours = OURS_C.get((tab, col.lower())) or OURS_C.get((a.get("tablo") or tab, col.lower()))
        d, s = first((ours, "Bizim tanım"), (a.get("aciklama"), "CRM açıklaması"), (a.get("etiket"), "CRM etiketi"))
        if d:
            n_desc += 1
        opts = vals({o["deger"]: o["etiket"] for o in a.get("secenekler") or []}) if a.get("secenekler") else ""
        m = mc.get(col.lower())
        crm_cols.append([tab, e.get("mantiksal_ad") or "", col, a.get("alan") or "", a.get("etiket") or "", d, s,
                         a.get("tur") or "", opts, ", ".join(a.get("hedef") or []), "Evet" if a.get("ozel") else "Hayır",
                         (m or {}).get("dolu", 0) if olculdu else None, (m or {}).get("oran", 0.0) if olculdu else None,
                         "Evet" if m and m.get("ogrenildi") else "Hayır", REL_C.get((tab, col.lower())) or ""])
    crm_tables.append([tab, e.get("mantiksal_ad") or "", e.get("turkce_ad") or "", desc, srcl, SINIF.get(e.get("sinif"), e.get("sinif")),
                       "Evet" if e.get("ozel") else "Hayır", e["satir"], len(fields), n_desc,
                       len(mc) if olculdu else None, "Evet" if mt.get("kodda") else "Hayır"])

# ------------------------------------------------------------------ Excel
F = "Arial"
H = Font(name=F, bold=True, color="FFFFFF"); HF = PatternFill("solid", fgColor="1F4E78"); B = Font(name=F)
wb = Workbook()


def sheet(ws, headers, rows, widths, pct=(), num=(), wrap=()):
    ws.append(headers)
    for c in ws[1]:
        c.font, c.fill, c.alignment = H, HF, Alignment(wrap_text=True, vertical="center")
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font = B
            if c.column in pct:
                c.number_format = "0.0%"
            elif c.column in num:
                c.number_format = "#,##0"
            if c.column in wrap:
                c.alignment = Alignment(wrap_text=False, vertical="top")
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
    ws.row_dimensions[1].height = 34


ws = wb.active; ws.title = "Okuma notu"
lines = [
    ("Logo ve CRM veri sözlüğü", True),
    ("Her tablo ve kolon için bildiğimiz açıklama; bilmiyorsak sistemde yazan açıklama. «Açıklama kaynağı» sütunu hangisi olduğunu söyler.", False),
    ("", False),
    ("Açıklama kaynakları (öncelik sırasıyla)", True),
    ("Logo — Bizim sözlük: canlı veride ölçülüp yazılmış anlam (docs/kaynak-sozlugu/logo-sozluk.json, 34 tablo ailesi) ve veri notları.", False),
    ("Logo — Logo belgesi: Logo'nun resmî tablo/kolon belgesi (LDDS) Türkçe açıklaması ya da Türkçe çevirisi; yoksa İngilizce özgün metin.", False),
    ("Logo — Eski katalog (otomatik): 2026-09-07/09 taramasında modelin yazdığı kolon açıklaması; doğrulanmamıştır.", False),
    ("CRM — Bizim tanım: sohbet motorunun kullandığı alan tanımı (crm_query.py, relational_contracts.py).", False),
    ("CRM — CRM açıklaması / etiketi: CRM'in kendi Türkçe metadata metni (alan açıklaması, yoksa ekran etiketi).", False),
    ("", False),
    ("Kapsam", True),
    ("Logo: verisi dolu 778 tablo (2026 firması 411, genel L_ ve özel tablolar). Kolon listesi Logo belgesi + eski katalog + canlı ölçümün birleşimi. 2021–2025 (211) kopyaları aynı yapıdadır.", False),
    ("CRM: verisi dolu bütün varlıklar ve alanları (CRM metadata, 2026-10-01).", False),
    ("Dolu satır / doluluk: 2026-10-02 canlı ölçüm (sayısal 0, boş metin, 1900 öncesi tarih boş sayılır). CRM sistem/günlük tablolarında ölçülmedi (boş).", False),
    ("«Kodda kullanılıyor»: alanın adı ürün kodunda o tabloyu anan bir dosyada geçiyor.", False),
    ("Kod / seçenek değerleri: Logo için bizim ölçtüğümüz değer anlamları ya da Logo belgesi; CRM için seçenek listesi.", False),
]
for i, (t, bold) in enumerate(lines, 1):
    c = ws.cell(i, 1, t); c.font = Font(name=F, bold=bold, size=14 if i == 1 else 10); c.alignment = Alignment(wrap_text=True)
ws.column_dimensions["A"].width = 130

sheet(wb.create_sheet("Logo tablolar"), ["Tablo", "Aile", "Tür", "Satır", "Tablo açıklaması", "Açıklama kaynağı",
      "Kolon sayısı", "Açıklaması olan kolon", "Dolu kolon", "Kodda kullanılıyor"], logo_tables,
      [30, 22, 26, 13, 55, 22, 11, 13, 11, 11], num=(4, 7, 8, 9))
sheet(wb.create_sheet("Logo kolonlar"), ["Tablo", "Aile", "Kolon", "Veri tipi", "Açıklama", "Açıklama kaynağı", "Kod değerleri",
      "Güven (bizim sözlük)", "Dolu satır", "Doluluk", "Kodda kullanılıyor", "Logo belgesi (İngilizce özgün)"], logo_cols,
      [28, 20, 24, 11, 70, 22, 50, 11, 12, 9, 11, 45], pct=(10,), num=(9,))
sheet(wb.create_sheet("CRM varlıklar"), ["Tablo", "Varlık", "Türkçe ad", "Varlık açıklaması", "Açıklama kaynağı", "Sınıf",
      "TİMAŞ'a özel", "Satır", "Alan sayısı", "Açıklaması olan alan", "Dolu alan", "Kodda kullanılıyor"], crm_tables,
      [30, 26, 28, 60, 16, 18, 10, 13, 10, 13, 10, 11], num=(8, 9, 10, 11))
sheet(wb.create_sheet("CRM alanlar"), ["Tablo", "Varlık", "Fiziksel kolon", "Mantıksal ad", "CRM etiketi", "Açıklama", "Açıklama kaynağı",
      "Alan türü", "Seçenekler", "Bağlantı hedefi", "TİMAŞ'a özel", "Dolu satır", "Doluluk", "Kodda kullanılıyor", "Motorda kullanılan ad"], crm_cols,
      [28, 22, 28, 26, 28, 70, 16, 12, 50, 20, 10, 12, 9, 11, 18], pct=(13,), num=(12,))
wb.save(OUT)
from collections import Counter
print(OUT)
print("logo", len(logo_tables), "tablo", len(logo_cols), "kolon", Counter(r[5] for r in logo_cols))
print("crm", len(crm_tables), "varlik", len(crm_cols), "alan", Counter(r[6] for r in crm_cols))
