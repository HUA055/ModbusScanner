#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modbus 扫描工具 (TCP / RTU)
基于 pymodbus 3.x，支持保持/输入寄存器、线圈、离散输入扫描。
合并了两段示例代码（Modbus TCP 与 Modbus RTU 扫描），并修正了
pymodbus 3.x 下「异常不抛、改用 result.isError() 判断」的兼容问题。
"""
import threading
import queue
import time
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from pymodbus.exceptions import ModbusException


# ---------- 功能码映射 ----------
FUNC_MAP = {
    "0x03 保持寄存器 (4x)": ("read_holding_registers", "registers"),
    "0x04 输入寄存器 (3x)": ("read_input_registers", "registers"),
    "0x01 线圈 (0x)": ("read_coils", "bits"),
    "0x02 离散输入 (1x)": ("read_discrete_inputs", "bits"),
}


def build_client(mode, cfg):
    if mode == "TCP":
        return ModbusTcpClient(host=cfg["host"], port=cfg["port"], timeout=cfg["timeout"])
    return ModbusSerialClient(
        port=cfg["port"],
        baudrate=cfg["baudrate"],
        bytesize=cfg["bytesize"],
        parity=cfg["parity"],
        stopbits=cfg["stopbits"],
        timeout=cfg["timeout"],
    )


def read_one(client, func_name, address, count, slave):
    """返回 (status, payload_str, note)，status ∈ {ok, exception, noresp}"""
    method = getattr(client, func_name)
    result = method(address=address, count=count, slave=slave)
    if result.isError():
        code = getattr(result, "exception_code", None)
        if code is not None:
            return "exception", f"异常 0x{code:02X}", "从站存在但功能/地址不支持"
        return "noresp", "无响应", ""
    if func_name.endswith("registers"):
        regs = list(result.registers[:count])
        val = ", ".join(str(r) for r in regs)
        note = "HEX: " + ", ".join(f"0x{r:04X}" for r in regs)
        return "ok", val, note
    bits = list(result.bits[:count])
    val = "".join("1" if b else "0" for b in bits)
    return "ok", val, ""


class ScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Modbus 扫描工具  v1.0")
        self.root.geometry("920x700")
        self.scanning = False
        self.stop_event = threading.Event()
        self.q = queue.Queue()
        self.results = []
        self._build_ui()
        self.root.after(100, self._poll_queue)

    # ---------------- UI ----------------
    def _build_ui(self):
        f_mode = ttk.LabelFrame(self.root, text="协议模式", padding=8)
        f_mode.pack(fill="x", padx=10, pady=6)
        self.mode = tk.StringVar(value="TCP")
        ttk.Radiobutton(f_mode, text="Modbus TCP", variable=self.mode, value="TCP",
                        command=self._toggle_mode).pack(side="left", padx=8)
        ttk.Radiobutton(f_mode, text="Modbus RTU (串口)", variable=self.mode, value="RTU",
                        command=self._toggle_mode).pack(side="left", padx=8)

        f_conn = ttk.LabelFrame(self.root, text="连接参数", padding=8)
        f_conn.pack(fill="x", padx=10, pady=4)

        self.f_tcp = ttk.Frame(f_conn)
        ttk.Label(self.f_tcp, text="IP 地址:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        self.host = ttk.Entry(self.f_tcp, width=18); self.host.insert(0, "127.0.0.1")
        self.host.grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(self.f_tcp, text="端口:").grid(row=0, column=2, sticky="e", padx=4, pady=2)
        self.port = ttk.Entry(self.f_tcp, width=8); self.port.insert(0, "502")
        self.port.grid(row=0, column=3, padx=4, pady=2)

        self.f_rtu = ttk.Frame(f_conn)
        ttk.Label(self.f_rtu, text="串口号:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        self.com = ttk.Entry(self.f_rtu, width=10); self.com.insert(0, "COM1")
        self.com.grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(self.f_rtu, text="波特率:").grid(row=0, column=2, sticky="e", padx=4, pady=2)
        self.baud = ttk.Entry(self.f_rtu, width=10); self.baud.insert(0, "9600")
        self.baud.grid(row=0, column=3, padx=4, pady=2)
        ttk.Label(self.f_rtu, text="校验:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        self.parity = ttk.Combobox(self.f_rtu, width=8, values=["N", "E", "O"], state="readonly")
        self.parity.set("N"); self.parity.grid(row=1, column=1, padx=4, pady=2)
        ttk.Label(self.f_rtu, text="数据位:").grid(row=1, column=2, sticky="e", padx=4, pady=2)
        self.bytesize = ttk.Entry(self.f_rtu, width=8); self.bytesize.insert(0, "8")
        self.bytesize.grid(row=1, column=3, padx=4, pady=2)
        ttk.Label(self.f_rtu, text="停止位:").grid(row=1, column=4, sticky="e", padx=4, pady=2)
        self.stopbits = ttk.Entry(self.f_rtu, width=8); self.stopbits.insert(0, "1")
        self.stopbits.grid(row=1, column=5, padx=4, pady=2)

        self.f_tcp.pack(fill="x")
        self.f_rtu.pack(fill="x")
        self._toggle_mode()

        f_scan = ttk.LabelFrame(self.root, text="扫描参数", padding=8)
        f_scan.pack(fill="x", padx=10, pady=4)
        r = 0
        ttk.Label(f_scan, text="功能码:").grid(row=r, column=0, sticky="e", padx=4, pady=2)
        self.func = ttk.Combobox(f_scan, width=24, values=list(FUNC_MAP.keys()), state="readonly")
        self.func.set(list(FUNC_MAP.keys())[0]); self.func.grid(row=r, column=1, padx=4, pady=2)
        ttk.Label(f_scan, text="起始地址(0基):").grid(row=r, column=2, sticky="e", padx=4, pady=2)
        self.addr = ttk.Entry(f_scan, width=10); self.addr.insert(0, "0")
        self.addr.grid(row=r, column=3, padx=4, pady=2)
        ttk.Label(f_scan, text="数量:").grid(row=r, column=4, sticky="e", padx=4, pady=2)
        self.count = ttk.Entry(f_scan, width=8); self.count.insert(0, "1")
        self.count.grid(row=r, column=5, padx=4, pady=2)
        r += 1
        ttk.Label(f_scan, text="从站起:").grid(row=r, column=0, sticky="e", padx=4, pady=2)
        self.sstart = ttk.Entry(f_scan, width=8); self.sstart.insert(0, "1")
        self.sstart.grid(row=r, column=1, padx=4, pady=2)
        ttk.Label(f_scan, text="从站止:").grid(row=r, column=2, sticky="e", padx=4, pady=2)
        self.send = ttk.Entry(f_scan, width=8); self.send.insert(0, "247")
        self.send.grid(row=r, column=3, padx=4, pady=2)
        ttk.Label(f_scan, text="超时(ms):").grid(row=r, column=4, sticky="e", padx=4, pady=2)
        self.timeout = ttk.Entry(f_scan, width=8); self.timeout.insert(0, "300")
        self.timeout.grid(row=r, column=5, padx=4, pady=2)
        r += 1
        ttk.Label(f_scan, text="间隔(ms):").grid(row=r, column=0, sticky="e", padx=4, pady=2)
        self.interval = ttk.Entry(f_scan, width=8); self.interval.insert(0, "100")
        self.interval.grid(row=r, column=1, padx=4, pady=2)
        ttk.Label(f_scan, text="提示: 40001→地址0, 40002→地址1").grid(
            row=r, column=2, columnspan=4, sticky="w", padx=4, pady=2)

        f_btn = ttk.Frame(self.root)
        f_btn.pack(fill="x", padx=10, pady=4)
        self.btn_start = ttk.Button(f_btn, text="开始扫描", command=self.start_scan)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(f_btn, text="停止", command=self.stop_scan, state="disabled")
        self.btn_stop.pack(side="left", padx=4)
        self.btn_export = ttk.Button(f_btn, text="导出CSV", command=self.export_csv)
        self.btn_export.pack(side="left", padx=4)
        self.btn_clear = ttk.Button(f_btn, text="清空", command=self.clear_results)
        self.btn_clear.pack(side="left", padx=4)

        f_res = ttk.LabelFrame(self.root, text="扫描结果", padding=8)
        f_res.pack(fill="both", expand=True, padx=10, pady=4)
        cols = ("slave", "status", "value", "note")
        self.tree = ttk.Treeview(f_res, columns=cols, show="headings", height=12)
        self.tree.heading("slave", text="从站地址")
        self.tree.heading("status", text="状态")
        self.tree.heading("value", text="数值")
        self.tree.heading("note", text="备注")
        self.tree.column("slave", width=90)
        self.tree.column("status", width=110)
        self.tree.column("value", width=220)
        self.tree.column("note", width=320)
        vsb = ttk.Scrollbar(f_res, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        f_log = ttk.LabelFrame(self.root, text="日志", padding=6)
        f_log.pack(fill="x", padx=10, pady=4)
        self.log = scrolledtext.ScrolledText(f_log, height=6, state="disabled")
        self.log.pack(fill="both")

        self.status = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w").pack(
            fill="x", side="bottom")

    def _toggle_mode(self):
        if self.mode.get() == "TCP":
            self.f_rtu.pack_forget()
            self.f_tcp.pack(fill="x")
        else:
            self.f_tcp.pack_forget()
            self.f_rtu.pack(fill="x")

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _poll_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "row":
                    self._add_row(item[1])
                elif item[0] == "log":
                    self._log(item[1])
                elif item[0] == "done":
                    self._scan_finished(item[1])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _add_row(self, row):
        self.results.append(row)
        self.tree.insert("", "end", values=row)

    # ---------------- 控制 ----------------
    def start_scan(self):
        if self.scanning:
            return
        try:
            cfg = self._collect_cfg()
        except ValueError as e:
            messagebox.showerror("参数错误", str(e))
            return
        self.scanning = True
        self.stop_event.clear()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.clear_results()
        self.status.set("扫描中…")
        threading.Thread(target=self._run_scan, args=(cfg,), daemon=True).start()

    def _collect_cfg(self):
        mode = self.mode.get()
        timeout = float(self.timeout.get()) / 1000.0
        interval = float(self.interval.get()) / 1000.0
        sstart = int(self.sstart.get())
        send = int(self.send.get())
        if not (1 <= sstart <= send <= 247):
            raise ValueError("从站范围需在 1–247 之间")
        address = int(self.addr.get())
        count = int(self.count.get())
        if address < 0 or count < 1:
            raise ValueError("地址需≥0，数量需≥1")
        func_name, _ = FUNC_MAP[self.func.get()]
        if mode == "TCP":
            cfg = {"host": self.host.get().strip(), "port": int(self.port.get()),
                   "timeout": timeout}
        else:
            cfg = {"port": self.com.get().strip(), "baudrate": int(self.baud.get()),
                   "parity": self.parity.get(), "bytesize": int(self.bytesize.get()),
                   "stopbits": int(self.stopbits.get()), "timeout": timeout}
        cfg.update({"mode": mode, "func": func_name, "address": address,
                    "count": count, "sstart": sstart, "send": send, "interval": interval})
        return cfg

    def _run_scan(self, cfg):
        client = None
        try:
            client = build_client(cfg["mode"], cfg)
            if not client.connect():
                self.q.put(("log", "连接失败，请检查参数 / 端口是否被占用。"))
                self.q.put(("done", False))
                return
            self.q.put(("log", f"已连接 ({cfg['mode']})，扫描 {cfg['sstart']}–{cfg['send']} …"))
            found = 0
            for slave in range(cfg["sstart"], cfg["send"] + 1):
                if self.stop_event.is_set():
                    self.q.put(("log", "用户已停止。"))
                    break
                try:
                    status, value, note = read_one(client, cfg["func"], cfg["address"],
                                                  cfg["count"], slave)
                    if status == "ok":
                        self.q.put(("row", (str(slave), "在线", value, note)))
                        found += 1
                    elif status == "exception":
                        self.q.put(("row", (str(slave), "异常", value, note)))
                    # noresp：从站无响应，视为不存在，跳过
                except ModbusException:
                    pass  # 无响应/超时：从站不存在
                except Exception as e:
                    self.q.put(("row", (str(slave), "错误", str(e)[:40], "")))
                if cfg["interval"] > 0:
                    time.sleep(cfg["interval"])
            self.q.put(("log", f"扫描结束，命中（在线+异常）从站：{found}"))
            self.q.put(("done", True))
        except Exception as e:
            self.q.put(("log", f"严重错误: {e}"))
            self.q.put(("done", False))
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    def _scan_finished(self, ok):
        self.scanning = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.status.set("完成" if ok else "异常结束")

    def stop_scan(self):
        self.stop_event.set()

    def clear_results(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results = []

    def export_csv(self):
        if not self.results:
            messagebox.showinfo("提示", "暂无结果可导出。")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["从站地址", "状态", "数值", "备注"])
                for r in self.results:
                    w.writerow(r)
            messagebox.showinfo("已保存", path)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))


def main():
    root = tk.Tk()
    try:
        ScannerApp(root)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("启动失败", str(e))


if __name__ == "__main__":
    main()
