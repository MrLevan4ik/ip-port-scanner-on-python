import os
import sys
import time
import json
import socket
import argparse
import logging
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
# Логирование ошибок
# ---------------------------------------------------------------------------
ERROR_LOG_DIR = "logs"
ERROR_LOG_FILE = os.path.join(ERROR_LOG_DIR, "error.log")
ERROR_THRESHOLD = 10  # порог, после которого предлагаем открыть лог

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
    error_logger.error("%s — %s: %s", proxy_addr, type(exception).__name__, exception)


def offer_open_log(error_count: int):
    """Если ошибок много — предлагаем открыть лог-файл одной клавишей."""
    if error_count < ERROR_THRESHOLD:
        return
    print(f"\n⚠️  За сканирование произошло {error_count} ошибок.")
    print(f"   Лог-файл: {os.path.abspath(ERROR_LOG_FILE)}")
    try:
        choice = input("   Открыть лог сейчас? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if choice in ("", "y", "д"):
        _open_file(ERROR_LOG_FILE)


def _open_file(path: str):
    """Открывает файл стандартным приложением ОС."""
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"   Не удалось открыть файл: {e}")


# ---------------------------------------------------------------------------
# Проверка прокси
# ---------------------------------------------------------------------------
def check_socks_speed(ip: str, port: int, socks_type: int, timeout: int,
                      test_url: str):
    """Проверка SOCKS4/SOCKS5 прокси с измерением скорости."""
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
    """Проверка HTTP/HTTPS прокси с измерением скорости."""
    proxy_addr = f"{protocol}://{ip}:{port}"
    proxy_type = "http" if protocol == "http" else "https"
    proxies = {"http": f"{proxy_type}://{ip}:{port}",
               "https": f"{proxy_type}://{ip}:{port}"}
    try:
        start = time.time()
        response = requests.get(
            test_url,
            proxies=proxies,
            timeout=timeout,
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
    """Проверяет прокси и возвращает результат со скоростью."""
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
        port = int(parts[1])
        protocol = parts[2].lower() if len(parts) > 2 else None

        if protocol in ("socks4", "socks5", "http", "https"):
            return (protocol, ip, port)
        elif not protocol:
            return [("socks4", ip, port), ("socks5", ip, port),
                    ("http", ip, port), ("https", ip, port)]

    return None


def read_proxies_from_file(filepath: str):
    proxies_to_check = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                result = parse_proxy_string(line)
                if result:
                    if isinstance(result, list):
                        proxies_to_check.extend(result)
                    else:
                        proxies_to_check.append(result)
    except Exception as e:
        log_error(filepath, e)
        print(f"    Ошибка чтения {filepath}: {e}")
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
# Сканирование
# ---------------------------------------------------------------------------
def scan_file(file_info: dict, timeout: int, max_workers: int,
              test_url: str, error_count: list):
    file_path = file_info["path"]
    display_name = file_info["display_name"]
    filename = file_info["filename"]

    print(f"\n  Сканирование файла: {display_name}")

    proxies_to_check = read_proxies_from_file(file_path)
    if not proxies_to_check:
        print(f"    Нет данных для проверки в {filename}")
        return []

    working = []
    checked_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                check_proxy_with_speed, proto, ip, port, timeout, test_url
            ): (proto, ip, port, display_name)
            for proto, ip, port in proxies_to_check
        }

        for future in as_completed(futures):
            proto, ip, port, _source = futures[future]
            checked_count += 1
            result = future.result()

            if result:
                result["source_file"] = display_name
                working.append(result)
                speed_info = f"{result['total_ms']}ms"
                if result.get("speed_kbps"):
                    speed_info += f", {result['speed_kbps']}KB/s"
                print(f"    [OK]  {result['proxy']} - {speed_info}")
            else:
                error_count[0] += 1
                print(f"    [--]  {proto}://{ip}:{port}")

    print(f"    Итого в {filename}: {len(working)}/{checked_count} работающих")
    return working


