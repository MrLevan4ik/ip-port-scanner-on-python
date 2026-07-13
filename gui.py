import os
import sys
import re
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QCheckBox, QPushButton, QTextEdit, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QProgressBar, QGroupBox, QSplitter, QMessageBox, QAbstractItemView,
    QSizePolicy, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QIntValidator


# ---------------------------------------------------------------------------
# Валидированный ввод числа (заменяет QSpinBox со стрелками)
# ---------------------------------------------------------------------------
class NumInput(QLineEdit):
    def __init__(self, default=0, min_val=0, max_val=999999,
                 placeholder="", parent=None):
        super().__init__(parent)
        self._min = min_val
        self._max = max_val
        self.setValidator(QIntValidator(min_val, max_val))
        self.setText(str(default))
        self.setPlaceholderText(placeholder)
        self.setFixedWidth(85)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def value(self):
        try:
            return int(self.text())
        except ValueError:
            return self._min


# ---------------------------------------------------------------------------
# Стили Catppuccin Mocha
# ---------------------------------------------------------------------------
STYLE = """
QMainWindow {
    background-color: #1e1e2e;
}
QGroupBox {
    font-weight: 600;
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 10px;
    padding: 12px 8px 8px 8px;
    color: #cdd6f4;
    background-color: rgba(49, 50, 68, 80);
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    color: #89b4fa;
    font-size: 11px;
}
QLabel {
    color: #bac2de;
    font-size: 11px;
}
QLineEdit {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 5px;
    padding: 5px 8px;
    font-size: 12px;
    selection-background-color: #45475a;
}
QLineEdit:focus {
    border: 1px solid #89b4fa;
}
QLineEdit:read-only {
    background-color: #11111b;
    color: #6c7086;
}
QCheckBox {
    color: #a6adc8;
    spacing: 6px;
    font-size: 11px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1.5px solid #45475a;
    background-color: #181825;
}
QCheckBox::indicator:hover {
    border-color: #585b70;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}
QPushButton {
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 600;
    font-size: 12px;
    min-height: 22px;
}
QPushButton#btn_start {
    background-color: #a6e3a1;
    color: #1e1e2e;
}
QPushButton#btn_start:hover {
    background-color: #94e2d5;
}
QPushButton#btn_start:disabled {
    background-color: #313244;
    color: #585b70;
}
QPushButton#btn_stop {
    background-color: #f38ba8;
    color: #1e1e2e;
}
QPushButton#btn_stop:hover {
    background-color: #eba0ac;
}
QPushButton#btn_stop:disabled {
    background-color: #313244;
    color: #585b70;
}
QPushButton#btn_browse {
    background-color: #313244;
    color: #a6adc8;
    padding: 5px 10px;
    font-size: 11px;
}
QPushButton#btn_browse:hover {
    background-color: #45475a;
    color: #cdd6f4;
}
QPushButton#btn_open {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QPushButton#btn_open:hover {
    background-color: #74c7ec;
}
QPushButton#btn_open:disabled {
    background-color: #313244;
    color: #585b70;
}
QProgressBar {
    border: 1px solid #313244;
    border-radius: 6px;
    text-align: center;
    color: #1e1e2e;
    background-color: #181825;
    font-size: 11px;
    font-weight: 600;
    min-height: 22px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #a6e3a1, stop:1 #94e2d5);
    border-radius: 5px;
}
QTextEdit {
    background-color: #11111b;
    color: #a6e3a1;
    border: 1px solid #313244;
    border-radius: 6px;
    font-family: 'Cascadia Code', 'Consolas', 'SF Mono', monospace;
    font-size: 11px;
    padding: 4px;
}
QTableWidget {
    background-color: #11111b;
    color: #cdd6f4;
    gridline-color: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 6px;
    selection-background-color: #313244;
    font-size: 11px;
}
QTableWidget::item {
    padding: 3px 6px;
}
QHeaderView::section {
    background-color: #181825;
    color: #89b4fa;
    border: none;
    border-bottom: 2px solid #313244;
    padding: 6px 8px;
    font-weight: 600;
    font-size: 11px;
}
QStatusBar {
    background-color: #11111b;
    color: #585b70;
    border-top: 1px solid #1e1e2e;
    font-size: 11px;
}
QSplitter::handle {
    background-color: #313244;
    width: 2px;
}
"""


