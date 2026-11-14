import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import time


class CFRLaserGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CFR Single Shot Control")

        self.ser = None
        self.port_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Disconnected")
        self.response_var = tk.StringVar(value="")
        self.state_var = tk.StringVar(value="Idle")

        self.build_gui()
        self.refresh_ports()

    def build_gui(self):
        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        # ---------- CONNECTION ----------
        ttk.Label(main, text="Serial Port").grid(row=0, column=0)
        self.port_box = ttk.Combobox(main, textvariable=self.port_var, width=15)
        self.port_box.grid(row=0, column=1)

        ttk.Button(main, text="Refresh", command=self.refresh_ports).grid(row=0, column=2)
        ttk.Button(main, text="Connect", command=self.connect).grid(row=0, column=3)
        ttk.Button(main, text="Disconnect", command=self.disconnect).grid(row=0, column=4)

        ttk.Separator(main).grid(row=1, column=0, columnspan=5, sticky="ew", pady=8)

        # ---------- HOW TO FIRE ----------
        instructions = (
            "HOW TO FIRE SINGLE SHOT:\n\n"
            "1. Ensure interlock is CLOSED\n"
            "2. Connect to laser\n"
            "3. Click 'Prep System'\n"
            "4. Wait for system to stabilize\n"
            "5. Press SINGLE SHOT\n\n"
            "Sequence performed automatically:\n"
            "- Simmer flashlamp (M)\n"
            "- Enable flashlamp (A)\n"
            "- Set Q-switch internal (QI)\n"
            "- Open shutter (SHC1)\n"
            "- Fire (OP)\n"
        )

        instr_box = tk.Text(main, height=10, width=60)
        instr_box.insert("1.0", instructions)
        instr_box.config(state="disabled")
        instr_box.grid(row=2, column=0, columnspan=5, pady=5)

        ttk.Separator(main).grid(row=3, column=0, columnspan=5, sticky="ew", pady=8)

        # ---------- CONTROL ----------
        ttk.Button(main, text="Prep System", command=self.prep_system).grid(row=4, column=0, sticky="ew")
        ttk.Button(main, text="Stop System", command=self.safe_stop).grid(row=4, column=1, sticky="ew")

        ttk.Button(main, text="Open Shutter", command=lambda: self.send_cmd("SHC1")).grid(row=5, column=0)
        ttk.Button(main, text="Close Shutter", command=lambda: self.send_cmd("SHC0")).grid(row=5, column=1)

        ttk.Button(main, text="Simmer", command=lambda: self.send_cmd("M")).grid(row=5, column=2)
        ttk.Button(main, text="Flashlamp ON", command=lambda: self.send_cmd("A")).grid(row=5, column=3)

        fire_btn = tk.Button(
            main,
            text="SINGLE SHOT",
            command=self.single_shot,
            bg="red",
            fg="white",
            font=("Arial", 14, "bold"),
            height=2
        )
        fire_btn.grid(row=6, column=0, columnspan=5, sticky="ew", pady=10)

        ttk.Separator(main).grid(row=7, column=0, columnspan=5, sticky="ew", pady=8)

        # ---------- STATUS ----------
        ttk.Label(main, text="State:").grid(row=8, column=0)
        ttk.Label(main, textvariable=self.state_var).grid(row=8, column=1)

        ttk.Label(main, text="Connection:").grid(row=9, column=0)
        ttk.Label(main, textvariable=self.status_var).grid(row=9, column=1)

        ttk.Label(main, text="Last Response:").grid(row=10, column=0)
        ttk.Label(main, textvariable=self.response_var, wraplength=500).grid(row=10, column=1, columnspan=4)

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_box["values"] = ports
        if ports:
            self.port_var.set(ports[0])

    def connect(self):
        try:
            self.ser = serial.Serial(self.port_var.get(), 9600, timeout=1)
            self.status_var.set("Connected")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def disconnect(self):
        if self.ser:
            self.ser.close()
        self.status_var.set("Disconnected")

    def send_cmd(self, cmd):
        if not self.ser or not self.ser.is_open:
            return

        try:
            self.ser.write((cmd + "\r\n").encode())
            time.sleep(0.2)
            resp = self.ser.read_all().decode(errors="ignore")
            self.response_var.set(f"{cmd} -> {resp}")
        except Exception as e:
            messagebox.showerror("Serial Error", str(e))

    # ---------- PREP ----------
    def prep_system(self):
        self.state_var.set("Preparing...")
        self.root.update()

        self.send_cmd("M")      # simmer
        time.sleep(0.5)

        self.send_cmd("A")      # flashlamp on
        time.sleep(0.5)

        self.send_cmd("QI")     # Q-switch internal
        time.sleep(0.3)

        self.send_cmd("SHC1")   # open shutter
        time.sleep(3)

        self.state_var.set("READY TO FIRE")

    # ---------- FIRE ----------
    def single_shot(self):
        if self.state_var.get() != "READY TO FIRE":
            messagebox.showwarning("Not Ready", "Run PREP SYSTEM first")
            return

        confirm = messagebox.askyesno(
            "Confirm Fire",
            "Confirm eyewear, beam path, and interlocks are safe."
        )
        if not confirm:
            return

        self.state_var.set("FIRING")
        self.root.update()

        self.send_cmd("OP")

        self.state_var.set("SHOT FIRED")

    # ---------- STOP ----------
    def safe_stop(self):
        self.send_cmd("CS")
        time.sleep(0.2)
        self.send_cmd("S")
        time.sleep(0.2)
        self.send_cmd("SHC0")
        self.state_var.set("Stopped")


if __name__ == "__main__":
    root = tk.Tk()
    app = CFRLaserGUI(root)
    root.mainloop()