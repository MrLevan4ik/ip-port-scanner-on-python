import os
import sys
import time
import json
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QSpinBox, QCheckBox, QPushButton,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QProgressBar, QGroupBox, QComboBox, QSplitter, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor


# ---------------------------------------------------------------------------
# Поток сканирования
# ---------------------------------------------------------------------------
class ScanWorker(QThread):
    progress = pyqtSignal(int, int, int)  # done, total, found
    log = pyqtSignal(str)
    result_ready = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            from main import (
                find_all_txt_files, read_proxies_from_file,
                check_proxy_with_retry, log_error, is_valid_ip,
                _setup_error_log,
            )
        except ImportError as e:
            self.error.emit(f"Ошибка импорта main.py: {e}")
            return

        cfg = self.config
        if not cfg.get("no_log_errors"):
            _setup_error_log()

        base_path = cfg["input_dir"]
        if not os.path.exists(base_path):
            self.error.emit(f"Папка {base_path} не найдена!")
            return

        self.log.emit(f"Поиск .txt файлов в {base_path} ...")
        txt_files = find_all_txt_files(base_path)
        if not txt_files:
            self.error.emit(f"Не найдено .txt файлов в {base_path}!")
            return

        self.log.emit(f"Найдено {len(txt_files)} файлов")

        all_working = []
        total_proxies = 0
        for tf in txt_files:
            proxies = read_proxies_from_file(tf["path"], cfg.get("validate_ip"))
            total_proxies += len(proxies)

        if cfg.get("limit") and total_proxies > cfg["limit"]:
            total_proxies = cfg["limit"]

        done_count = 0
        found_count = 0

        for txt_file in txt_files:
            if self._stop:
                break

            proxies = read_proxies_from_file(
                txt_file["path"], cfg.get("validate_ip"))
            if cfg.get("limit"):
                proxies = proxies[:cfg["limit"] - done_count]

            self.log.emit(f"Файл: {txt_file['display_name']} "
                          f"({len(proxies)} прокси)")

            for proto, ip, port in proxies:
                if self._stop:
                    break

                result = check_proxy_with_retry(
                    proto, ip, port, cfg["timeout"],
                    cfg["test_url"], cfg.get("retry", 1))

                done_count += 1
                if result:
                    # Фильтр по скорости
                    if cfg.get("min_speed") and result["total_ms"] > cfg["min_speed"]:
                        self.progress.emit(done_count, total_proxies, found_count)
                        continue
                    result["source_file"] = txt_file["display_name"]
                    all_working.append(result)
                    found_count += 1
                    speed = f"{result['total_ms']}ms"
                    if result.get("speed_kbps"):
                        speed += f", {result['speed_kbps']}KB/s"
                    self.log.emit(f"  [OK]  {result['proxy']} - {speed}")

                self.progress.emit(done_count, total_proxies, found_count)

        self.result_ready.emit(all_working)


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class ProxyScannerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Proxy Scanner")
        self.setMinimumSize(900, 650)
        self.worker = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Верхняя панель — настройки
        settings_group = QGroupBox("Настройки")
        settings_layout = QVBoxLayout()

        # Ряд 1: папки
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Папка с прокси:"))
        self.input_dir = QLineEdit("proxies")
        row1.addWidget(self.input_dir)
        btn_browse_in = QPushButton("Обзор...")
        btn_browse_in.clicked.connect(self._browse_input)
        row1.addWidget(btn_browse_in)

        row1.addWidget(QLabel("Папка результатов:"))
        self.output_dir = QLineEdit(".")
        row1.addWidget(self.output_dir)
        btn_browse_out = QPushButton("Обзор...")
        btn_browse_out.clicked.connect(self._browse_output)
        row1.addWidget(btn_browse_out)
        settings_layout.addLayout(row1)

        # Ряд 2: параметры
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Таймаут (сек):"))
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 60)
        self.timeout.setValue(5)
        row2.addWidget(self.timeout)

        row2.addWidget(QLabel("Потоки:"))
        self.workers = QSpinBox()
        self.workers.setRange(1, 500)
        self.workers.setValue(30)
        row2.addWidget(self.workers)

        row2.addWidget(QLabel("Ретраи:"))
        self.retries = QSpinBox()
        self.retries.setRange(1, 10)
        self.retries.setValue(1)
        row2.addWidget(self.retries)

        row2.addWidget(QLabel("Лимит:"))
        self.limit = QSpinBox()
        self.limit.setRange(0, 999999)
        self.limit.setValue(0)
        self.limit.setSpecialValueText("нет")
        row2.addWidget(self.limit)

        row2.addWidget(QLabel("Мин.скорость (мс):"))
        self.min_speed = QSpinBox()
        self.min_speed.setRange(0, 60000)
        self.min_speed.setValue(0)
        self.min_speed.setSpecialValueText("нет")
        row2.addWidget(self.min_speed)
        settings_layout.addLayout(row2)

        # Ряд 3: чекбоксы
        row3 = QHBoxLayout()
        self.chk_progress = QCheckBox("Прогресс-бар")
        self.chk_validate = QCheckBox("Валидация IP")
        self.chk_geo = QCheckBox("Геолокация")
        self.chk_fetch = QCheckBox("Скачать списки")
        self.chk_no_log = QCheckBox("Без логов")
        for chk in (self.chk_progress, self.chk_validate,
                    self.chk_geo, self.chk_fetch, self.chk_no_log):
            row3.addWidget(chk)
        row3.addStretch()
        settings_layout.addLayout(row3)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Кнопки управления
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Сканировать")
        self.btn_start.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "font-weight: bold; padding: 8px 20px; }")
        self.btn_start.clicked.connect(self._start_scan)

        self.btn_stop = QPushButton("Остановить")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; "
            "font-weight: bold; padding: 8px 20px; }")
        self.btn_stop.clicked.connect(self._stop_scan)

        self.btn_open_results = QPushButton("Открыть результаты")
        self.btn_open_results.setEnabled(False)
        self.btn_open_results.clicked.connect(self._open_results)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_open_results)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Нижняя часть: лог + таблица результатов
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Лог
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(QLabel("Лог:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)
        splitter.addWidget(log_widget)

        # Таблица результатов
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.addWidget(QLabel("Результаты:"))
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels(
            ["#", "Протокол", "IP", "Порт", "Задержка", "Скорость", "Файл"])
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        results_layout.addWidget(self.results_table)
        splitter.addWidget(results_widget)

        splitter.setSizes([350, 550])
        layout.addWidget(splitter)

    def _browse_input(self):
        d = QFileDialog.getExistingDirectory(self, "Папка с прокси")
        if d:
            self.input_dir.setText(d)

    def _browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "Папка результатов")
        if d:
            self.output_dir.setText(d)

    def _start_scan(self):
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_open_results.setEnabled(False)
        self.log_text.clear()
        self.results_table.setRowCount(0)
        self.progress_bar.setValue(0)

        config = {
            "input_dir": self.input_dir.text(),
            "output_dir": self.output_dir.text(),
            "timeout": self.timeout.value(),
            "workers": self.workers.value(),
            "test_url": "http://httpbin.org/get",
            "retry": self.retries.value(),
            "min_speed": self.min_speed.value() or None,
            "limit": self.limit.value() or None,
            "validate_ip": self.chk_validate.isChecked(),
            "geo": self.chk_geo.isChecked(),
            "fetch": self.chk_fetch.isChecked(),
            "no_log_errors": self.chk_no_log.isChecked(),
        }

        self.worker = ScanWorker(config)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._on_log)
        self.worker.result_ready.connect(self._on_results)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _stop_scan(self):
        if self.worker:
            self.worker.stop()
            self.log_text.append("\nОстановка...")

    def _on_progress(self, done, total, found):
        if total > 0:
            self.progress_bar.setValue(int(done / total * 100))

    def _on_log(self, msg):
        self.log_text.append(msg)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_results(self, results):
        if not results:
            self.log_text.append("\nНет работающих прокси!")
            return

        results.sort(key=lambda x: x["total_ms"])

        # Заполнение таблицы
        self.results_table.setRowCount(len(results))
        for i, p in enumerate(results):
            speed = f"{p['total_ms']}ms"
            if p.get("speed_kbps"):
                speed += f" ({p['speed_kbps']}KB/s)"

            items = [
                str(i + 1), p["protocol"], p["ip"], str(p["port"]),
                speed, f"{p.get('speed_kbps', '')} KB/s"
                if p.get("speed_kbps") else "",
                p.get("source_file", ""),
            ]
            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                # Цвет строки по скорости
                if p["total_ms"] < 500:
                    item.setBackground(QColor(200, 255, 200))
                elif p["total_ms"] < 1500:
                    item.setBackground(QColor(255, 255, 200))
                else:
                    item.setBackground(QColor(255, 200, 200))
                self.results_table.setItem(i, col, item)

        self.log_text.append(f"\nНайдено прокси: {len(results)}")

        # Сохранение результатов
        self.log_text.append("Сохранение результатов...")
        try:
            from main import save_all_formats
            save_all_formats(results, self.output_dir.text(),
                             self.chk_geo.isChecked())
        except Exception as e:
            self.log_text.append(f"Ошибка сохранения: {e}")

        self.btn_open_results.setEnabled(True)

    def _on_error(self, msg):
        QMessageBox.warning(self, "Ошибка", msg)
        self.log_text.append(f"\nОШИБКА: {msg}")

    def _on_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(100)

    def _open_results(self):
        out = self.output_dir.text()
        if os.path.isdir(out):
            try:
                if sys.platform == "win32":
                    os.startfile(out)
                elif sys.platform == "darwin":
                    import subprocess
                    subprocess.Popen(["open", out])
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", out])
            except Exception as e:
                QMessageBox.warning(self, "Ошибка",
                                    f"Не удалось открыть: {e}")


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------
def run_gui():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Тёмная тема
    palette = app.palette()
    palette.setColor(palette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(palette.ColorRole.WindowText, QColor(255, 255, 255))
    palette.setColor(palette.ColorRole.Base, QColor(35, 35, 35))
    palette.setColor(palette.ColorRole.AlternateBase, QColor(53, 53, 53))
    palette.setColor(palette.ColorRole.ToolTipBase, QColor(25, 25, 25))
    palette.setColor(palette.ColorRole.ToolTipText, QColor(255, 255, 255))
    palette.setColor(palette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(palette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(palette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(palette.ColorRole.BrightText, QColor(255, 0, 0))
    palette.setColor(palette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(palette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(palette.ColorRole.HighlightedText, QColor(35, 35, 35))
    app.setPalette(palette)

    window = ProxyScannerGUI()
    window.show()
    sys.exit(app.exec())
