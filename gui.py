import os
import sys
import time
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QSpinBox, QCheckBox, QPushButton,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QProgressBar, QGroupBox, QSplitter, QMessageBox, QFrame,
    QAbstractItemView, QStatusBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QTextCursor


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
STYLE = """
QMainWindow {
    background-color: #1e1e2e;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 14px;
    color: #cdd6f4;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #89b4fa;
}
QLabel {
    color: #cdd6f4;
}
QLineEdit, QSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 5px 8px;
    min-height: 22px;
}
QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #89b4fa;
}
QCheckBox {
    color: #cdd6f4;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #45475a;
    background-color: #313244;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}
QPushButton {
    border: none;
    border-radius: 5px;
    padding: 7px 18px;
    font-weight: bold;
    min-height: 24px;
}
QPushButton#btn_start {
    background-color: #a6e3a1;
    color: #1e1e2e;
}
QPushButton#btn_start:hover {
    background-color: #94e2d5;
}
QPushButton#btn_start:disabled {
    background-color: #45475a;
    color: #6c7086;
}
QPushButton#btn_stop {
    background-color: #f38ba8;
    color: #1e1e2e;
}
QPushButton#btn_stop:hover {
    background-color: #eba0ac;
}
QPushButton#btn_stop:disabled {
    background-color: #45475a;
    color: #6c7086;
}
QPushButton#btn_browse {
    background-color: #45475a;
    color: #cdd6f4;
}
QPushButton#btn_browse:hover {
    background-color: #585b70;
}
QPushButton#btn_open {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QPushButton#btn_open:hover {
    background-color: #74c7ec;
}
QPushButton#btn_open:disabled {
    background-color: #45475a;
    color: #6c7086;
}
QProgressBar {
    border: 1px solid #45475a;
    border-radius: 4px;
    text-align: center;
    color: #1e1e2e;
    background-color: #313244;
    min-height: 20px;
}
QProgressBar::chunk {
    background-color: #a6e3a1;
    border-radius: 3px;
}
QTextEdit {
    background-color: #181825;
    color: #a6e3a1;
    border: 1px solid #45475a;
    border-radius: 4px;
    font-family: Consolas, monospace;
    font-size: 11px;
}
QTableWidget {
    background-color: #181825;
    color: #cdd6f4;
    gridline-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    selection-background-color: #45475a;
}
QTableWidget::item {
    padding: 4px 8px;
}
QHeaderView::section {
    background-color: #313244;
    color: #89b4fa;
    border: none;
    border-bottom: 2px solid #45475a;
    padding: 6px 8px;
    font-weight: bold;
}
QStatusBar {
    background-color: #181825;
    color: #6c7086;
    border-top: 1px solid #313244;
}
QSplitter::handle {
    background-color: #313244;
}
QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 4px;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #313244;
    color: #6c7086;
    padding: 8px 16px;
    border: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #45475a;
    color: #cdd6f4;
}
"""


