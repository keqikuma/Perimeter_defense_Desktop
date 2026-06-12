# 周界拦截上位机

基于 Python + PyQt6 的周界网关北向 TCP 控制客户端。Mac 开发，可打包部署至 Windows。

## 功能

- 可编辑 `config.yaml` 连接参数（地址、端口、超时、轮询间隔）
- 电源开启 / 关闭（0x01 / 0x02）
- 打击开启 / 关闭，红绿状态指示灯（0x03 / 0x04 / 0x05）
- 设备仓温度实时读取与展示（0x11）
- 空调开启 / 关闭（0x12 / 0x13）
- 扫描网关当前 IP → 连接 → 控制与修改 IP（0x20 / 0x21）

## 环境要求

- Python 3.10+

## 安装与运行

```bash
cd Perimeter_defense_Desktop
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 配置文件

首次运行会在项目根目录使用 `config.yaml`，也可在界面修改后点击「保存配置」。

```yaml
connection:
  host: 192.168.1.201
  port: 9000
timeouts:
  connect_sec: 5.0
  response_sec: 15.0
polling:
  temperature_sec: 3.0
  status_sec: 5.0
```

## 使用流程

1. 填写或确认网关地址（默认来自配置文件）
2. 点击 **扫描当前 IP**，查询网关 eth1 实际地址
3. 点击 **连接**，建立 TCP 长连接
4. 连接后可进行打击控制、温度监测、IP 修改

> 修改网关 IP 后需重启 `perimeter-gateway`，再用新 IP 扫描并连接。

## Windows 打包

```bash
pip install pyinstaller
pyinstaller --name "周界拦截上位机" --windowed --onefile main.py
```

生成的可执行文件在 `dist/` 目录。将 `config.yaml` 放在 exe 同级目录便于修改。

## 协议文档

详见 [doc/上位机北向TCP协议.md](doc/上位机北向TCP协议.md)。