# ---------------------------------------------------------------------------
# Сохранение результатов
# ---------------------------------------------------------------------------
def save_all_formats(working_proxies: list, output_dir: str):
    if not working_proxies:
        print("Нет работающих прокси для сохранения")
        return

    os.makedirs(output_dir, exist_ok=True)

    sorted_by_speed = sorted(working_proxies, key=lambda x: x["total_ms"])

    # 1. Все работающие прокси
    with open(os.path.join(output_dir, "1_all_working_proxies.txt"), "w",
              encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("ВСЕ РАБОТАЮЩИЕ ПРОКСИ (от быстрых к медленным)\n")
        f.write(f"Всего найдено: {len(sorted_by_speed)} прокси\n")
        f.write(f"Дата сканирования: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write("=" * 80 + "\n\n")
        for idx, p in enumerate(sorted_by_speed, 1):
            speed_info = f"{p['total_ms']}ms"
            if p.get("speed_kbps"):
                speed_info += f" ({p['speed_kbps']} KB/s)"
            f.write(f"{idx:3}. {p['proxy']:<45} | {speed_info:<20} "
                    f"| {p.get('source_file', 'unknown')}\n")

    # 2. Формат для повторного использования
    with open(os.path.join(output_dir, "2_proxies_for_reuse.txt"), "w",
              encoding="utf-8") as f:
        f.write("# Работающие прокси в формате protocol://ip:port\n")
        f.write(f"# Всего: {len(sorted_by_speed)} прокси\n")
        f.write(f"# Создан: {datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
        for p in sorted_by_speed:
            f.write(f"{p['proxy']}\n")

    # 3. Только ip:port
    with open(os.path.join(output_dir, "3_ips_only.txt"), "w",
              encoding="utf-8") as f:
        f.write("# IP:PORT без протокола (уникальные адреса)\n")
        f.write(f"# Всего: {len(sorted_by_speed)} адресов\n\n")
        seen = set()
        for p in sorted_by_speed:
            addr = f"{p['ip']}:{p['port']}"
            if addr not in seen:
                seen.add(addr)
                f.write(f"{addr}\n")

    # 4. Отдельные файлы по протоколам
    protocols = ["socks4", "socks5", "http", "https"]
    for protocol in protocols:
        filtered = [p for p in sorted_by_speed if p["protocol"] == protocol]
        if filtered:
            fname = os.path.join(output_dir, f"4_{protocol}_proxies.txt")
            with open(fname, "w", encoding="utf-8") as f:
                f.write(f"# {protocol.upper()} ПРОКСИ (работающие)\n")
                f.write(f"# Всего: {len(filtered)} прокси\n")
                f.write(f"# Создан: {datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
                for p in filtered:
                    speed_info = f"{p['total_ms']}ms"
                    if p.get("speed_kbps"):
                        speed_info += f", {p['speed_kbps']}KB/s"
                    f.write(f"{p['proxy']:<45}  # {speed_info}\n")
            print(f"    Сохранён {os.path.basename(fname)} ({len(filtered)} прокси)")

    # 5. CSV
    with open(os.path.join(output_dir, "5_proxies_analysis.csv"), "w",
              encoding="utf-8") as f:
        f.write("protocol,ip,port,response_ms,speed_kbps,source_file\n")
        for p in sorted_by_speed:
            f.write(f"{p['protocol']},{p['ip']},{p['port']},{p['total_ms']},"
                    f"{p.get('speed_kbps', '')},{p.get('source_file', 'unknown')}\n")

    # 6. JSON
    json_data = [
        {
            "protocol": p["protocol"], "ip": p["ip"], "port": p["port"],
            "response_ms": p["total_ms"], "speed_kbps": p.get("speed_kbps"),
            "source": p.get("source_file"),
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
            print(f"    {protocol.upper()}: {count} прокси, "
                  f"средняя скорость: {avg:.1f}ms")

    fast = [p for p in sorted_by_speed if p["total_ms"] < 500]
    medium = [p for p in sorted_by_speed if 500 <= p["total_ms"] < 1500]
    slow = [p for p in sorted_by_speed if p["total_ms"] >= 1500]

    print(f"\n  РАСПРЕДЕЛЕНИЕ ПО СКОРОСТИ:")
    print(f"    Быстрые  (<500ms):     {len(fast)}")
    print(f"    Средние  (500-1500ms): {len(medium)}")
    print(f"    Медленные (>1500ms):   {len(slow)}")

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
  python main.py                           # папка proxies/, 30 потоков
  python main.py -d my_proxies/            #своя папка с прокси
  python main.py -t 3 -w 50               #таймаут 3с, 50 потоков
  python main.py -o results/ -t 10         #результаты в results/, таймаут 10с
""",
    )
    parser.add_argument(
        "-d", "--input-dir", default="proxies",
        help="Папка со списками прокси (по умолчанию: proxies/)")
    parser.add_argument(
        "-o", "--output-dir", default=".",
        help="Папка для сохранения результатов (по умолчанию: текущая)")
    parser.add_argument(
        "-t", "--timeout", type=int, default=5,
        help="Таймаут соединения в секундах (по умолчанию: 5)")
    parser.add_argument(
        "-w", "--workers", type=int, default=30,
        help="Количество потоков (по умолчанию: 30)")
    parser.add_argument(
        "--test-url", default="http://httpbin.org/get",
        help="URL для проверки скорости (по умолчанию: http://httpbin.org/get)")
    parser.add_argument(
        "--log-errors", action="store_true", default=True,
        help="Логировать ошибки в logs/error.log (вкл. по умолчанию)")
    parser.add_argument(
        "--no-log-errors", action="store_false", dest="log_errors",
        help="Отключить логирование ошибок в файл")
    return parser


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.log_errors:
        _setup_error_log()

    base_path = args.input_dir
    if not os.path.exists(base_path):
        print(f"Папка {base_path} не найдена!")
        return

    print(f"Поиск .txt файлов в {base_path} ...")
    txt_files = find_all_txt_files(base_path)

    if not txt_files:
        print(f"Не найдено ни одного .txt файла в {base_path}!")
        return

    print(f"Найдено {len(txt_files)} .txt файлов:")
    for tf in txt_files:
        indent = "  " * tf["depth"]
        print(f"  {indent}{tf['display_name']}")

    all_working = []
    error_count = [0]

    for idx, txt_file in enumerate(txt_files, 1):
        print(f"\n{'=' * 60}")
        print(f"  Сканирование {idx}/{len(txt_files)}")
        print(f"{'=' * 60}")

        working = scan_file(
            txt_file, args.timeout, args.workers,
            args.test_url, error_count,
        )
        all_working.extend(working)

    if not all_working:
        print("\nНет работающих прокси!")
        offer_open_log(error_count[0])
        return

    print(f"\n{'=' * 60}")
    print(f"  ВСЕГО РАБОТАЮЩИХ ПРОКСИ: {len(all_working)}")
    print(f"{'=' * 60}")

    sorted_proxies = sorted(all_working, key=lambda x: x["total_ms"])

    print("\n  ТОП-10 БЫСТРЫХ ПРОКСИ:")
    print("-" * 60)
    for i, p in enumerate(sorted_proxies[:10], 1):
        speed_str = f"{p['total_ms']}ms"
        if p.get("speed_kbps"):
            speed_str += f" ({p['speed_kbps']}KB/s)"
        source_short = p.get("source_file", "unknown")[:30]
        print(f"  {i:2}. {source_short:<33} {p['proxy']:<35} - {speed_str}")

    print("\n  СОХРАНЕНИЕ РЕЗУЛЬТАТОВ:")
    stats = save_all_formats(all_working, args.output_dir)

    print(f"\n{'=' * 60}")
    print(f"  СКАНИРОВАНИЕ ЗАВЕРШЕНО!")
    print(f"{'=' * 60}")

    if stats:
        print(f"\n  ИТОГОВАЯ СТАТИСТИКА:")
        print(f"    Всего прокси: {stats['total']}")
        print(f"    Быстрые (<500ms): {stats['fast']}")
        print(f"    Средние (500-1500ms): {stats['medium']}")
        print(f"    Медленные (>1500ms): {stats['slow']}")
        for protocol, count in stats["by_protocol"].items():
            if count:
                print(f"    {protocol.upper()}: {count}")

    offer_open_log(error_count[0])


if __name__ == "__main__":
    main()
