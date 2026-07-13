import os
import sys
import re
import time
import json
import socket
import argparse
import logging
import signal
import subprocess
import platform
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import socks
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Глобальный флаг для экстренного завершения (Ctrl+C)
# ---------------------------------------------------------------------------
_shutdown_requested = False


def _signal_handler(sig, frame):
    global _shutdown_requested
    if _shutdown_requested:
        print("\n\nПринудительное завершение.\n")
        sys.exit(1)
    _shutdown_requested = True
    print("\n\nЗавершение... ожидание завершения текущих задач...\n")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ---------------------------------------------------------------------------
# Логирование ошибок
# ---------------------------------------------------------------------------
ERROR_LOG_DIR = "logs"
ERROR_LOG_FILE = os.path.join(ERROR_LOG_DIR, "error.log")
ERROR_THRESHOLD = 10

error_logger = logging.getLogger("proxy_errors")
error_logger.setLevel(logging.DEBUG)


def _setup_error_log():
    os.makedirs(ERROR_LOG_DIR, exist_ok=True)
    fh = logging.FileHandler(ERROR_LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    error_logger.addHandler(fh)


def log_error(proxy_addr: str, exception: Exception):
    error_logger.error("%s — %s: %s", proxy_addr,
                       type(exception).__name__, exception)


def offer_open_log(error_count: int):
    if error_count < ERROR_THRESHOLD:
        return
    print(f"\n  За сканирование произошло {error_count} ошибок.")
    print(f"  Лог-файл: {os.path.abspath(ERROR_LOG_FILE)}")
    try:
        choice = input("  Открыть лог сейчас? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if choice in ("", "y", "д"):
        _open_file(ERROR_LOG_FILE)


def _open_file(path: str):
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"  Не удалось открыть файл: {e}")


# ---------------------------------------------------------------------------
# Валидация IP
# ---------------------------------------------------------------------------
_IPV4_RE = re.compile(
    r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
)
_IPV6_RE = re.compile(r"^([0-9a-fA-F:]+)$")


def is_valid_ip(ip: str) -> bool:
    m = _IPV4_RE.match(ip)
    if m:
        return all(0 <= int(g) <= 255 for g in m.groups())
    return bool(_IPV6_RE.match(ip))


# ---------------------------------------------------------------------------
# Скачивание прокси-листов
# ---------------------------------------------------------------------------
PUBLIC_PROXY_URLS = [
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
]


def fetch_proxy_lists(output_dir: str, urls: list = None):
    """Скачивает публичные прокси-листы и сохраняет в output_dir."""
    urls = urls or PUBLIC_PROXY_URLS
    os.makedirs(output_dir, exist_ok=True)
    downloaded = []
    for url in urls:
        filename = url.rsplit("/", 1)[-1]
        filepath = os.path.join(output_dir, filename)
        print(f"  Скачивание {url} ...")
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(resp.text)
            count = len(resp.text.strip().splitlines())
            print(f"    Сохранён {filename} ({count} строк)")
            downloaded.append(filepath)
        except Exception as e:
            print(f"    Ошибка скачивания {filename}: {e}")
            log_error(url, e)
    return downloaded


# ---------------------------------------------------------------------------
# Геолокация
# ---------------------------------------------------------------------------
_geo_cache: dict = {}


def lookup_country(ip: str) -> str:
    """Определяет страну по IP через бесплатный API."""
    if ip in _geo_cache:
        return _geo_cache[ip]
    try:
        resp = requests.get(f"http://ip-api.com/json/{ip}?fields=country",
                            timeout=5)
        data = resp.json()
        country = data.get("country", "Unknown")
    except Exception:
        country = "Unknown"
    _geo_cache[ip] = country
    return country


# ---------------------------------------------------------------------------
# Проверка прокси
# ---------------------------------------------------------------------------
def check_socks_speed(ip: str, port: int, socks_type: int, timeout: int,
                      test_url: str):
    proxy_name = f"socks{'4' if socks_type == socks.SOCKS4 else '5'}://{ip}:{port}"
    try:
        s = socks.socksocket()
        s.set_proxy(socks_type, ip, port)
        s.settimeout(timeout)

        parsed = urlparse(test_url)
        host = parsed.hostname or "httpbin.org"
        port_target = parsed.port or 80

        start = time.time()
        s.connect((host, port_target))
        connect_time = (time.time() - start) * 1000

        s.send(f"GET /get HTTP/1.0\r\nHost: {host}\r\n\r\n".encode())
        data = s.recv(4096)
        total_time = (time.time() - start) * 1000
        s.close()

        if b"origin" in data or b"200 OK" in data:
            return total_time, connect_time
    except Exception as e:
        log_error(proxy_name, e)
    return None, None


def check_http_speed(ip: str, port: int, protocol: str, timeout: int,
                     test_url: str):
    proxy_addr = f"{protocol}://{ip}:{port}"
    proxy_type = "http" if protocol == "http" else "https"
    proxies = {"http": f"{proxy_type}://{ip}:{port}",
               "https": f"{proxy_type}://{ip}:{port}"}
    try:
        start = time.time()
        response = requests.get(
            test_url, proxies=proxies, timeout=timeout,
            verify=False if protocol == "https" else True,
        )
        total_time = (time.time() - start) * 1000
        if response.status_code == 200:
            content_size = len(response.content) / 1024
            speed_kbps = (content_size / (total_time / 1000)) if total_time > 0 else 0
            return total_time, speed_kbps
    except Exception as e:
        log_error(proxy_addr, e)
    return None, None


def check_proxy_with_speed(protocol: str, ip: str, port: int, timeout: int,
                           test_url: str):
    proxy_addr = f"{protocol}://{ip}:{port}"

    if protocol == "socks4":
        total_time, connect_time = check_socks_speed(
            ip, port, socks.SOCKS4, timeout, test_url)
        if total_time:
            return {
                "proxy": proxy_addr, "protocol": protocol, "ip": ip,
                "port": port, "alive": True, "total_ms": round(total_time, 2),
                "connect_ms": round(connect_time, 2) if connect_time else None,
                "speed_kbps": None,
            }

    elif protocol == "socks5":
        total_time, connect_time = check_socks_speed(
            ip, port, socks.SOCKS5, timeout, test_url)
        if total_time:
            return {
                "proxy": proxy_addr, "protocol": protocol, "ip": ip,
                "port": port, "alive": True, "total_ms": round(total_time, 2),
                "connect_ms": round(connect_time, 2) if connect_time else None,
                "speed_kbps": None,
            }

    elif protocol in ("http", "https"):
        total_time, speed = check_http_speed(ip, port, protocol, timeout, test_url)
        if total_time:
            return {
                "proxy": proxy_addr, "protocol": protocol, "ip": ip,
                "port": port, "alive": True, "total_ms": round(total_time, 2),
                "connect_ms": None,
                "speed_kbps": round(speed, 2) if speed else None,
            }

    return None


# ---------------------------------------------------------------------------
# Парсинг входных данных
# ---------------------------------------------------------------------------
def parse_proxy_string(line: str):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    if "://" in line:
        parsed = urlparse(line)
        protocol = parsed.scheme.lower()
        ip = parsed.hostname
        port = parsed.port
        if protocol in ("socks4", "socks5", "http", "https") and ip and port:
            return (protocol, ip, port)

    parts = line.replace(" ", ":").split(":")
    if len(parts) >= 2:
        ip = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            return None
        protocol = parts[2].lower() if len(parts) > 2 else None

        if protocol in ("socks4", "socks5", "http", "https"):
            return (protocol, ip, port)
        elif not protocol:
            return [("socks4", ip, port), ("socks5", ip, port),
                    ("http", ip, port), ("https", ip, port)]

    return None


def read_proxies_from_file(filepath: str, validate_ip: bool = False):
    proxies_to_check = []
    skipped = 0
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                result = parse_proxy_string(line)
                if result:
                    if isinstance(result, list):
                        if validate_ip:
                            result = [(p, ip, pt) for p, ip, pt in result
                                      if is_valid_ip(ip)]
                        proxies_to_check.extend(result)
                    else:
                        protocol, ip, port = result
                        if validate_ip and not is_valid_ip(ip):
                            skipped += 1
                            continue
                        proxies_to_check.append(result)
    except Exception as e:
        log_error(filepath, e)
        print(f"    Ошибка чтения {filepath}: {e}")
    if skipped:
        print(f"    Пропущено {skipped} записей с невалидным IP")
    return proxies_to_check


def find_all_txt_files(base_path: str):
    txt_files = []
    for root, _dirs, files in os.walk(base_path):
        for file in files:
            if file.lower().endswith(".txt"):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(root, base_path)
                display_name = base_path if rel_path == "." else rel_path
                txt_files.append({
                    "path": file_path,
                    "directory": root,
                    "filename": file,
                    "display_name": os.path.join(display_name, file),
                    "depth": root.count(os.sep) - base_path.count(os.sep),
                })
    return txt_files


# ---------------------------------------------------------------------------
# Прогресс-бар
# ---------------------------------------------------------------------------
class ProgressTracker:
    def __init__(self, total: int, label: str = ""):
        self.total = total
        self.done = 0
        self.found = 0
        self.label = label
        self.start_time = time.time()

    def update(self, success: bool = False):
        self.done += 1
        if success:
            self.found += 1
        self._draw()

    def _draw(self):
        if self.total == 0:
            return
        pct = self.done / self.total * 100
        elapsed = time.time() - self.start_time
        rate = self.done / elapsed if elapsed > 0 else 0
        eta = (self.total - self.done) / rate if rate > 0 else 0
        bar_len = 30
        filled = int(bar_len * self.done / self.total)
        bar = "=" * filled + "-" * (bar_len - filled)
        sys.stdout.write(
            f"\r  [{bar}] {pct:5.1f}%  "
            f"{self.done}/{self.total}  "
            f"ok={self.found}  "
            f"{elapsed:.0f}s elapsed  "
            f"ETA {eta:.0f}s  "
        )
        sys.stdout.flush()

    def finish(self):
        elapsed = time.time() - self.start_time
        sys.stdout.write(f"\r{'':70}\r")
        sys.stdout.flush()
        return elapsed


# ---------------------------------------------------------------------------
# Сканирование одного прокси с ретраями
# ---------------------------------------------------------------------------
def check_proxy_with_retry(protocol: str, ip: str, port: int, timeout: int,
                           test_url: str, retries: int):
    """Проверяет прокси, при неудаче повторяет до retries раз."""
    for attempt in range(1, retries + 1):
        result = check_proxy_with_speed(protocol, ip, port, timeout, test_url)
        if result:
            return result
        if attempt < retries:
            time.sleep(0.3)
    return None


# ---------------------------------------------------------------------------
# Сканирование файла
# ---------------------------------------------------------------------------
def scan_file(file_info: dict, timeout: int, max_workers: int,
              test_url: str, error_count: list, retries: int = 1,
              progress: ProgressTracker = None, min_speed: float = None,
              validate_ip: bool = False):
    file_path = file_info["path"]
    display_name = file_info["display_name"]
    filename = file_info["filename"]

    print(f"\n  Файл: {display_name}")

    proxies_to_check = read_proxies_from_file(file_path, validate_ip)
    if not proxies_to_check:
        print(f"    Нет данных для проверки в {filename}")
        return []

    working = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                check_proxy_with_retry, proto, ip, port, timeout,
                test_url, retries
            ): (proto, ip, port, display_name)
            for proto, ip, port in proxies_to_check
        }

        for future in as_completed(futures):
            if _shutdown_requested:
                executor.shutdown(wait=False, cancel_futures=True)
                break

            proto, ip, port, _source = futures[future]
            result = future.result()

            if result:
                # Фильтр по минимальной скорости (макс. задержка)
                if min_speed and result["total_ms"] > min_speed:
                    if progress:
                        progress.update(False)
                    continue
                result["source_file"] = display_name
                working.append(result)
                if progress:
                    progress.update(True)
                else:
                    speed_info = f"{result['total_ms']}ms"
                    if result.get("speed_kbps"):
                        speed_info += f", {result['speed_kbps']}KB/s"
                    print(f"    [OK]  {result['proxy']} - {speed_info}")
            else:
                error_count[0] += 1
                if progress:
                    progress.update(False)
                else:
                    print(f"    [--]  {proto}://{ip}:{port}")

    print(f"    Итого: {len(working)}/{len(proxies_to_check)}")
    return working