# ---------------------------------------------------------------------------
# Поток сканирования
# ---------------------------------------------------------------------------
class ScanWorker(QThread):
    progress = pyqtSignal(int, int, int)
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
                check_proxy_with_retry, _setup_logs, is_valid_ip,
            )
        except ImportError as e:
            self.error.emit(f"Ошибка импорта: {e}")
            return

        cfg = self.config
        if not cfg.get("no_log_errors") or not cfg.get("no_log_general"):
            _setup_logs()

        base_path = cfg["input_dir"]
        if not os.path.exists(base_path):
            self.error.emit(f"Папка не найдена: {base_path}")
            return

        self.log.emit(f"[INFO] Поиск .txt файлов в {base_path}")
        txt_files = find_all_txt_files(base_path)
        if not txt_files:
            self.error.emit(f"Нет .txt файлов в {base_path}!")
            return

        self.log.emit(f"[INFO] Найдено файлов: {len(txt_files)}")
        for tf in txt_files:
            self.log.emit(f"  {tf['display_name']}")

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
                remaining = cfg["limit"] - done_count
                proxies = proxies[:remaining]

            self.log.emit(f"\n[FILE] {txt_file['display_name']} "
                          f"({len(proxies)} прокси)")

            for proto, ip, port in proxies:
                if self._stop:
                    break

                result = check_proxy_with_retry(
                    proto, ip, port, cfg["timeout"],
                    cfg["test_url"], cfg.get("retry", 1))

                done_count += 1
                if result:
                    if cfg.get("min_speed") and result["total_ms"] > cfg["min_speed"]:
                        self.progress.emit(done_count, total_proxies, found_count)
                        continue
                    result["source_file"] = txt_file["display_name"]
                    all_working.append(result)
                    found_count += 1
                    speed = f"{result['total_ms']}ms"
                    if result.get("speed_kbps"):
                        speed += f", {result['speed_kbps']}KB/s"
                    self.log.emit(f"[OK]  {result['proxy']} - {speed}")

                self.progress.emit(done_count, total_proxies, found_count)

        self.result_ready.emit(all_working)


