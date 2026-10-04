import os
import sys
import subprocess

print("""
\x1b[38;2;255;20;147m╦╔═ ╔═╗ ╦═╗ ╔╦╗ ╔═╗
\x1b[38;2;255;20;147m╠╩╗ ╠═╣ ╠╦╝ ║║║ ╠═╣
\x1b[38;2;255;20;147m╩ ╩ ╩ ╩ ╩╚═ ╩ ╩ ╩ ╩\x1b[38;2;0;255;58m>(setup)
""")

print("""[0] pip
[1] pip3
Which one do you use?""")

c = input(">>>: ").strip()

if c == "0":
    pip = "pip"
elif c == "1":
    pip = "pip3"
else:
    print("Neplatná volba, použiju pip3.")
    pip = "pip3"

# ============================================================
# Instalace Python balíčků
# ============================================================
packages = [
    "requests",              # FIX: chybělo
    "cloudscraper",
    "pysocks",               # FIX: 'socks' je deprecated, PySocks je správný
    "colorama",
    "undetected-chromedriver",
    '"httpx[http2]"',        # FIX: bez [http2] nefunguje http2/pxhttp2
]

print(f"\n[*] Instaluji Python balíčky přes {pip}...\n")
for pkg in packages:
    # Pro "httpx[http2]" je potřeba zachovat uvozovky kvůli shellu
    if pkg.startswith('"'):
        cmd = f'{pip} install {pkg}'
    else:
        cmd = f'{pip} install {pkg}'
    print(f"[>] {cmd}")
    ret = os.system(cmd)
    if ret != 0:
        print(f"[!] Instalace {pkg} selhala (kód {ret}), pokračuji...")

# ============================================================
# Google Chrome pro undetected_chromedriver (cfreq, cfsoc)
# ============================================================
if os.name == "nt":
    print("\n[*] Windows detekován – Chrome si nainstaluj ručně, pokud ho nemáš.")
else:
    print("\n[*] Linux detekován – kontroluji Google Chrome...")
    if os.path.exists("/usr/bin/google-chrome") or os.path.exists("/usr/bin/google-chrome-stable"):
        print("[*] Google Chrome už je nainstalovaný, přeskakuji.")
    else:
        print("[*] Google Chrome nenalezen, zkouším nainstalovat...")
        # Zjistit, jestli jsme root
        is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
        sudo = "" if is_root else "sudo "

        # curl nebo wget
        if os.system("which curl > /dev/null 2>&1") == 0:
            downloader = "curl -LO"
        elif os.system("which wget > /dev/null 2>&1") == 0:
            downloader = "wget"
        else:
            print("[!] Ani curl ani wget není nainstalovaný.")
            print("    Nainstaluj Chrome ručně:")
            print("    sudo apt-get update && sudo apt-get install -y wget")
            downloader = None

        if downloader:
            deb_url = "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
            deb_file = "google-chrome-stable_current_amd64.deb"

            print(f"[>] {downloader} {deb_url}")
            os.system(f"{downloader} {deb_url}")

            print(f"[>] {sudo}apt-get update")
            os.system(f"{sudo}apt-get update")

            print(f"[>] {sudo}apt-get install -y ./{deb_file}")
            os.system(f"{sudo}apt-get install -y ./{deb_file}")

            # Doinstalovat závislosti, pokud chybí
            print(f"[>] {sudo}apt-get install -f -y")
            os.system(f"{sudo}apt-get install -f -y")

            # Uklidit
            if os.path.exists(deb_file):
                os.remove(deb_file)

            if os.path.exists("/usr/bin/google-chrome") or os.path.exists("/usr/bin/google-chrome-stable"):
                print("[*] Google Chrome nainstalován.")
            else:
                print("[!] Instalace Chrome se nepovedla, zkontroluj výstup výše.")

# ============================================================
# Kontrola, že vše funguje
# ============================================================
print("\n[*] Kontroluji importy...")
missing = []
try:
    import requests
except ImportError:
    missing.append("requests")
try:
    import cloudscraper
except ImportError:
    missing.append("cloudscraper")
try:
    import socks
except ImportError:
    missing.append("pysocks")
try:
    import colorama
except ImportError:
    missing.append("colorama")
try:
    import undetected_chromedriver
except ImportError:
    missing.append("undetected-chromedriver")
try:
    import httpx
    # Ověřit HTTP/2 podporu
    try:
        import h2  # noqa
    except ImportError:
        missing.append("httpx[http2] (h2 chybí)")
except ImportError:
    missing.append("httpx")

if missing:
    print("\n[!] Chybí následující balíčky:")
    for m in missing:
        print(f"    - {m}")
    print(f"\n    Doinstaluj je ručně: {pip} install <balíček>")
else:
    print("[*] Všechny balíčky OK.")

print("\nDone.\n")