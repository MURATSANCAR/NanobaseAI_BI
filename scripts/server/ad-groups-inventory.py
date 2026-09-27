"""AD'deki grupların dökümü — yetki rolleri hangi gruplara bağlanacak, ona bakmak için (salt okuma).

Giriş servisinin AD ayarını ve kütüphanelerini kullanır; test sunucusunda (VPN açıkken) koşar:

    sudo /opt/timas-login/venv/bin/python scripts/server/ad-groups-inventory.py

Çıktı: grupların OU'ya göre dağılımı, her grubun türü (güvenlik/dağıtım), kapsamı, doğrudan üye sayısı,
açıklaması; etkin kullanıcıların OU dağılımı. Kişi adı yazmaz.
"""
import collections
import json
import sys

sys.path.insert(0, '/opt/timas-login')
from server import AD_FILE, ensure_md4  # noqa: E402

ensure_md4()
from ldap3 import NONE, NTLM, SUBTREE, Connection, Server  # noqa: E402

ENABLED_PERSON = '(&(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))'


def ou_of(dn):
    return ','.join(p for p in dn.split(',')[1:] if not p.upper().startswith('DC=')) or '(kök)'


def first(v):
    return (v[0] if v else '') if isinstance(v, list) else (v or '')


def main():
    c = json.load(open(AD_FILE))
    server = Server(c['host'], port=int(c.get('port', 389)), get_info=NONE, connect_timeout=5)
    conn = Connection(server, user=f"{c['netbios']}\\{c['bind_user']}", password=c['bind_password'],
                      authentication=NTLM, receive_timeout=30)
    if not conn.bind():
        sys.exit(f'servis hesabı reddedildi: {conn.result}')

    rows = []
    for e in conn.extend.standard.paged_search(
            c['base_dn'], '(objectClass=group)', SUBTREE, paged_size=500, generator=True,
            attributes=['sAMAccountName', 'distinguishedName', 'groupType', 'member', 'description']):
        if e.get('type') != 'searchResEntry':
            continue
        a = e['attributes']
        gt = int(first(a.get('groupType')) or 0) & 0xFFFFFFFF
        kind = 'güvenlik' if gt & 0x80000000 else 'dağıtım'
        scope = ('yerleşik' if gt & 1 else 'global' if gt & 2 else 'etki-alanı-yerel' if gt & 4
                 else 'evrensel' if gt & 8 else '?')
        rows.append((ou_of(first(a.get('distinguishedName')) or e['dn']), first(a.get('sAMAccountName')), kind, scope,
                     len(a.get('member') or []), str(first(a.get('description')))[:70]))
    rows.sort()
    print(f'toplam grup: {len(rows)}')
    print('\n== OU başına grup sayısı')
    for ou, n in collections.Counter(r[0] for r in rows).most_common():
        print(f'{n:5}  {ou}')
    print('\n== gruplar (OU | ad | tür | kapsam | doğrudan üye | açıklama)')
    for r in rows:
        print(' | '.join(map(str, r)))

    users = collections.Counter()
    for e in conn.extend.standard.paged_search(c['base_dn'], ENABLED_PERSON, SUBTREE, paged_size=500,
                                               generator=True, attributes=['distinguishedName']):
        if e.get('type') == 'searchResEntry':
            users[ou_of(first(e['attributes'].get('distinguishedName')) or e['dn'])] += 1
    print(f'\n== etkin kullanıcıların OU dağılımı ({sum(users.values())})')
    for ou, n in users.most_common():
        print(f'{n:5}  {ou}')
    conn.unbind()


if __name__ == '__main__':
    main()
