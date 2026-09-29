"""Kabul: CRM pasif kayıt süzgeci, editör atamanın salt okunur olması, Masam › Görevlerim, CRM hakları ve lisans.

Test sunucusunda, aday kodla açılan yan köprüye (127.0.0.1:8798) kısa ömürlü timasai oturumuyla koşar; referanslar
CRM .28'e süzgeçsiz doğrudan bağlantıyla okunur. Hiçbir şey yazmaz.

    /data/nanobaseai/bi/semantic-venv/bin/python kabul.py   # /tmp/claude-crmtask/cookie: oturum anahtarı
"""
import sys, json, urllib.request, urllib.error
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.profiler.connectors import connector_from_file
raw = connector_from_file("/data/nanobaseai/bi/secrets/crm-mssql-connection.json").inner  # süzgeçsiz referans
P = "Timas_MSCRM.dbo."
def ref(sql): return raw.execute(sql, 100000)[1]
COOKIE = open("/tmp/claude-crmtask/cookie").read().strip()
def api(method, path, body=None):
    req = urllib.request.Request("http://127.0.0.1:8798" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Cookie": f"__Secure-timas_session={COOKIE}; timas_session={COOKIE}",
                                          "Content-Type": "application/json", "Origin": "https://portal.nanobase.ai"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r: return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e: return e.code, (e.read() or b"")[:300].decode("utf-8", "replace")
ok = fail = 0
def check(name, cond, info=""):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print(("OK   " if cond else "KALDI"), name, info)
# K1 editörsüz projeler = CRM referansı
st, d = api("GET", "/api/v1/editorial/assignments/pending")
year = d.get("sinceYear") if st == 200 else None
r = ref(f"SELECT COUNT(*) n FROM {P}new_projeBase j WHERE j.statecode=0 AND j.new_editoru IS NULL AND j.CreatedOn>='{year}-01-01' AND j.statuscode IN (100000019,100000020)")[0]["n"] if year else None
check("K1 editörsüz proje sayısı", st == 200 and d["total"] == r, f"ekran {d.get('total') if st==200 else st} / ref {r}")
check("K1b portal atama sütunu yok", st == 200 and "onBoard" not in d)
# K2 kaldırılan yazma uçları
for m, p in (("POST", "/api/v1/editorial/assignments"), ("GET", "/api/v1/editorial/assignments/editors"),
             ("GET", "/api/v1/editorial/assignments/rules"), ("POST", "/api/v1/editorial/tasks/mine/adopt")):
    s2, _ = api(m, p, {} if m == "POST" else None)
    check(f"K2 kaldırıldı {m} {p}", s2 in (404, 405), f"durum {s2}")
# K3 Görevlerim (timasai CRM kullanıcısı)
st, g = api("GET", "/api/v1/editorial/tasks/mine")
check("K3 Görevlerim ucu", st == 200 and "tasks" in g, f"durum {st} me={g.get('me') if st==200 else g}")
if st == 200 and g.get("me"):
    n = ref(f"SELECT COUNT(*) n FROM {P}new_projeBase j WHERE j.statecode=0 AND j.new_editoru='{g['me']['id']}' AND j.statuscode IN (100000019,100000020) AND j.CreatedOn>='{g['sinceYear']}-01-01'")[0]["n"]
    check("K3b Görevlerim satırı = CRM'de editörü olduğu proje", len(g["tasks"]) <= n, f"ekran {len(g['tasks'])} / ref {n}")
# K4 sözleşme listesi: hak etiketleri ve toplam
st, c = api("GET", "/api/v1/editorial/contracts")
r = ref(f"SELECT COUNT(*) n FROM {P}new_sozlesmeBase s WHERE s.statecode=0")[0]["n"]
check("K4 sözleşme toplamı", st == 200 and c["total"] == r, f"ekran {c.get('total') if st==200 else st} / ref {r}")
if st == 200:
    first = c["items"][0]
    rr = ref(f"SELECT CAST(new_iletimhakki AS int) il, CAST(new_EKitap AS int) ek, CAST(new_SesliKitapHakki AS int) se FROM {P}new_sozlesmeBase WHERE new_sozlesmeId='{first['id']}'")[0]
    got = {x["key"]: x["granted"] for x in first.get("rights", [])}
    check("K4b liste hakları = CRM (iletim, e-kitap, sesli)", (got.get("iletim"), got.get("ekitap"), got.get("sesli")) ==
          tuple(None if rr[k] is None else bool(rr[k]) for k in ("il", "ek", "se")), f"{got.get('iletim'), got.get('ekitap'), got.get('sesli')} / {rr}")
# K5 kitap 360 hak özeti (çok sözleşmeli kitap)
b = ref(f"SELECT TOP 1 sk.new_kitapid FROM {P}new_new_sozlesme_new_kitapBase sk JOIN {P}new_sozlesmeBase s ON s.new_sozlesmeId=sk.new_sozlesmeid WHERE s.statecode=0 AND s.new_SozlesmeTipi=5 AND s.statuscode IN (100000000,100000006,100000007) GROUP BY sk.new_kitapid HAVING SUM(CASE WHEN ISNULL(s.new_iletimhakki,0)=0 THEN 1 ELSE 0 END)>0 AND COUNT(*)>=2 ORDER BY COUNT(*) DESC")[0]["new_kitapid"]
st, bk = api("GET", f"/api/v1/editorial/books/{b}")
rr = ref(f"SELECT COUNT(*) n, SUM(CASE WHEN s.new_iletimhakki=1 THEN 1 ELSE 0 END) il FROM {P}new_new_sozlesme_new_kitapBase sk JOIN {P}new_sozlesmeBase s ON s.new_sozlesmeId=sk.new_sozlesmeid WHERE s.statecode=0 AND s.new_SozlesmeTipi=5 AND s.statuscode IN (100000000,100000006,100000007) AND sk.new_kitapid='{b}'")[0]
it = {x["key"]: x for x in (bk.get("rights") or {}).get("items", [])} if st == 200 else {}
check("K5 kitap hak tabanı = yürürlükteki Telif Alış", st == 200 and bk["rights"]["basis"] == rr["n"], f"ekran {bk['rights']['basis'] if st==200 else st} / ref {rr['n']}")
check("K5b iletim hakkı sayısı ve durum", st == 200 and it["iletim"]["yes"] == (rr["il"] or 0) and it["iletim"]["state"] in ("kismi", "yok"),
      f"{it.get('iletim', {}).get('yes')}/{it.get('iletim', {}).get('of')} {it.get('iletim', {}).get('state')} / ref {rr}")
# K6 kişi kartı: sözleşme sayısı (tekil) ve haklar
cid = ref(f"SELECT TOP 1 t.new_kisi FROM {P}new_sozlesmetarafiBase t JOIN {P}new_sozlesmeBase s ON s.new_sozlesmeId=t.new_sozlesmeid JOIN {P}ContactBase c ON c.ContactId=t.new_kisi WHERE t.statecode=0 AND s.statecode=0 AND c.statecode=0 GROUP BY t.new_kisi HAVING COUNT(*) BETWEEN 5 AND 20 ORDER BY COUNT(*) DESC")[0]["new_kisi"]
st, pe = api("GET", f"/api/v1/editorial/contributors/{cid}")
n = ref(f"SELECT COUNT(DISTINCT s.new_sozlesmeId) n FROM {P}new_sozlesmetarafiBase t JOIN {P}new_sozlesmeBase s ON s.new_sozlesmeId=t.new_sozlesmeid WHERE t.statecode=0 AND s.statecode=0 AND t.new_kisi='{cid}'")[0]["n"]
check("K6 kişi sözleşme sayısı", st == 200 and len(pe["contracts"]) == n, f"ekran {len(pe['contracts']) if st==200 else st} / ref {n}")
check("K6b kişi sözleşmelerinde haklar ve lisans", st == 200 and all("rights" in x and "license" in x for x in pe["contracts"]))
if st == 200:
    print("     örnek lisans:", json.dumps(pe["contracts"][0]["license"]["terms"], ensure_ascii=False)[:300])
# K7 sözleşme ayrıntısı: CRM hakları, lisans, ülke/dil
sid = ref(f"SELECT TOP 1 x.new_sozlesmeid FROM {P}new_new_sozlesme_new_ulkeBase x JOIN {P}new_sozlesmeBase s ON s.new_sozlesmeId=x.new_sozlesmeid WHERE s.statecode=0 GROUP BY x.new_sozlesmeid HAVING COUNT(*)>=2")[0]["new_sozlesmeid"]
st, dt = api("GET", f"/api/v1/editorial/contracts/item/{sid.lower()}")
n = ref(f"SELECT COUNT(*) n FROM {P}new_new_sozlesme_new_ulkeBase x JOIN {P}new_ulkeBase u ON u.new_ulkeId=x.new_ulkeid WHERE x.new_sozlesmeid='{sid}' AND u.statecode=0")[0]["n"]
lic = (dt.get("crm") or {}).get("license") if st == 200 else None
check("K7 sözleşme ayrıntısı hak listesi (12)", st == 200 and len(dt["crm"]["rights"]) == 12, f"durum {st}")
check("K7b ülke kapsamı = CRM (etkin ülke)", st == 200 and lic and len(lic["countries"]) == n, f"ekran {len(lic['countries']) if lic else '-'} / ref {n}")
if lic: print("     seçenek etiketleri:", {k: lic["terms"].get(k) for k in ("paymentType", "basis", "paymentMethod", "currency")})
# K8 pasif kayıt: ContactBase pasif kişi sözleşme tarafında görünmez
pas = ref(f"SELECT TOP 1 s.new_sozlesmeId, c.FullName FROM {P}new_sozlesmetarafiBase t JOIN {P}ContactBase c ON c.ContactId=t.new_kisi JOIN {P}new_sozlesmeBase s ON s.new_sozlesmeId=t.new_sozlesmeid WHERE c.statecode=1 AND t.statecode=0 AND s.statecode=0")
if pas:
    st, dt = api("GET", f"/api/v1/editorial/contracts/item/{pas[0]['new_sozlesmeId'].lower()}")
    names = [p["name"] for p in (dt.get("crm") or {}).get("terms", {}).get("parties", [])] if st == 200 else []
    check("K8 pasif kişi sözleşme tarafında görünmüyor", st == 200 and pas[0]["FullName"] not in names, f"pasif «{pas[0]['FullName']}» · taraflar {names}")
else:
    print("BİLGİ K8: pasif kişili etkin sözleşme tarafı yok")
print(f"\nSONUÇ: {ok} geçti, {fail} kaldı")
# K9 /haklar hak kartı: orijinal dil adı bağlı kayıttan, CRM hakları 12, lisans
row = ref(f"SELECT TOP 1 sk.new_kitapid, d.new_name dil, s.new_sozlesmeId sid FROM {P}new_new_sozlesme_new_kitapBase sk JOIN {P}new_sozlesmeBase s ON s.new_sozlesmeId=sk.new_sozlesmeid JOIN {P}new_dilBase d ON d.new_dilId=s.new_orjinaldili WHERE s.statecode=0 AND d.statecode=0 AND s.new_SozlesmeTipi=5 ORDER BY s.ModifiedOn DESC")[0]
st, card = api("GET", f"/api/v1/rights/books/{row['new_kitapid'].lower()}")
cs = [x for x in (card.get("contracts") or []) if x["id"] == row["sid"].lower()] if st == 200 else []
check("K9 hak kartı orijinal dil adı = CRM", bool(cs) and cs[0]["originalLanguage"] == row["dil"], f"ekran {cs[0]['originalLanguage'] if cs else st} / ref {row['dil']}")
check("K9b hak kartında 12 CRM hakkı ve lisans", bool(cs) and len(cs[0].get("crmRights") or []) == 12 and "terms" in (cs[0].get("license") or {}))
print(f"\nSONUÇ (K9 dahil): {ok} geçti, {fail} kaldı")