# ---------------------------------------------------------------------------
# Лог виджет
# ---------------------------------------------------------------------------
class LogWidget(QTextEdit):
    def append_colored(self, msg: str, color: str = "#a6e3a1"):
        self.setTextColor(QColor(color))
        self.append(msg)
        self.setTextColor(QColor("#a6e3a1"))
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class ProxyScannerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Proxy Scanner")
        self.setMinimumSize(960, 620)
        self.resize(1050, 680)
        self.worker = None

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(10, 8, 10, 8)

        # --- Заголовок (компактный) ---
        header = QHBoxLayout()
        header.setSpacing(10)
        dot = QLabel("\u25cf")
        dot.setStyleSheet("color: #a6e3a1; font-size: 10px;")
        header.addWidget(dot)
        title = QLabel("PROXY SCANNER")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #cdd6f4; letter-spacing: 2px;")
        header.addWidget(title)
        header.addStretch()
        ver = QLabel("v2.0")
        ver.setStyleSheet("color: #585b70; font-size: 10px;")
        header.addWidget(ver)
        main_layout.addLayout(header)

        # --- Секция настроек ---
        settings = QGroupBox("Настройки")
        s_layout = QVBoxLayout()
        s_layout.setSpacing(6)
        settings.setLayout(s_layout)

        # Папки
        folders = QHBoxLayout()
        folders.setSpacing(6)
        folders.addWidget(QLabel("Вход:"))
        self.input_dir = QLineEdit("proxies")
        self.input_dir.setMinimumWidth(160)
        folders.addWidget(self.input_dir)
        btn_in = QPushButton("...")
        btn_in.setObjectName("btn_browse")
        btn_in.setFixedWidth(32)
        btn_in.clicked.connect(lambda: self._browse("input"))
        folders.addWidget(btn_in)

        folders.addSpacing(16)

        folders.addWidget(QLabel("Выход:"))
        self.output_dir = QLineEdit(".")
        self.output_dir.setMinimumWidth(160)
        folders.addWidget(self.output_dir)
        btn_out = QPushButton("...")
        btn_out.setObjectName("btn_browse")
        btn_out.setFixedWidth(32)
        btn_out.clicked.connect(lambda: self._browse("output"))
        folders.addWidget(btn_out)
        folders.addStretch()
        s_layout.addLayout(folders)

        # Параметры (NumInput вместо QSpinBox)
        params = QHBoxLayout()
        params.setSpacing(4)

        param_defs = [
            ("Таймаут (с)", 5, 1, 60),
            ("Потоки", 30, 1, 500),
            ("Ретраи", 1, 1, 10),
            ("Лимит", 0, 0, 999999),
            ("Мин. задержка (мс)", 0, 0, 60000),
        ]

        self.param_inputs = {}
        for label_text, default, min_v, max_v in param_defs:
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 10px;")
            params.addWidget(lbl)
            inp = NumInput(default, min_v, max_v)
            params.addWidget(inp)
            self.param_inputs[label_text] = inp
            params.addSpacing(8)

        params.addStretch()
        s_layout.addLayout(params)

        # Чекбоксы
        checks = QHBoxLayout()
        checks.setSpacing(12)
        self.chk_progress = QCheckBox("Прогресс-бар")
        self.chk_validate = QCheckBox("Валидация IP")
        self.chk_geo = QCheckBox("Геолокация")
        self.chk_fetch = QCheckBox("Авто-загрузка")
        self.chk_no_log_err = QCheckBox("Без лога ошибок")
        self.chk_no_log_gen = QCheckBox("Без общего лога")
        for chk in (self.chk_progress, self.chk_validate,
                    self.chk_geo, self.chk_fetch,
                    self.chk_no_log_err, self.chk_no_log_gen):
            checks.addWidget(chk)
        checks.addStretch()
        s_layout.addLayout(checks)

        main_layout.addWidget(settings)

        # --- Кнопки управления ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_start = QPushButton("\u25b6  СКАНИРОВАТЬ")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setFixedHeight(32)
        self.btn_start.clicked.connect(self._start_scan)

        self.btn_stop = QPushButton("\u25a0  СТОП")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setFixedHeight(32)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_scan)

        self.btn_open = QPushButton("\u2197  ОТКРЫТЬ РЕЗУЛЬТАТЫ")
        self.btn_open.setObjectName("btn_open")
        self.btn_open.setFixedHeight(32)
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_results)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.btn_open)
        btn_row.addStretch()
        main_layout.addLayout(btn_row)

        # --- Прогресс-бар ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%  |  %v / %m")
        self.progress_bar.setFixedHeight(24)
        main_layout.addWidget(self.progress_bar)

        # --- Сплиттер: лог + таблица ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Лог
        log_frame = QWidget()
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(4)
        log_label = QLabel("Лог")
        log_label.setStyleSheet("color: #585b70; font-size: 10px; font-weight: 600;")
        log_layout.addWidget(log_label)
        self.log_text = LogWidget()
        log_layout.addWidget(self.log_text)
        splitter.addWidget(log_frame)

        # Таблица результатов
        table_frame = QWidget()
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)
        table_label = QLabel("Результаты")
        table_label.setStyleSheet("color: #585b70; font-size: 10px; font-weight: 600;")
        table_layout.addWidget(table_label)
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels(
            ["#", "Протокол", "IP", "Порт", "Задержка", "Скорость", "Источник"])
        self.results_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setShowGrid(False)
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        table_layout.addWidget(self.results_table)
        splitter.addWidget(table_frame)

        splitter.setSizes([380, 620])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

        # Статус-бар
        self.statusBar().showMessage("Готово")

    def _browse(self, target: str):
        d = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if d:
            if target == "input":
                self.input_dir.setText(d)
            else:
                self.output_dir.setText(d)

    def _start_scan(self):
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_open.setEnabled(False)
        self.log_text.clear()
        self.results_table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Сканирование...")

        params = self.param_inputs
        config = {
            "input_dir": self.input_dir.text(),
            "output_dir": self.output_dir.text(),
            "timeout": params["Таймаут (с)"].value(),
            "workers": params["Потоки"].value(),
            "test_url": "http://httpbin.org/get",
            "retry": params["Ретраи"].value(),
            "min_speed": params["Мин. задержка (мс)"].value() or None,
            "limit": params["Лимит"].value() or None,
            "validate_ip": self.chk_validate.isChecked(),
            "geo": self.chk_geo.isChecked(),
            "fetch": self.chk_fetch.isChecked(),
            "no_log_errors": self.chk_no_log_err.isChecked(),
            "no_log_general": self.chk_no_log_gen.isChecked(),
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
            self.log_text.append_colored("\n[STOP] Остановка...", "#f38ba8")
            self.statusBar().showMessage("Остановка...")

    def _on_progress(self, done, total, found):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(done)
        self.statusBar().showMessage(
            f"Проверено: {done}/{total}  |  Найдено: {found}")

    def _on_log(self, msg: str):
        if msg.startswith("[OK]"):
            self.log_text.append_colored(msg, "#a6e3a1")
        elif msg.startswith("[FAIL]"):
            self.log_text.append_colored(msg, "#f38ba8")
        elif msg.startswith("[FILE]"):
            self.log_text.append_colored(msg, "#89b4fa")
        elif msg.startswith("[INFO]"):
            self.log_text.append_colored(msg, "#f9e2af")
        else:
            self.log_text.append_colored(msg, "#585b70")

    def _on_results(self, results: list):
        if not results:
            self.log_text.append_colored(
                "\n[RESULT] Рабочих прокси не найдено!", "#f38ba8")
            self.statusBar().showMessage("Готово - нет прокси")
            return

        results.sort(key=lambda x: x["total_ms"])

        self.results_table.setRowCount(len(results))
        for i, p in enumerate(results):
            speed = f"{p['total_ms']}ms"
            if p.get("speed_kbps"):
                speed += f" ({p['speed_kbps']}KB/s)"

            items = [
                str(i + 1), p["protocol"], p["ip"], str(p["port"]),
                speed,
                f"{p.get('speed_kbps', '')} KB/s" if p.get("speed_kbps") else "",
                p.get("source_file", ""),
            ]
            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                # Цвет строки по скорости
                if p["total_ms"] < 500:
                    bg = QColor(24, 68, 24)
                elif p["total_ms"] < 1500:
                    bg = QColor(68, 64, 24)
                else:
                    bg = QColor(68, 24, 24)
                item.setBackground(bg)
                self.results_table.setItem(i, col, item)

        self.log_text.append_colored(
            f"\n[RESULT] Найдено {len(results)} работающих прокси", "#89b4fa")

        # Сохранение
        self.log_text.append_colored("[INFO] Сохранение результатов...", "#f9e2af")
        try:
            from main import save_all_formats
            save_all_formats(results, self.output_dir.text(),
                             self.chk_geo.isChecked())
            self.log_text.append_colored("[INFO] Результаты сохранены", "#a6e3a1")
        except Exception as e:
            self.log_text.append_colored(
                f"[ERROR] Ошибка сохранения: {e}", "#f38ba8")

        self.btn_open.setEnabled(True)
        self.statusBar().showMessage(f"Готово - найдено {len(results)} прокси")

    def _on_error(self, msg: str):
        QMessageBox.warning(self, "Ошибка", msg)
        self.log_text.append_colored(f"\n[ERROR] {msg}", "#f38ba8")
        self.statusBar().showMessage("Ошибка")

    def _on_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

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
    app.setStyleSheet(STYLE)

    window = ProxyScannerGUI()
    window.show()
    sys.exit(app.exec())
