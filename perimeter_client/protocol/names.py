"""北向 CMD 名称。"""

from perimeter_client.protocol.frame import Command

CMD_NAMES: dict[int, str] = {
    Command.POWER_ON: "开启电源",
    Command.POWER_OFF: "关闭电源",
    Command.SIGNAL_ON: "信号打开",
    Command.SIGNAL_OFF: "信号关闭",
    Command.QUERY_SIGNAL: "查询打击状态",
    Command.TEMPERATURE: "温度查询",
    Command.AC_ON: "空调开启",
    Command.AC_OFF: "空调关闭",
    Command.SET_IP: "设置网关IP",
    Command.QUERY_IP: "查询网关IP",
}


def cmd_name(cmd: int) -> str:
    return CMD_NAMES.get(cmd, f"未知命令 0x{cmd:02X}")
