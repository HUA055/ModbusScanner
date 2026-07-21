# ModbusScanner

> ⚠️ **本项目由 AI 生成**：全部代码与文档由 AI 助手（虾助理 / WorkBuddy）在用户指令下自动生成，未经人工逐行审查。仅供学习、自用与二次开发参考；用于生产环境或对外分发前，请自行审查并充分测试。

## 项目情况
基于 `pymodbus` 的 **Modbus 扫描工具**，用于快速探测总线（Modbus TCP / RTU）上的从站设备。

- 合并了 Modbus TCP 与 Modbus RTU 两段扫描逻辑；
- 修正了 pymodbus 3.x 的兼容性：通信异常**不再抛出**，改用 `result.isError()` 判断；`NoSuchSlaveException` 已在 3.x 移除；
- 无响应/超时视为「从站不存在」静默跳过，带 `exception_code` 的异常响应记为「异常」（说明从站在线但功能/地址不支持）。

> 注：本项目**不包含任何第三方商业扫描工具**，仅含自行生成的源码。

## 功能
- 协议：Modbus TCP / Modbus RTU（串口）
- 功能码：0x03 保持寄存器(4x)、0x04 输入寄存器(3x)、0x01 线圈(0x)、0x02 离散输入(1x)
- 从站范围扫描（默认 1–247）
- 可调参数：IP/端口、串口号/波特率/校验/数据位/停止位、起始地址、数量、超时(ms)、间隔(ms)
- 结果表格 + 日志 + 一键导出 CSV（UTF-8-BOM，Excel 直接打开）
- 后台线程扫描，UI 不卡死，支持「停止」
- 单文件 EXE 发布（PyInstaller `--onefile --noconsole`）

## 目录
```
ModbusScanner/
├── modbus_scanner.py        # 源码（Tkinter GUI）
├── requirements.txt
├── .gitignore
└── dist/ModbusScanner.exe  # 构建产物（见「构建」），默认不纳入版本库
```

## 依赖
```
pymodbus>=3.0
pyinstaller>=6.0
```
（Tkinter 为 Python 标准库，无需额外安装）

## 使用（源码直接运行）
```bash
pip install pymodbus
python modbus_scanner.py
```

## 构建单文件 EXE
```bash
pip install pymodbus pyinstaller
pyinstaller --onefile --noconsole --name ModbusScanner --collect-submodules pymodbus modbus_scanner.py
# 产物位于 dist/ModbusScanner.exe
```

## 免责声明
本工具按「现状」提供，作者不对使用后果负责。请勿将其用于未授权的网络探测。