# ---------------------------------------------------------------------------
# Scan worker thread
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
            self.error.emit(f"Import error: {e}")
            return

        cfg = self.config
        if not cfg.get("no_log_errors") or not cfg.get("no_log_general"):
            _setup_logs()

        base_path = cfg["input_dir"]
        if not os.path.exists(base_path):
            self.error.emit(f"Folder not found: {base_path}")
            return

        self.log.emit(f"[INFO] Searching .txt files in {base_path}")
        txt_files = find_all_txt_files(base_path)
        if not txt_files:
            self.error.emit(f"No .txt files in {base_path}!")
            return

        self.log.emit(f"[INFO] Found {len(txt_files)} files")
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
                          f"({len(proxies)} proxies)")

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
# Log widget with color highlighting
# ---------------------------------------------------------------------------
class LogWidget(QTextEdit):
    def append_log(self, msg: str):
        self.append(msg)
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def append_colored(self, msg: str, color: str = "#a6e3a1"):
        self.setTextColor(QColor(color))
        self.append(msg)
        self.setTextColor(QColor("#a6e3a1"))
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class ProxyScannerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Proxy Scanner")
        self.setMinimumSize(1000, 700)
        self.resize(1100, 750)
        self.worker = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Title
        title = QLabel("PROXY SCANNER")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #89b4fa; padding: 4px 0;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Settings
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()
        settings_group.setLayout(settings_layout)

        # Row 1: Folders
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Input dir:"))
        self.input_dir = QLineEdit("proxies")
        self.input_dir.setMinimumWidth(180)
        row1.addWidget(self.input_dir)
        btn_in = QPushButton("Browse...")
        btn_in.setObjectName("btn_browse")
        btn_in.setFixedWidth(80)
        btn_in.clicked.connect(lambda: self._browse("input"))
        row1.addWidget(btn_in)

        row1.addSpacing(20)

        row1.addWidget(QLabel("Output dir:"))
        self.output_dir = QLineEdit(".")
        self.output_dir.setMinimumWidth(180)
        row1.addWidget(self.output_dir)
        btn_out = QPushButton("Browse...")
        btn_out.setObjectName("btn_browse")
        btn_out.setFixedWidth(80)
        btn_out.clicked.connect(lambda: self._browse("output"))
        row1.addWidget(btn_out)
        row1.addStretch()
        settings_layout.addLayout(row1)

        # Row 2: Parameters
        row2 = QHBoxLayout()
        for label_text, widget, default in [
            ("Timeout (s):", QSpinBox(), 5),
            ("Workers:", QSpinBox(), 30),
            ("Retries:", QSpinBox(), 1),
            ("Limit:", QSpinBox(), 0),
            ("Min speed (ms):", QSpinBox(), 0),
        ]:
            row2.addWidget(QLabel(label_text))
            if label_text == "Timeout (s):":
                widget.setRange(1, 60)
            elif label_text == "Workers:":
                widget.setRange(1, 500)
            elif label_text == "Retries:":
                widget.setRange(1, 10)
            elif "Limit" in label_text:
                widget.setRange(0, 999999)
                widget.setSpecialValueText("none")
            elif "Min speed" in label_text:
                widget.setRange(0, 60000)
                widget.setSpecialValueText("none")
            widget.setValue(default)
            widget.setFixedWidth(80)
            row2.addWidget(widget)
            row2.addSpacing(8)

        row2.addStretch()
        settings_layout.addLayout(row2)

        # Store widgets
        self.timeout_w = row2.itemAt(1).widget()
        self.workers_w = row2.itemAt(3).widget()
        self.retries_w = row2.itemAt(5).widget()
        self.limit_w = row2.itemAt(7).widget()
        self.min_speed_w = row2.itemAt(9).widget()

        # Row 3: Checkboxes
        row3 = QHBoxLayout()
        self.chk_progress = QCheckBox("Progress bar")
        self.chk_validate = QCheckBox("Validate IP")
        self.chk_geo = QCheckBox("Geolocation")
        self.chk_fetch = QCheckBox("Auto-fetch lists")
        self.chk_no_log_err = QCheckBox("No error log")
        self.chk_no_log_gen = QCheckBox("No general log")
        for chk in (self.chk_progress, self.chk_validate,
                    self.chk_geo, self.chk_fetch,
                    self.chk_no_log_err, self.chk_no_log_gen):
            row3.addWidget(chk)
        row3.addStretch()
        settings_layout.addLayout(row3)

        layout.addWidget(settings_group)

        # Control buttons
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("  SCAN  ")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setFixedHeight(36)
        self.btn_start.clicked.connect(self._start_scan)

        self.btn_stop = QPushButton("  STOP  ")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setFixedHeight(36)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_scan)

        self.btn_open = QPushButton("  OPEN RESULTS  ")
        self.btn_open.setObjectName("btn_open")
        self.btn_open.setFixedHeight(36)
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_results)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_open)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%  |  %v / %m")
        layout.addWidget(self.progress_bar)

        # Splitter: log + results
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: log
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Log"))
        self.log_text = LogWidget()
        self.log_text.setFont(QFont("Consolas", 10))
        left_layout.addWidget(self.log_text)
        splitter.addWidget(left)

        # Right: results table
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Results"))
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels(
            ["#", "Protocol", "IP", "Port", "Latency", "Speed", "Source"])
        self.results_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setAlternatingRowColors(False)
        self.results_table.verticalHeader().setVisible(False)
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        right_layout.addWidget(self.results_table)
        splitter.addWidget(right)

        splitter.setSizes([400, 600])
        layout.addWidget(splitter)

        # Status bar
        self.statusBar().showMessage("Ready")

    def _browse(self, target: str):
        d = QFileDialog.getExistingDirectory(self, "Select folder")
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
        self.statusBar().showMessage("Scanning...")

        config = {
            "input_dir": self.input_dir.text(),
            "output_dir": self.output_dir.text(),
            "timeout": self.timeout_w.value(),
            "workers": self.workers_w.value(),
            "test_url": "http://httpbin.org/get",
            "retry": self.retries_w.value(),
            "min_speed": self.min_speed_w.value() or None,
            "limit": self.limit_w.value() or None,
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
            self.log_text.append_colored("\n[STOP] Stopping...", "#f38ba8")
            self.statusBar().showMessage("Stopping...")

    def _on_progress(self, done, total, found):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(done)
        self.statusBar().showMessage(
            f"Scanning: {done}/{total}  |  Found: {found}")

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
            self.log_text.append_colored(msg, "#6c7086")

    def _on_results(self, results: list):
        if not results:
            self.log_text.append_colored(
                "\n[RESULT] No working proxies found!", "#f38ba8")
            self.statusBar().showMessage("Done - no working proxies")
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
                # Color by speed
                if p["total_ms"] < 500:
                    item.setBackground(QColor(24, 80, 24))
                elif p["total_ms"] < 1500:
                    item.setBackground(QColor(80, 75, 24))
                else:
                    item.setBackground(QColor(80, 24, 24))
                self.results_table.setItem(i, col, item)

        self.log_text.append_colored(
            f"\n[RESULT] Found {len(results)} working proxies", "#89b4fa")

        # Save
        self.log_text.append_colored("[INFO] Saving results...", "#f9e2af")
        try:
            from main import save_all_formats
            save_all_formats(results, self.output_dir.text(),
                             self.chk_geo.isChecked())
            self.log_text.append_colored("[INFO] Results saved", "#a6e3a1")
        except Exception as e:
            self.log_text.append_colored(
                f"[ERROR] Save failed: {e}", "#f38ba8")

        self.btn_open.setEnabled(True)
        self.statusBar().showMessage(f"Done - {len(results)} proxies found")

    def _on_error(self, msg: str):
        QMessageBox.warning(self, "Error", msg)
        self.log_text.append_colored(f"\n[ERROR] {msg}", "#f38ba8")
        self.statusBar().showMessage("Error")

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
                QMessageBox.warning(self, "Error",
                                    f"Could not open: {e}")


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
def run_gui():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)

    window = ProxyScannerGUI()
    window.show()
    sys.exit(app.exec())
