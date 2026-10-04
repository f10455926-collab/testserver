# -*- coding: utf-8 -*-
"""
Kontrola prostředí pro main.py
"""
import sys
import os

print("=" * 60)
print("KONTROLA PROSTŘEDÍ PRO main.py")
print("=" * 60)

ok = True

# --- Python verze ---
print(f"\n[*] Python: {sys.version.split()[0]}")
if sys.version_info < (3, 8):
    print("    [!] Potřebuješ Python 3.8+")
    ok = False
else:
    print("    [OK]")

# --- Balíčky ---
print("\n[*] Kontrola balíčků:")
packages = [
    ("requests", "requests"),
    ("cloudscraper", "cloudscraper"),
    ("socks", "PySocks"),
    ("colorama", "colorama"),
    ("undetected_chromedriver", "undetected-chromedriver"),
    ("httpx", "httpx"),
    ("h2", "httpx[http2]"),
]
for mod, name in packages:
    try:
        m = __import__(mod)
        ver = getattr(m, "__version__", "?")
        print(f"    [OK] {name} ({ver})")
    except ImportError as e:
        print(f"    [X]  {name} – CHYBÍ ({e})")
        ok = False

# --- Soubory ---
print("\n[*] Kontrola souborů:")
files = [
    ("./proxy.txt", "proxy.txt"),
    ("./resources/ua.txt", "resources/ua.txt"),
    ("./main.py", "main.py"),
]
for path, name in files:
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f"    [OK] {name} ({size} B)")
    else:
        print(f"    [!] {name} – CHYBÍ")
        if name != "main.py":
            ok = False

# --- Parsování proxy.txt ---
print("\n[*] Kontrola formátu proxy.txt:")
if os.path.exists("./proxy.txt"):
    raw = open("./proxy.txt").read().split("\n")
    good, bad = 0, 0
    for line in raw:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "://" in line:
            line = line.split("://", 1)[1]
        parts = line.split(":")
        if len(parts) in (2, 4):
            try:
                int(parts[1])
                good += 1
            except ValueError:
                bad += 1
        else:
            bad += 1
    print(f"    [OK] {good} platných proxy")
    if bad:
        print(f"    [!] {bad} neplatných řádků")
        ok = False
else:
    print("    [X] proxy.txt neexistuje")
    ok = False

# --- Parsování ua.txt ---
print("\n[*] Kontrola ua.txt:")
if os.path.exists("./resources/ua.txt"):
    ua = [x for x in open("./resources/ua.txt").read().split("\n") if x.strip()]
    print(f"    [OK] {len(ua)} User-Agentů")
    if len(ua) < 5:
        print("    [!] Moc málo UA, doporučuji 50+")
else:
    print("    [!] ua.txt chybí (main.py si ho vytvoří sám, ale bude jen 4 UA)")
    ok = False

# --- Test SOCKS5 proxy ---
print("\n[*] Test SOCKS5 proxy (první z proxy.txt):")
try:
    import socks
    import socket
    if os.path.exists("./proxy.txt"):
        raw = open("./proxy.txt").read().split("\n")
        first = None
        for line in raw:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "://" in line:
                line = line.split("://", 1)[1]
            parts = line.split(":")
            if len(parts) in (2, 4):
                first = parts
                break
        if first:
            host, port = first[0], int(first[1])
            user = first[2] if len(first) == 4 else None
            pwd = first[3] if len(first) == 4 else None
            s = socks.socksocket()
            s.settimeout(5)
            if user:
                s.set_proxy(socks.SOCKS5, host, port, username=user, password=pwd)
            else:
                s.set_proxy(socks.SOCKS5, host, port)
            s.connect(("example.com", 80))
            print(f"    [OK] {host}:{port} funguje")
            s.close()
        else:
            print("    [!] Žádná proxy k testu")
except Exception as e:
    print(f"    [X] Proxy test selhal: {e}")
    print("    (Může být jen mrtvá proxy, ne chyba kódu)")

# --- Test Chrome (pro cfreq/cfsoc) ---
print("\n[*] Kontrola Google Chrome (pro cfreq/cfsoc):")
chrome_paths = [
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]
found = False
for p in chrome_paths:
    if os.path.exists(p):
        print(f"    [OK] {p}")
        found = True
        break
if not found:
    print("    [!] Chrome nenalezen – cfreq/cfsoc nebudou fungovat")
    print("    (Ostatní metody fungují bez Chrome)")

# --- Závěr ---
print("\n" + "=" * 60)
if ok:
    print("VŠE OK – můžeš spustit: python3 main.py")
else:
    print("NĚCO CHYBÍ – oprav výše uvedené a spusť znovu")
print("=" * 60)