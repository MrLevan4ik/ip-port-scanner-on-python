import os
import time
import socket
import socks
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

# Настройки
TIMEOUT = 5
MAX_WORKERS = 30
SPEED_TEST_URL = "http://httpbin.org/get"

def check_socks4_speed(ip, port):
    """Проверка SOCKS4 прокси с измерением скорости"""
    try:
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS4, ip, port)
        s.settimeout(TIMEOUT)
        
        start = time.time()
        s.connect(("httpbin.org", 80))
        connect_time = (time.time() - start) * 1000
        
        s.send(b"GET /get HTTP/1.0\r\nHost: httpbin.org\r\n\r\n")
        data = s.recv(4096)
        total_time = (time.time() - start) * 1000
        s.close()
        
        if b"origin" in data or b"200 OK" in data:
            return total_time, connect_time
    except:
        pass
    return None, None

def check_socks5_speed(ip, port):
    """Проверка SOCKS5 прокси с измерением скорости"""
    try:
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, ip, port)
        s.settimeout(TIMEOUT)
        
        start = time.time()
        s.connect(("httpbin.org", 80))
        connect_time = (time.time() - start) * 1000
        
        s.send(b"GET /get HTTP/1.0\r\nHost: httpbin.org\r\n\r\n")
        data = s.recv(4096)
        total_time = (time.time() - start) * 1000
        s.close()
        
        if b"origin" in data or b"200 OK" in data:
            return total_time, connect_time
    except:
        pass
    return None, None

def check_http_speed(ip, port, protocol='http'):
    """Проверка HTTP/HTTPS прокси с измерением скорости"""
    proxy_type = 'http' if protocol == 'http' else 'https'
    proxies = {
        'http': f'{proxy_type}://{ip}:{port}',
        'https': f'{proxy_type}://{ip}:{port}'
    }
    
    try:
        start = time.time()
        response = requests.get(
            SPEED_TEST_URL, 
            proxies=proxies, 
            timeout=TIMEOUT,
            verify=False if protocol == 'https' else True
        )
        total_time = (time.time() - start) * 1000
        
        if response.status_code == 200:
            content_size = len(response.content) / 1024
            speed_kbps = (content_size / (total_time / 1000)) if total_time > 0 else 0
            return total_time, speed_kbps
    except:
        pass
    return None, None

def check_proxy_with_speed(protocol, ip, port):
    """Проверяет прокси и возвращает результат со скоростью"""
    if protocol == 'socks4':
        total_time, connect_time = check_socks4_speed(ip, port)
        if total_time:
            return {
                'proxy': f"{protocol}://{ip}:{port}",
                'protocol': protocol,
                'ip': ip,
                'port': port,
                'alive': True,
                'total_ms': round(total_time, 2),
                'connect_ms': round(connect_time, 2) if connect_time else None,
                'speed_kbps': None
            }
    
    elif protocol == 'socks5':
        total_time, connect_time = check_socks5_speed(ip, port)
        if total_time:
            return {
                'proxy': f"{protocol}://{ip}:{port}",
                'protocol': protocol,
                'ip': ip,
                'port': port,
                'alive': True,
                'total_ms': round(total_time, 2),
                'connect_ms': round(connect_time, 2) if connect_time else None,
                'speed_kbps': None
            }
    
    elif protocol in ['http', 'https']:
        total_time, speed = check_http_speed(ip, port, protocol)
        if total_time:
            return {
                'proxy': f"{protocol}://{ip}:{port}",
                'protocol': protocol,
                'ip': ip,
                'port': port,
                'alive': True,
                'total_ms': round(total_time, 2),
                'connect_ms': None,
                'speed_kbps': round(speed, 2) if speed else None
            }
    
    return None

