"""Basın ve web — robots.txt okuyucusu (DB ve ağ gerektirmez).

Python'un robotparser'ı `*` jokerini anlamıyor (2026-09-24 kanal ölçümünde iTunes aramasını yanlış "izinli" saydı);
`web_watch.parse_robots` + `path_allowed` RFC 9309'a göre okur. Koşturma:  python3 tests/editorial/web_robots.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from semantic_bridge.web_watch import parse_robots, path_allowed  # noqa: E402

sonuc = []


def ok(ad, kosul):
    print(("GEÇTİ  " if kosul else "DÜŞTÜ  ") + ad)
    sonuc.append(kosul)


p = parse_robots("User-agent: *\nDisallow: /search*\nAllow: /\n")
ok("joker: /search* aramayı kapatır", not path_allowed(p, "/search?term=kitap"))
ok("joker: başka yol açık", path_allowed(p, "/podcast/1"))

p = parse_robots("User-agent: *\nDisallow: /*-p-*/yorumlar\n")
ok("ortadaki joker: ürün yorumu kapalı", not path_allowed(p, "/kitap-x-p-123/yorumlar"))
ok("ortadaki joker: ürün sayfası açık", path_allowed(p, "/kitap-x-p-123"))

p = parse_robots("User-agent: *\nDisallow: /*.html$\n")
ok("$: .html ile biten kapalı", not path_allowed(p, "/haber/1.html"))
ok("$: .html? sorgulu yol açık", path_allowed(p, "/haber/1.html?x=1"))

p = parse_robots("User-agent: *\nDisallow: /w/\nAllow: /w/api.php?action=mobileview&\n")
ok("uzun Allow kazanır", path_allowed(p, "/w/api.php?action=mobileview&page=x"))
ok("kısa Disallow geçerli", not path_allowed(p, "/w/index.php"))

p = parse_robots("User-agent: *\nAllow: /\nContent-Signal: ai-train=no, search=yes, ai-input=no\n")
ok("Content-Signal ai-input=no okunur", p["aiInputNo"])
p = parse_robots("User-agent: *\nContent-Signal: ai-train=no, search=yes, ai-input=yes\nAllow: /\n")
ok("ai-input=yes engel değil", not p["aiInputNo"])

p = parse_robots("User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
ok("başka botun yasağı bize uymaz", path_allowed(p, "/k/yazar/"))
p = parse_robots("User-agent: TimasZekiBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
ok("adımıza yazılmış grup öncelikli", not path_allowed(p, "/"))

p = parse_robots("User-agent: *\nCrawl-delay: 10\nDisallow:\n")
ok("Crawl-delay okunur, boş Disallow kapatmaz", p["delay"] == 10.0 and path_allowed(p, "/rss.xml"))

p = parse_robots("User-agent: Bingbot\nUser-agent: *\nDisallow: /feeds/videos.xml\n")
ok("ardışık User-agent tek grup: YouTube RSS kapalı", not path_allowed(p, "/feeds/videos.xml?channel_id=1"))

print("SONUÇ:", f"{sum(sonuc)}/{len(sonuc)} geçti")
raise SystemExit(0 if all(sonuc) else 1)