# ---------------------------------------------------------------------------
# Сохранение результатов
# ---------------------------------------------------------------------------
def save_all_formats(working_proxies: list, output_dir: str,
                     add_geo: bool = False):
    if not working_proxies:
        print("Нет работающих прокси для сохранения")
        return

    os.makedirs(output_dir, exist_ok=True)

    # Геолокация если включена
    if add_geo:
        print("  Определение стран...")
        for p in working_proxies:
            p["country"] = lookup_country(p["ip"])
            time.sleep(0.15)  # лимит free API

    sorted_by_speed = sorted(working_proxies, key=lambda x: x["total_ms"])

    geo_note = " + страна" if add_geo else ""

    # 1. Все работающие прокси
    with open(os.path.join(output_dir, "1_all_working_proxies.txt"), "w",
              encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("ВСЕ РАБОТАЮЩИЕ ПРОКСИ (от быстрых к медленным)\n")
        f.write(f"Всего найдено: {len(sorted_by_speed)} прокси\n")
        f.write(f"Дата: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write("=" * 80 + "\n\n")
        for idx, p in enumerate(sorted_by_speed, 1):
            speed_info = f"{p['total_ms']}ms"
            if p.get("speed_kbps"):
                speed_info += f" ({p['speed_kbps']} KB/s)"
            geo = f" | {p.get('country', '')}" if add_geo else ""
            f.write(f"{idx:3}. {p['proxy']:<45} | {speed_info:<20}"
                    f"{geo} | {p.get('source_file', '')}\n")

    # 2. Для повторного использования
    with open(os.path.join(output_dir, "2_proxies_for_reuse.txt"), "w",
              encoding="utf-8") as f:
        f.write("# Работающие прокси protocol://ip:port\n")
        f.write(f"# Всего: {len(sorted_by_speed)} прокси\n")
        f.write(f"# Создан: {datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
        for p in sorted_by_speed:
            f.write(f"{p['proxy']}\n")

    # 3. Только ip:port
    with open(os.path.join(output_dir, "3_ips_only.txt"), "w",
              encoding="utf-8") as f:
        f.write("# IP:PORT без протокола (уникальные)\n")
        f.write(f"# Всего: {len(sorted_by_speed)} адресов\n\n")
        seen = set()
        for p in sorted_by_speed:
            addr = f"{p['ip']}:{p['port']}"
            if addr not in seen:
                seen.add(addr)
                f.write(f"{addr}\n")

    # 4. По протоколам
    protocols = ["socks4", "socks5", "http", "https"]
    for protocol in protocols:
        filtered = [p for p in sorted_by_speed if p["protocol"] == protocol]
        if filtered:
            fname = os.path.join(output_dir, f"4_{protocol}_proxies.txt")
            with open(fname, "w", encoding="utf-8") as f:
                f.write(f"# {protocol.upper()} ПРОКСИ\n")
                f.write(f"# Всего: {len(filtered)}\n")
                f.write(f"# Создан: {datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
                for p in filtered:
                    speed_info = f"{p['total_ms']}ms"
                    if p.get("speed_kbps"):
                        speed_info += f", {p['speed_kbps']}KB/s"
                    geo = f" [{p.get('country', '')}]" if add_geo else ""
                    f.write(f"{p['proxy']:<45}  # {speed_info}{geo}\n")
            print(f"    {os.path.basename(fname)} ({len(filtered)})")

    # 5. CSV
    with open(os.path.join(output_dir, "5_proxies_analysis.csv"), "w",
              encoding="utf-8") as f:
        header = "protocol,ip,port,response_ms,speed_kbps,country,source_file\n"
        f.write(header)
        for p in sorted_by_speed:
            geo = p.get("country", "")
            f.write(f"{p['protocol']},{p['ip']},{p['port']},{p['total_ms']},"
                    f"{p.get('speed_kbps', '')},{geo},"
                    f"{p.get('source_file', '')}\n")

    # 6. JSON
    json_data = [
        {
            "protocol": p["protocol"], "ip": p["ip"], "port": p["port"],
            "response_ms": p["total_ms"], "speed_kbps": p.get("speed_kbps"),
            "country": p.get("country"), "source": p.get("source_file"),
        }
        for p in sorted_by_speed
    ]
    with open(os.path.join(output_dir, "6_proxies.json"), "w",
              encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    # Статистика
    print(f"\n  СТАТИСТИКА ПО ПРОТОКОЛАМ:")
    for protocol in protocols:
        count = len([p for p in sorted_by_speed if p["protocol"] == protocol])
        if count:
            avg = sum(p["total_ms"] for p in sorted_by_speed
                      if p["protocol"] == protocol) / count
            print(f"    {protocol.upper()}: {count}, "
                  f"средняя: {avg:.1f}ms")

    fast = [p for p in sorted_by_speed if p["total_ms"] < 500]
    medium = [p for p in sorted_by_speed if 500 <= p["total_ms"] < 1500]
    slow = [p for p in sorted_by_speed if p["total_ms"] >= 1500]

    print(f"\n  ПО СКОРОСТИ:")
    print(f"    Быстрые  (<500ms):     {len(fast)}")
    print(f"    Средние  (500-1500ms): {len(medium)}")
    print(f"    Медленные (>1500ms):   {len(slow)}")

    if add_geo:
        countries = {}
        for p in sorted_by_speed:
            c = p.get("country", "Unknown")
            countries[c] = countries.get(c, 0) + 1
        print(f"\n  ПО СТРАНАМ:")
        for c, n in sorted(countries.items(), key=lambda x: -x[1])[:10]:
            print(f"    {c}: {n}")

    return {
        "total": len(sorted_by_speed),
        "fast": len(fast),
        "medium": len(medium),
        "slow": len(slow),
        "by_protocol": {p: len([x for x in sorted_by_speed
                                if x["protocol"] == p]) for p in protocols},
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Сканер прокси с проверкой работоспособности и скорости.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Примеры:
  python main.py                               # базовый запуск
  python main.py -d my_proxies/ -t 3 -w 50    # свои настройки
  python main.py --fetch                       # скачать прокси-листы
  python main.py --watch 300                   # проверка каждые 5 минут
  python main.py --geo --min-speed 1000        # только быстрые + страны
""",
    )

    # Основные
    g = parser.add_argument_group("Основные")
    g.add_argument("-d", "--input-dir", default="proxies",
                   help="Папка со списками прокси (по умолчанию: proxies/)")
    g.add_argument("-o", "--output-dir", default=".",
                   help="Папка для результатов (по умолчанию: текущая)")
    g.add_argument("-t", "--timeout", type=int, default=5,
                   help="Таймаут соединения, сек (по умолчанию: 5)")
    g.add_argument("-w", "--workers", type=int, default=30,
                   help="Количество потоков (по умолчанию: 30)")
    g.add_argument("--test-url", default="http://httpbin.org/get",
                   help="URL для проверки скорости")

    # Опциональные фичи
    g2 = parser.add_argument_group("Опциональные фичи")
    g2.add_argument("--progress", action="store_true",
                    help="Показывать прогресс-бар вместо каждого прокси")
    g2.add_argument("--retry", type=int, default=1, metavar="N",
                    help="Повторять проверку N раз при неудаче (по умолчанию: 1)")
    g2.add_argument("--min-speed", type=float, default=None, metavar="MS",
                    help="Максимальная задержка в мс (отбросить медленнее)")
    g2.add_argument("--limit", type=int, default=None, metavar="N",
                    help="Ограничить количество проверяемых прокси")
    g2.add_argument("--parallel-files", type=int, default=1, metavar="N",
                    help="Сканировать N файлов параллельно (по умолчанию: 1)")
    g2.add_argument("--validate-ip", action="store_true",
                    help="Проверять формат IP перед подключением")
    g2.add_argument("--geo", action="store_true",
                    help="Определять страну прокси (бесплатный API)")
    g2.add_argument("--fetch", action="store_true",
                    help="Скачать публичные прокси-листы перед сканированием")
    g2.add_argument("--fetch-urls", nargs="+", metavar="URL",
                   help="Доп. URLs для скачивания прокси-листов")
    g2.add_argument("--watch", type=int, default=None, metavar="SEC",
                    help="Повторять сканирование каждые N секунд")

    # Логирование
    g3 = parser.add_argument_group("Логирование")
    g3.add_argument("--no-log-errors", action="store_true",
                    help="Отключить логирование ошибок в файл")

    return parser


# ---------------------------------------------------------------------------
# Один цикл сканирования
# ---------------------------------------------------------------------------
def run_scan(args):
    base_path = args.input_dir

    # Скачивание если нужно
    if args.fetch:
        print("\n  СКАЧИВАНИЕ ПРОКСИ-ЛИСТОВ:")
        fetch_proxy_lists(base_path, args.fetch_urls)
        print()

    if not os.path.exists(base_path):
        print(f"Папка {base_path} не найдена!")
        return None

    print(f"  Поиск .txt файлов в {base_path} ...")
    txt_files = find_all_txt_files(base_path)

    if not txt_files:
        print(f"  Не найдено .txt файлов в {base_path}!")
        return None

    print(f"  Найдено {len(txt_files)} файлов:")
    for tf in txt_files:
        indent = "  " * tf["depth"]
        print(f"    {indent}{tf['display_name']}")

    all_working = []
    error_count = [0]

    # Подсчёт общего количества прокси для прогресс-бара
    total_proxies = 0
    if args.progress:
        for tf in txt_files:
            proxies = read_proxies_from_file(tf["path"], args.validate_ip)
            total_proxies += len(proxies)
            if args.limit and total_proxies >= args.limit:
                total_proxies = args.limit
                break
        progress = ProgressTracker(total_proxies, "Сканирование")
    else:
        progress = None

    def _scan_one(txt_file):
        return scan_file(
            txt_file, args.timeout, args.workers, args.test_url,
            error_count, args.retry, progress,
            args.min_speed, args.validate_ip,
        )

    if args.parallel_files > 1 and len(txt_files) > 1:
        with ThreadPoolExecutor(max_workers=args.parallel_files) as ex:
            futures = {ex.submit(_scan_one, tf): tf for tf in txt_files}
            for future in as_completed(futures):
                if _shutdown_requested:
                    break
                all_working.extend(future.result())
    else:
        for txt_file in txt_files:
            if _shutdown_requested:
                break
            all_working.extend(_scan_one(txt_file))

    if progress:
        elapsed = progress.finish()
        print(f"  Сканирование заняло {elapsed:.1f}с")

    # Лимит
    if args.limit and len(all_working) > args.limit:
        all_working = sorted(all_working, key=lambda x: x["total_ms"])
        all_working = all_working[:args.limit]
        print(f"\n  Ограничено до {args.limit} прокси (--limit)")

    offer_open_log(error_count[0])

    return all_working


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.no_log_errors:
        _setup_error_log()

    print("=" * 60)
    print("  PROXY SCANNER")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    while True:
        all_working = run_scan(args)

        if all_working:
            print(f"\n  ВСЕГО РАБОТАЮЩИХ ПРОКСИ: {len(all_working)}")

            sorted_proxies = sorted(all_working, key=lambda x: x["total_ms"])

            print("\n  ТОП-10 БЫСТРЫХ:")
            print("-" * 60)
            for i, p in enumerate(sorted_proxies[:10], 1):
                speed_str = f"{p['total_ms']}ms"
                if p.get("speed_kbps"):
                    speed_str += f" ({p['speed_kbps']}KB/s)"
                src = p.get("source_file", "")[:25]
                print(f"  {i:2}. {src:<28} {p['proxy']:<35} {speed_str}")

            print("\n  СОХРАНЕНИЕ:")
            stats = save_all_formats(all_working, args.output_dir, args.geo)

            print(f"\n{'=' * 60}")
            print(f"  СКАНИРОВАНИЕ ЗАВЕРШЕНО!")
            print(f"{'=' * 60}")

            if stats:
                print(f"\n  ИТОГО:")
                print(f"    Всего: {stats['total']}")
                print(f"    Быстрые (<500ms): {stats['fast']}")
                print(f"    Средние (500-1500ms): {stats['medium']}")
                print(f"    Медленные (>1500ms): {stats['slow']}")
                for protocol, count in stats["by_protocol"].items():
                    if count:
                        print(f"    {protocol.upper()}: {count}")
        else:
            print("\n  Нет работающих прокси!")

        # Watch mode
        if args.watch and not _shutdown_requested:
            print(f"\n  Следующая проверка через {args.watch}с "
                  f"(Ctrl+C для выхода)...")
            try:
                for _ in range(args.watch):
                    if _shutdown_requested:
                        break
                    time.sleep(1)
            except KeyboardInterrupt:
                break
            if _shutdown_requested:
                break
            print(f"\n{'=' * 60}")
            print(f"  ПОВТОРНОЕ СКАНИРОВАНИЕ")
            print(f"{'=' * 60}")
        else:
            break


if __name__ == "__main__":
    main()