def parse_proxy_string(line):
    """Разбор строки с прокси"""
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    
    # Формат: protocol://ip:port
    if '://' in line:
        parsed = urlparse(line)
        protocol = parsed.scheme.lower()
        ip = parsed.hostname
        port = parsed.port
        if protocol in ['socks4', 'socks5', 'http', 'https'] and ip and port:
            return (protocol, ip, port)
    
    # Формат: ip:port:protocol
    parts = line.replace(' ', ':').split(':')
    if len(parts) >= 2:
        ip = parts[0]
        port = int(parts[1])
        protocol = parts[2].lower() if len(parts) > 2 else None
        
        if protocol and protocol in ['socks4', 'socks5', 'http', 'https']:
            return (protocol, ip, port)
        elif not protocol:
            return [('socks4', ip, port), ('socks5', ip, port), ('http', ip, port), ('https', ip, port)]
    
    return None

def read_proxies_from_file(filepath):
    """Читает прокси из любого .txt файла"""
    proxies_to_check = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                result = parse_proxy_string(line)
                if result:
                    if isinstance(result, list):
                        proxies_to_check.extend(result)
                    else:
                        proxies_to_check.append(result)
    except Exception as e:
        print(f"    ❌ Ошибка чтения {filepath}: {e}")
    return proxies_to_check

def find_all_txt_files(base_path):
    """Рекурсивно находит ВСЕ файлы с расширением .txt во всех вложенных папках"""
    txt_files = []
    
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.lower().endswith('.txt'):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(root, base_path)
                if rel_path == '.':
                    display_name = base_path
                else:
                    display_name = rel_path
                
                txt_files.append({
                    'path': file_path,
                    'directory': root,
                    'filename': file,
                    'display_name': os.path.join(display_name, file),
                    'depth': root.count(os.sep) - base_path.count(os.sep)
                })
    
    return txt_files

def scan_file(file_info):
    """Сканирует один .txt файл с проверкой скорости"""
    file_path = file_info['path']
    display_name = file_info['display_name']
    filename = file_info['filename']
    
    print(f"\n📄 Сканирование файла: {display_name}")
    
    proxies_to_check = read_proxies_from_file(file_path)
    
    if not proxies_to_check:
        print(f"   ⚠️ Нет данных для проверки в {filename}")
        return []
    
    working = []
    checked_count = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(check_proxy_with_speed, proto, ip, port): (proto, ip, port, display_name) 
                   for proto, ip, port in proxies_to_check}
        
        for future in as_completed(futures):
            proto, ip, port, source = futures[future]
            checked_count += 1
            result = future.result()
            
            if result:
                result['source_file'] = source
                working.append(result)
                speed_info = f"{result['total_ms']}ms"
                if result.get('speed_kbps'):
                    speed_info += f", {result['speed_kbps']}KB/s"
                print(f"   ✅ {result['proxy']} - {speed_info}")
            else:
                print(f"   ❌ {proto}://{ip}:{port}")
    
    print(f"   📊 Итого в {filename}: {len(working)}/{checked_count} работающих")
    return working

