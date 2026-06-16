"""周界拦截上位机主窗口。"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from perimeter_client.config import AppConfig, load_config, save_config
from perimeter_client.logging import get_logger, log_file_path
from perimeter_client.paths import app_base_dir
from perimeter_client.ui.log_handler import LogEmitter, QtLogHandler
from perimeter_client.ui.widgets import StatusLight
from perimeter_client.ui.worker import GatewayWorker, TaskBridge

logger = get_logger("ui")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("周界拦截上位机")
        self.resize(760, 780)

        self._config = load_config()
        self._worker = GatewayWorker(self._config)
        self._task_bridge = TaskBridge()
        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)
        self._worker.bind_bridge(self._task_bridge)
        self._worker_thread.start()
        self._setup_worker_signals()

        self._connected = False
        self._busy = False
        self._task_in_flight = False
        self._current_block_ui = False

        self._build_ui()
        self._setup_ui_logging()
        self._apply_config_to_form()
        self._set_control_enabled(False)

        self._temp_timer = QTimer(self)
        self._temp_timer.timeout.connect(
            lambda: self._poll_temperature(background=True)
        )
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(
            lambda: self._poll_strike_status(background=True)
        )

    def _setup_worker_signals(self) -> None:
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.ip_scanned.connect(self._on_ip_scanned)
        self._worker.ip_applied.connect(self._on_ip_applied)
        self._worker.strike_changed.connect(self._on_strike_changed)
        self._worker.temperature_updated.connect(self._on_temperature_updated)
        self._worker.command_done.connect(self._on_command_done)

    def _setup_ui_logging(self) -> None:
        self._log_emitter = LogEmitter()
        self._log_emitter.message.connect(self._append_log_line)

        ui_level = getattr(logging, self._config.log_ui_level.upper(), logging.INFO)
        qt_handler = QtLogHandler(self._log_emitter, ui_level)
        logging.getLogger("perimeter_client").addHandler(qt_handler)

        log_path = log_file_path()
        if log_path is not None:
            self.log_path_label.setText(f"日志文件: {log_path}")
            logger.info("界面日志已启用，文件日志: %s", log_path)

    def _append_log_line(self, message: str) -> None:
        self.log_view.append(message)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addWidget(self._build_connection_group())
        root.addWidget(self._build_power_group())
        root.addWidget(self._build_strike_group())
        root.addWidget(self._build_temperature_group())
        root.addWidget(self._build_ac_group())
        root.addWidget(self._build_ip_config_group())
        root.addWidget(self._build_log_group(), stretch=1)

    def _build_connection_group(self) -> QGroupBox:
        box = QGroupBox("连接设置")
        layout = QFormLayout(box)

        row_host = QHBoxLayout()
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("192.168.1.201")
        row_host.addWidget(self.host_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(9000)
        row_host.addWidget(QLabel("端口"))
        row_host.addWidget(self.port_input)
        layout.addRow("网关地址", row_host)

        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("扫描当前 IP")
        self.scan_btn.clicked.connect(self._on_scan_ip)
        btn_row.addWidget(self.scan_btn)

        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self._on_connect)
        btn_row.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("断开")
        self.disconnect_btn.clicked.connect(self._on_disconnect)
        btn_row.addWidget(self.disconnect_btn)

        self.save_config_btn = QPushButton("保存配置")
        self.save_config_btn.clicked.connect(self._on_save_config)
        btn_row.addWidget(self.save_config_btn)
        layout.addRow(btn_row)

        self.conn_status_label = QLabel("未连接")
        self.scanned_ip_label = QLabel("当前网关 IP：--")
        layout.addRow("连接状态", self.conn_status_label)
        layout.addRow("", self.scanned_ip_label)

        hint = QLabel("流程：先扫描当前 IP → 确认地址后点击连接 → 方可控制与修改 IP")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addRow(hint)
        return box

    def _build_power_group(self) -> QGroupBox:
        box = QGroupBox("周界拦截 — 电源控制 (0x01 / 0x02)")
        layout = QHBoxLayout(box)

        self.power_on_btn = QPushButton("开启电源")
        self.power_on_btn.clicked.connect(self._on_power_on)
        layout.addWidget(self.power_on_btn)

        self.power_off_btn = QPushButton("关闭电源")
        self.power_off_btn.clicked.connect(self._on_power_off)
        layout.addWidget(self.power_off_btn)

        layout.addStretch()
        layout.addWidget(QLabel("CMD 0x01 开启 / 0x02 关闭"))
        return box

    def _build_strike_group(self) -> QGroupBox:
        box = QGroupBox("周界拦截 — 打击控制 (0x03 / 0x04 / 0x05)")
        layout = QHBoxLayout(box)

        light_col = QVBoxLayout()
        light_col.addWidget(QLabel("打击状态"), alignment=Qt.AlignmentFlag.AlignCenter)
        self.strike_light = StatusLight(32)
        light_col.addWidget(self.strike_light, alignment=Qt.AlignmentFlag.AlignCenter)
        self.strike_text = QLabel("未知")
        self.strike_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        light_col.addWidget(self.strike_text)
        layout.addLayout(light_col)

        btn_col = QVBoxLayout()
        self.strike_on_btn = QPushButton("打击开启")
        self.strike_on_btn.clicked.connect(self._on_strike_on)
        btn_col.addWidget(self.strike_on_btn)

        self.strike_off_btn = QPushButton("打击关闭")
        self.strike_off_btn.clicked.connect(self._on_strike_off)
        btn_col.addWidget(self.strike_off_btn)

        self.strike_query_btn = QPushButton("查询状态")
        self.strike_query_btn.clicked.connect(self._poll_strike_status)
        btn_col.addWidget(self.strike_query_btn)
        layout.addLayout(btn_col)

        legend = QVBoxLayout()
        legend.addWidget(QLabel("绿色：打击已开启"))
        legend.addWidget(QLabel("红色：打击已关闭"))
        legend.addWidget(QLabel("灰色：未知 / 未连接"))
        layout.addLayout(legend)
        layout.addStretch()
        return box

    def _build_temperature_group(self) -> QGroupBox:
        box = QGroupBox("设备仓温度 (0x11)")
        layout = QHBoxLayout(box)
        self.temp_label = QLabel("--")
        self.temp_label.setStyleSheet("font-size: 28px; font-weight: bold;")
        layout.addWidget(self.temp_label)
        layout.addWidget(QLabel("℃"))
        layout.addStretch()
        self.temp_refresh_btn = QPushButton("立即刷新")
        self.temp_refresh_btn.clicked.connect(self._poll_temperature)
        layout.addWidget(self.temp_refresh_btn)
        return box

    def _build_ac_group(self) -> QGroupBox:
        box = QGroupBox("环境控制 — 空调 (0x12 / 0x13)")
        layout = QHBoxLayout(box)

        self.ac_on_btn = QPushButton("空调开启")
        self.ac_on_btn.clicked.connect(self._on_ac_on)
        layout.addWidget(self.ac_on_btn)

        self.ac_off_btn = QPushButton("空调关闭")
        self.ac_off_btn.clicked.connect(self._on_ac_off)
        layout.addWidget(self.ac_off_btn)

        layout.addStretch()
        layout.addWidget(QLabel("CMD 0x12 开启 / 0x13 关闭"))
        return box

    def _build_ip_config_group(self) -> QGroupBox:
        box = QGroupBox("网关 IP 配置 (0x20 / 0x21，需已连接)")
        layout = QFormLayout(box)

        row = QHBoxLayout()
        self.new_ip_input = QLineEdit()
        self.new_ip_input.setPlaceholderText("192.168.1.100")
        row.addWidget(self.new_ip_input)

        self.prefix_input = QSpinBox()
        self.prefix_input.setRange(0, 32)
        self.prefix_input.setValue(24)
        row.addWidget(QLabel("/"))
        row.addWidget(self.prefix_input)
        layout.addRow("新 IP 地址", row)

        self.apply_ip_btn = QPushButton("应用新 IP")
        self.apply_ip_btn.clicked.connect(self._on_apply_ip)
        layout.addRow(self.apply_ip_btn)

        note = QLabel(
            "设置成功后网关需重启服务，请用新 IP 重新扫描并连接。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #B71C1C;")
        layout.addRow(note)
        return box

    def _build_log_group(self) -> QGroupBox:
        box = QGroupBox("运行日志")
        layout = QVBoxLayout(box)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)

        toolbar = QHBoxLayout()
        self.log_path_label = QLabel("日志文件: --")
        self.log_path_label.setStyleSheet("color: #666;")
        toolbar.addWidget(self.log_path_label, stretch=1)

        self.open_log_dir_btn = QPushButton("打开日志目录")
        self.open_log_dir_btn.clicked.connect(self._on_open_log_dir)
        toolbar.addWidget(self.open_log_dir_btn)

        self.clear_log_btn = QPushButton("清空界面")
        self.clear_log_btn.clicked.connect(self.log_view.clear)
        toolbar.addWidget(self.clear_log_btn)
        layout.addLayout(toolbar)
        layout.addWidget(self.log_view)
        return box

    def _apply_config_to_form(self) -> None:
        self.host_input.setText(self._config.host)
        self.port_input.setValue(self._config.port)

    def _read_form_config(self) -> AppConfig:
        return AppConfig(
            host=self.host_input.text().strip() or self._config.host,
            port=self.port_input.value(),
            connect_timeout_sec=self._config.connect_timeout_sec,
            response_timeout_sec=self._config.response_timeout_sec,
            temperature_poll_interval_sec=self._config.temperature_poll_interval_sec,
            status_poll_interval_sec=self._config.status_poll_interval_sec,
            log_level=self._config.log_level,
            log_ui_level=self._config.log_ui_level,
            log_directory=self._config.log_directory,
            log_backup_count=self._config.log_backup_count,
        )

    def _on_open_log_dir(self) -> None:
        log_dir = app_base_dir() / self._config.log_directory
        log_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir.resolve())))
        logger.info("打开日志目录: %s", log_dir)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.scan_btn.setEnabled(not busy)
        self.connect_btn.setEnabled(not busy and not self._connected)
        self.disconnect_btn.setEnabled(not busy and self._connected)
        self._set_control_enabled(self._connected and not busy)

    def _set_control_enabled(self, enabled: bool) -> None:
        for w in (
            self.power_on_btn,
            self.power_off_btn,
            self.strike_on_btn,
            self.strike_off_btn,
            self.strike_query_btn,
            self.temp_refresh_btn,
            self.ac_on_btn,
            self.ac_off_btn,
            self.apply_ip_btn,
            self.new_ip_input,
            self.prefix_input,
        ):
            w.setEnabled(enabled)

    def _on_save_config(self) -> None:
        self._config = self._read_form_config()
        path = save_config(self._config)
        self._task_bridge.submit.emit("update_config", "", 0, self._config)
        logger.info("配置已保存: %s", path)

    def _run_worker(
        self, task: str, args: object = None, *, block_ui: bool = True
    ) -> None:
        if self._task_in_flight:
            return

        self._task_in_flight = True
        self._current_block_ui = block_ui
        if block_ui:
            self._set_busy(True)

        host = self.host_input.text().strip()
        port = self.port_input.value()
        self._task_bridge.submit.emit(task, host, port, args)

    def _on_worker_finished(self) -> None:
        self._task_in_flight = False
        if self._current_block_ui:
            self._set_busy(False)
        self._current_block_ui = False

    def _on_scan_ip(self) -> None:
        host = self.host_input.text().strip()
        if not host:
            QMessageBox.warning(self, "提示", "请先填写网关地址")
            return
        logger.info("正在扫描网关 IP: %s:%s", host, self.port_input.value())
        self._run_worker("scan_ip")

    def _on_ip_scanned(self, ip: str, prefix: int) -> None:
        text = f"当前网关 IP：{ip}/{prefix}"
        self.scanned_ip_label.setText(text)
        self.host_input.setText(ip)
        logger.info("扫描成功: %s/%s", ip, prefix)

    def _on_connect(self) -> None:
        host = self.host_input.text().strip()
        if not host:
            QMessageBox.warning(self, "提示", "请先扫描或填写网关地址")
            return
        logger.info("正在连接: %s:%s", host, self.port_input.value())
        self._run_worker("connect")

    def _on_connected(self) -> None:
        self._connected = True
        self.conn_status_label.setText("已连接")
        self.conn_status_label.setStyleSheet("color: #2E7D32; font-weight: bold;")
        self._set_control_enabled(True)
        logger.info("网关连接成功，控制面板已解锁")
        self._poll_strike_status()
        self._poll_temperature(background=True)
        self._temp_timer.start(int(self._config.temperature_poll_interval_sec * 1000))
        self._status_timer.start(int(self._config.status_poll_interval_sec * 1000))

    def _on_disconnect(self) -> None:
        self._temp_timer.stop()
        self._status_timer.stop()
        self._run_worker("disconnect")

    def _on_disconnected(self) -> None:
        self._connected = False
        self.conn_status_label.setText("未连接")
        self.conn_status_label.setStyleSheet("")
        self._set_strike_unknown()
        self.temp_label.setText("--")
        self._set_control_enabled(False)
        logger.info("已断开连接")

    def _run_command(self, action: str, task: str) -> None:
        logger.info("用户操作: %s", action)
        self._run_worker(task)

    def _on_command_done(self, action: str, payload_hex: str) -> None:
        logger.info("%s 成功，南向回包: %s", action, payload_hex)

    def _on_power_on(self) -> None:
        self._run_command("开启电源 (0x01)", "power_on")

    def _on_power_off(self) -> None:
        self._run_command("关闭电源 (0x02)", "power_off")

    def _on_ac_on(self) -> None:
        self._run_command("空调开启 (0x12)", "ac_on")

    def _on_ac_off(self) -> None:
        self._run_command("空调关闭 (0x13)", "ac_off")

    def _on_strike_on(self) -> None:
        logger.info("用户操作: 打击开启")
        self._run_worker("strike_on")

    def _on_strike_off(self) -> None:
        logger.info("用户操作: 打击关闭")
        self._run_worker("strike_off")

    def _poll_strike_status(self, *, background: bool = False) -> None:
        if not self._connected:
            return
        self._run_worker("query_strike", block_ui=not background)

    def _on_strike_changed(self, is_on: bool) -> None:
        if is_on:
            new_text = "打击已开启"
            new_state = StatusLight.ON
            new_style = "color: #2E7D32; font-weight: bold;"
        else:
            new_text = "打击已关闭"
            new_state = StatusLight.OFF
            new_style = "color: #C62828; font-weight: bold;"

        if self.strike_text.text() != new_text:
            self.strike_light.set_state(new_state)
            self.strike_text.setText(new_text)
            self.strike_text.setStyleSheet(new_style)
            logger.debug("界面更新打击状态: %s", "开启" if is_on else "关闭")

    def _set_strike_unknown(self) -> None:
        self.strike_light.set_state(StatusLight.UNKNOWN)
        self.strike_text.setText("未知")
        self.strike_text.setStyleSheet("color: #757575;")

    def _poll_temperature(self, *, background: bool = False) -> None:
        if not self._connected:
            return
        self._run_worker("query_temperature", block_ui=not background)

    def _on_temperature_updated(self, temp: float) -> None:
        text = f"{temp:.1f}"
        if self.temp_label.text() != text:
            self.temp_label.setText(text)
            logger.debug("界面更新温度: %s ℃", text)

    def _on_apply_ip(self) -> None:
        new_ip = self.new_ip_input.text().strip()
        if not new_ip:
            QMessageBox.warning(self, "提示", "请填写新 IP 地址")
            return
        prefix = self.prefix_input.value()
        reply = QMessageBox.question(
            self,
            "确认修改 IP",
            f"确定将网关 eth1 设置为 {new_ip}/{prefix} 吗？\n"
            "成功后需重启网关服务，并用新 IP 重新连接。",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        logger.info("用户操作: 设置 IP %s/%s", new_ip, prefix)
        self._run_worker("apply_ip", (new_ip, prefix))

    def _on_ip_applied(self, ip: str, prefix: int) -> None:
        self.scanned_ip_label.setText(f"当前网关 IP：{ip}/{prefix}（已应用，请重连）")
        logger.info("IP 设置成功: %s/%s，请重启网关后重连", ip, prefix)
        QMessageBox.information(
            self,
            "IP 已应用",
            f"网关 IP 已设置为 {ip}/{prefix}。\n"
            "请重启 perimeter-gateway 服务，再用新 IP 扫描并连接。",
        )

    def _on_worker_failed(self, message: str) -> None:
        logger.error("操作失败: %s", message)
        if self._current_block_ui:
            QMessageBox.warning(self, "操作失败", message)

    def closeEvent(self, event) -> None:
        self._temp_timer.stop()
        self._status_timer.stop()
        if self._connected:
            self._task_bridge.submit.emit("disconnect", "", 0, None)
            self._worker_thread.wait(3000)
        self._worker_thread.quit()
        self._worker_thread.wait()
        event.accept()