def save_all_formats(working_proxies):
    """Сохраняет результаты во всех требуемых форматах"""
    if not working_proxies:
        print("❌ Нет работающих прокси для сохранения")
        return
    
    # Сортировка по скорости (от быстрого к медленному)
    sorted_by_speed = sorted(working_proxies, key=lambda x: x['total_ms'])
    
    # 1. Общий файл со всеми работающими прокси с сортировкой по скорости
    with open('1_all_working_proxies.txt', 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("ВСЕ РАБОТАЮЩИЕ ПРОКСИ (от быстрых к медленным)\n")
        f.write(f"Всего найдено: {len(sorted_by_speed)} прокси\n")
        f.write(f"Дата сканирования: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")
        
        for idx, p in enumerate(sorted_by_speed, 1):
            speed_info = f"{p['total_ms']}ms"
            if p.get('speed_kbps'):
                speed_info += f" ({p['speed_kbps']} KB/s)"
            
            f.write(f"{idx:3}. {p['proxy']:<45} | {speed_info:<20} | {p.get('source_file', 'unknown')}\n")
    
    # 2. Файл для дальнейшего использования (привычный формат - protocol://ip:port)
    with open('2_proxies_for_reuse.txt', 'w', encoding='utf-8') as f:
        f.write("# Работающие прокси в формате protocol://ip:port\n")
        f.write(f"# Всего: {len(sorted_by_speed)} прокси\n")
        f.write(f"# Создан: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("# Скорость указана в миллисекундах\n\n")
        
        for p in sorted_by_speed:
            if p.get('speed_kbps'):
                f.write(f"{p['proxy']}  \n")
            else:
                f.write(f"{p['proxy']}  \n")
    
    # 3. Файл со списком адресов без протокола (только ip:port)
    with open('3_ips_only.txt', 'w', encoding='utf-8') as f:
        f.write("# IP:PORT без протокола (уникальные адреса)\n")
        f.write(f"# Всего: {len(sorted_by_speed)} адресов\n\n")
        
        seen = set()
        for p in sorted_by_speed:
            addr = f"{p['ip']}:{p['port']}"
            if addr not in seen:
                seen.add(addr)
                f.write(f"{addr}\n")
    
    # 4. Отдельные файлы под каждый вид прокси
    protocols = ['socks4', 'socks5', 'http', 'https']
    for protocol in protocols:
        filtered = [p for p in sorted_by_speed if p['protocol'] == protocol]
        if filtered:
            filename = f'4_{protocol}_proxies.txt'
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"# {protocol.upper()} ПРОКСИ (работающие)\n")
                f.write(f"# Всего: {len(filtered)} прокси\n")
                f.write(f"# Создан: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                for idx, p in enumerate(filtered, 1):
                    speed_info = f"{p['total_ms']}ms"
                    if p.get('speed_kbps'):
                        speed_info += f", {p['speed_kbps']}KB/s"
                    f.write(f"{p['proxy']:<45}  # {speed_info}\n")
            
            print(f"   ✅ Сохранён {filename} ({len(filtered)} прокси)")
    
    # 5. Дополнительно: CSV файл для Excel
    with open('5_proxies_analysis.csv', 'w', encoding='utf-8') as f:
        f.write("protocol,ip,port,response_ms,speed_kbps,source_file\n")
        for p in sorted_by_speed:
            f.write(f"{p['protocol']},{p['ip']},{p['port']},{p['total_ms']},{p.get('speed_kbps', '')},{p.get('source_file', 'unknown')}\n")
    
    # 6. JSON файл для программного использования
    import json
    json_data = []
    for p in sorted_by_speed:
        json_data.append({
            'protocol': p['protocol'],
            'ip': p['ip'],
            'port': p['port'],
            'response_ms': p['total_ms'],
            'speed_kbps': p.get('speed_kbps'),
            'source': p.get('source_file')
        })
    
    with open('6_proxies.json', 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    # Статистика
    print(f"\n📊 СТАТИСТИКА ПО ПРОТОКОЛАМ:")
    for protocol in protocols:
        count = len([p for p in sorted_by_speed if p['protocol'] == protocol])
        if count > 0:
            avg_speed = sum(p['total_ms'] for p in sorted_by_speed if p['protocol'] == protocol) / count
            print(f"   {protocol.upper()}: {count} прокси, средняя скорость: {avg_speed:.1f}ms")
    
    # Быстрые, средние, медленные
    fast = [p for p in sorted_by_speed if p['total_ms'] < 500]
    medium = [p for p in sorted_by_speed if 500 <= p['total_ms'] < 1500]
    slow = [p for p in sorted_by_speed if p['total_ms'] >= 1500]
    
    print(f"\n📈 РАСПРЕДЕЛЕНИЕ ПО СКОРОСТИ:")
    print(f"   ⚡ Быстрые (<500ms): {len(fast)} прокси")
    print(f"   📊 Средние (500-1500ms): {len(medium)} прокси")
    print(f"   🐢 Медленные (>1500ms): {len(slow)} прокси")
    
    return {
        'total': len(sorted_by_speed),
        'fast': len(fast),
        'medium': len(medium),
        'slow': len(slow),
        'by_protocol': {p: len([x for x in sorted_by_speed if x['protocol'] == p]) for p in protocols}
    }

def main():
    base_path = "proxies/"  # Измените на ваш путь
    
    if not os.path.exists(base_path):
        print(f"❌ Папка {base_path} не найдена!")
        return
    
    print(f"🔍 Поиск всех .txt файлов в {base_path} и всех вложенных папках...")
    
    # Рекурсивный поиск ВСЕХ .txt файлов
    txt_files = find_all_txt_files(base_path)
    
    if not txt_files:
        print(f"❌ Не найдено ни одного .txt файла в {base_path} и его подпапках!")
        return
    
    print(f"✅ Найдено {len(txt_files)} .txt файлов:")
    for tf in txt_files:
        indent = "  " * tf['depth']
        print(f"   {indent}📄 {tf['display_name']}")
    
    all_working = []
    
    # Сканирование каждого найденного .txt файла
    for idx, txt_file in enumerate(txt_files, 1):
        print(f"\n{'='*80}")
        print(f"📊 Сканирование {idx}/{len(txt_files)}")
        print(f"{'='*80}")
        
        working = scan_file(txt_file)
        all_working.extend(working)
    
    if not all_working:
        print("\n❌ Нет работающих прокси!")
        return
    
    # Вывод итогов
    print("\n" + "="*80)
    print(f"✅ ВСЕГО РАБОТАЮЩИХ ПРОКСИ: {len(all_working)}")
    print("="*80)
    
    # Сортировка по скорости
    sorted_proxies = sorted(all_working, key=lambda x: x['total_ms'])
    
    print("\n🏆 ТОП-10 БЫСТРЫХ ПРОКСИ (из всех файлов):")
    print("-"*80)
    for i, p in enumerate(sorted_proxies[:10], 1):
        speed_str = f"{p['total_ms']}ms"
        if p.get('speed_kbps'):
            speed_str += f" ({p['speed_kbps']}KB/s)"
        source_short = p.get('source_file', 'unknown')[:35]
        print(f"{i:2}. {source_short:<37} {p['proxy']:<40} - {speed_str}")
    
    # Сохраняем результаты во всех форматах
    print("\n💾 СОХРАНЕНИЕ РЕЗУЛЬТАТОВ:")
    stats = save_all_formats(all_working)
    
    print(f"\n{'='*80}")
    print(f"✅ СКАНИРОВАНИЕ ЗАВЕРШЕНО!")
    print(f"{'='*80}")
    print(f"\n📁 СОЗДАННЫЕ ФАЙЛЫ:")
    print(f"   1_all_working_proxies.txt    - Все прокси с сортировкой по скорости")
    print(f"   2_proxies_for_reuse.txt      - Для повторного использования (формат с протоколом)")
    print(f"   3_ips_only.txt               - Только IP:PORT без протокола")
    print(f"   4_*_proxies.txt              - Отдельно по каждому протоколу")
    print(f"   5_proxies_analysis.csv       - Таблица для Excel")
    print(f"   6_proxies.json               - JSON для программистов")
    
    print(f"\n📊 ИТОГОВАЯ СТАТИСТИКА:")
    print(f"   Всего прокси: {stats['total']}")
    print(f"   Быстрые (<500ms): {stats['fast']}")
    print(f"   Средние (500-1500ms): {stats['medium']}")
    print(f"   Медленные (>1500ms): {stats['slow']}")
    for protocol, count in stats['by_protocol'].items():
        if count > 0:
            print(f"   {protocol.upper()}: {count}")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    main()