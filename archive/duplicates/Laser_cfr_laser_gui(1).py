"""
Quantel CFR Single Shot Control - alignment workflow

Implements the manual's official Single-Shot procedure (CFR manual p. 33):
  1. Verify flashlamp is running
  2. Open shutter
  3. Send OP (Q-Switch single shot, INT mode only)

Adds:
  - Full WOR / IF1 / IF2 / IF3 / IQ interlock decoding
  - Live polling of IQ during the 8 s forced delay after flashlamp start
  - Threaded prep so the GUI does not freeze
  - Raw command/response log for debugging

Serial config per manual: 9600 8N1, no flow control, only Tx and Rx used.
Minimum inter-command delay is 150 ms. Commands terminate with CR LF.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import serial
import serial.tools.list_ports
import threading
import time
import queue


# ---------- Interlock bit definitions, straight from the manual ----------
# Each entry: (bit_label, human-readable description)
# Order matches manual: a, b, c, d, e, f, g, h

IF1_BITS = [
    ("a", "E-STOP button pressed"),
    ("b", "BNC remote interlock OPEN"),
    ("c", "Laser head thermostat OPEN"),
    ("d", "Laser head housing switch OPEN"),
    ("e", "ICE450 housing switch OPEN"),
    ("f", "Internal bus error"),
    ("g", "External bus error"),
    ("h", "Flashlamp timeout"),
]

IF2_BITS = [
    ("a", "Heater thermostat OPEN"),
    ("b", "Charger temperature OVER max"),
    ("c", "Coolant temperature UNDER min"),
    ("d", "Coolant temperature OVER max"),
    ("e", "Coolant level LOW"),
    ("f", "Coolant flow LOW"),
    ("g", "Charger / coolant / SHG temp BELOW min"),
    ("h", "Flashlamp power setting too HIGH"),
]

IF3_BITS = [
    ("a", "PSU charge error (no end of charge before fire)"),
    ("b", "Voltage over setting"),
    ("c", "No simmer sensed"),
    ("d", "External flash signal frequency too LOW"),
    ("e", "External flash signal frequency too HIGH"),
    ("f", "Capacitor discharge problem"),
    ("g", "Simmer timeout"),
    ("h", "PIV master/slave interlock mismatch"),
]

IQ_BITS = [
    ("a", "8-second forced delay after flashlamp start"),
    ("b", "Coolant temperature too LOW"),
    ("c", "Q-Switch timeout"),
    ("d", "Shutter is CLOSED"),
    ("e", "(unused)"),
    ("f", "(unused)"),
    ("g", "(unused)"),
    ("h", "(unused)"),
]


def parse_interlock_response(resp, bit_defs, prefix):
    """
    Parse a response like 'IF1 00 01 00 00' into a list of active fault names.
    The 8 bits map to a-h in order. Spaces between byte pairs are ignored.
    Returns list of human-readable fault strings (empty list = no faults).
    """
    if not resp:
        return ["(no response)"]

    # Strip the prefix and whitespace, leaving just the 8 ASCII 0/1 chars
    cleaned = resp.replace(prefix, "").replace(" ", "").strip()
    # Pull out only 0/1 characters
    bits = "".join(c for c in cleaned if c in "01")

    if len(bits) < 8:
        return [f"(malformed response: {resp!r})"]

    bits = bits[:8]
    faults = []
    for i, (label, desc) in enumerate(bit_defs):
        if bits[i] == "1":
            faults.append(f"{label}: {desc}")
    return faults


class CFRLaserGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CFR Single Shot Control")

        self.ser = None
        self.ser_lock = threading.Lock()  # serialize access from worker threads

        # State
        self.port_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Disconnected")
        self.state_var = tk.StringVar(value="Idle")
        self.last_resp_var = tk.StringVar(value="")
        self.interlock_summary_var = tk.StringVar(value="(not checked)")

        # Pump readback state
        self.pump_state_var = tk.StringVar(value="--")     # on / off
        self.pump_mode_var = tk.StringVar(value="--")      # normal / fill
        self.coolant_level_var = tk.StringVar(value="--")  # ok / low
        self.coolant_flow_var = tk.StringVar(value="--")   # lpm

        # Worker thread coordination
        self.prep_thread = None
        self.prep_cancel = threading.Event()
        self.pump_poll_active = tk.BooleanVar(value=False)

        # GUI update queue (worker threads push log messages here)
        self.log_queue = queue.Queue()

        self.build_gui()
        self.refresh_ports()
        self.poll_log_queue()

    # ============================================================
    # GUI construction
    # ============================================================
    def build_gui(self):
        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        # ---------- Connection ----------
        conn = ttk.LabelFrame(main, text="Connection", padding=6)
        conn.grid(row=0, column=0, columnspan=2, sticky="ew", pady=4)

        ttk.Label(conn, text="Port:").grid(row=0, column=0)
        self.port_box = ttk.Combobox(conn, textvariable=self.port_var, width=15)
        self.port_box.grid(row=0, column=1, padx=4)
        ttk.Button(conn, text="Refresh", command=self.refresh_ports).grid(row=0, column=2)
        ttk.Button(conn, text="Connect", command=self.connect).grid(row=0, column=3, padx=4)
        ttk.Button(conn, text="Disconnect", command=self.disconnect).grid(row=0, column=4)
        ttk.Label(conn, textvariable=self.status_var, foreground="blue").grid(row=0, column=5, padx=10)

        # ---------- Instructions ----------
        instr_frame = ttk.LabelFrame(main, text="Single-Shot Procedure (manual p. 33)", padding=6)
        instr_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        instructions = (
            "1. Confirm interlock loop is closed (e-stop out, housing closed, BNC jumper or interlock circuit)\n"
            "2. Connect to laser\n"
            "3. Click 'Check Interlocks' - resolve any faults\n"
            "4. Click 'Prep System' - waits ~9 s for flashlamp safety delay\n"
            "5. When state shows READY TO FIRE, click SINGLE SHOT\n\n"
            "Prep sequence: A (flashlamp internal) -> QI (Q-switch internal) -> SHC1 (open shutter)\n"
            "                -> poll IQ until 8-s safety delay clears -> READY"
        )
        instr = tk.Label(instr_frame, text=instructions, justify="left", font=("TkDefaultFont", 9))
        instr.grid(sticky="w")

        # ---------- Interlocks ----------
        ilk_frame = ttk.LabelFrame(main, text="Interlocks", padding=6)
        ilk_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)

        ttk.Button(ilk_frame, text="Check Interlocks (WOR + IF1/IF2/IF3/IQ)",
                   command=self.check_interlocks_async).grid(row=0, column=0, sticky="w")
        ttk.Label(ilk_frame, textvariable=self.interlock_summary_var,
                  foreground="darkgreen", wraplength=600, justify="left").grid(
            row=1, column=0, sticky="w", pady=4)

        # ---------- Pump / Coolant ----------
        pump_frame = ttk.LabelFrame(main, text="Pump & Coolant Control", padding=6)
        pump_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=4)

        # Mode controls
        ttk.Label(pump_frame, text="Mode:").grid(row=0, column=0, sticky="e", padx=2)
        ttk.Button(pump_frame, text="Normal (PMOD0)",
                   command=lambda: self.send_cmd_async("PMOD0")).grid(row=0, column=1, padx=2)
        fill_btn = ttk.Button(pump_frame, text="Fill Mode (PMOD1)",
                              command=self._enter_fill_mode)
        fill_btn.grid(row=0, column=2, padx=2)

        # Pump on/off
        ttk.Label(pump_frame, text="Pump:").grid(row=0, column=3, sticky="e", padx=(20, 2))
        ttk.Button(pump_frame, text="Pump ON (PUMP1)",
                   command=lambda: self.send_cmd_async("PUMP1")).grid(row=0, column=4, padx=2)
        ttk.Button(pump_frame, text="Pump OFF (PUMP0)",
                   command=self._confirm_pump_off).grid(row=0, column=5, padx=2)

        # Live readouts
        readout = ttk.Frame(pump_frame)
        readout.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(8, 2))

        ttk.Label(readout, text="Pump:").grid(row=0, column=0, sticky="e")
        ttk.Label(readout, textvariable=self.pump_state_var,
                  font=("TkDefaultFont", 10, "bold"),
                  foreground="blue", width=6).grid(row=0, column=1, sticky="w", padx=(2, 12))

        ttk.Label(readout, text="Mode:").grid(row=0, column=2, sticky="e")
        ttk.Label(readout, textvariable=self.pump_mode_var,
                  font=("TkDefaultFont", 10, "bold"),
                  foreground="blue", width=8).grid(row=0, column=3, sticky="w", padx=(2, 12))

        ttk.Label(readout, text="Level:").grid(row=0, column=4, sticky="e")
        self.level_label = ttk.Label(readout, textvariable=self.coolant_level_var,
                                     font=("TkDefaultFont", 10, "bold"), width=6)
        self.level_label.grid(row=0, column=5, sticky="w", padx=(2, 12))

        ttk.Label(readout, text="Flow (lpm):").grid(row=0, column=6, sticky="e")
        ttk.Label(readout, textvariable=self.coolant_flow_var,
                  font=("TkDefaultFont", 10, "bold"),
                  foreground="blue", width=8).grid(row=0, column=7, sticky="w", padx=(2, 12))

        ttk.Button(readout, text="Refresh now",
                   command=self.refresh_pump_status_async).grid(row=0, column=8, padx=4)
        ttk.Checkbutton(readout, text="Auto-poll (2 s)",
                        variable=self.pump_poll_active,
                        command=self._toggle_pump_polling).grid(row=0, column=9, padx=4)

        # Caveat about leaving pump off
        ttk.Label(pump_frame,
                  text="CAUTION: Do not leave pump OFF for long periods. ICE450 PFC supply can overheat within hours.",
                  foreground="dark red", wraplength=700, justify="left").grid(
            row=2, column=0, columnspan=6, sticky="w", pady=(4, 0))

        # ---------- Manual command buttons ----------
        cmd_frame = ttk.LabelFrame(main, text="Manual Commands", padding=6)
        cmd_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=4)

        ttk.Button(cmd_frame, text="Simmer (M)",
                   command=lambda: self.send_cmd_async("M")).grid(row=0, column=0, padx=2, pady=2)
        ttk.Button(cmd_frame, text="Flashlamp ON (A)",
                   command=lambda: self.send_cmd_async("A")).grid(row=0, column=1, padx=2, pady=2)
        ttk.Button(cmd_frame, text="Stop Flash (S)",
                   command=lambda: self.send_cmd_async("S")).grid(row=0, column=2, padx=2, pady=2)
        ttk.Button(cmd_frame, text="Q-Sw Internal (QI)",
                   command=lambda: self.send_cmd_async("QI")).grid(row=0, column=3, padx=2, pady=2)
        ttk.Button(cmd_frame, text="Stop Q-Sw (CS)",
                   command=lambda: self.send_cmd_async("CS")).grid(row=0, column=4, padx=2, pady=2)

        ttk.Button(cmd_frame, text="Open Shutter (SHC1)",
                   command=lambda: self.send_cmd_async("SHC1")).grid(row=1, column=0, padx=2, pady=2)
        ttk.Button(cmd_frame, text="Close Shutter (SHC0)",
                   command=lambda: self.send_cmd_async("SHC0")).grid(row=1, column=1, padx=2, pady=2)
        ttk.Button(cmd_frame, text="Query State (ST)",
                   command=lambda: self.send_cmd_async("ST")).grid(row=1, column=2, padx=2, pady=2)
        ttk.Button(cmd_frame, text="Status Word (WOR)",
                   command=lambda: self.send_cmd_async("WOR")).grid(row=1, column=3, padx=2, pady=2)

        # ---------- Prep / Fire ----------
        fire_frame = ttk.LabelFrame(main, text="Single-Shot Workflow", padding=6)
        fire_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=4)

        ttk.Button(fire_frame, text="Prep System",
                   command=self.start_prep, width=18).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(fire_frame, text="Stop System (safe shutdown)",
                   command=self.safe_stop, width=28).grid(row=0, column=1, padx=4, pady=4)

        self.fire_btn = tk.Button(
            fire_frame, text="SINGLE SHOT (OP)",
            command=self.single_shot,
            bg="red", fg="white", font=("Arial", 14, "bold"),
            height=2, state="disabled"
        )
        self.fire_btn.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=4)

        ttk.Label(fire_frame, text="State:").grid(row=2, column=0, sticky="e")
        self.state_label = ttk.Label(fire_frame, textvariable=self.state_var,
                                     font=("TkDefaultFont", 10, "bold"))
        self.state_label.grid(row=2, column=1, sticky="w")

        # ---------- Log ----------
        log_frame = ttk.LabelFrame(main, text="Communication Log", padding=6)
        log_frame.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=4)
        self.log = scrolledtext.ScrolledText(log_frame, height=12, width=80,
                                             font=("Courier", 9))
        self.log.grid(row=0, column=0, sticky="nsew")
        ttk.Button(log_frame, text="Clear Log",
                   command=lambda: self.log.delete("1.0", tk.END)).grid(row=1, column=0, sticky="e", pady=2)

        ttk.Label(main, textvariable=self.last_resp_var,
                  foreground="gray").grid(row=7, column=0, columnspan=2, sticky="w")

    # ============================================================
    # Logging helpers (thread-safe via queue)
    # ============================================================
    def log_msg(self, msg):
        """Push a log message; safe to call from any thread."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {msg}\n")

    def poll_log_queue(self):
        """Drain log queue into the text widget. Runs on the GUI thread."""
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log.insert(tk.END, line)
                self.log.see(tk.END)
        except queue.Empty:
            pass
        self.root.after(50, self.poll_log_queue)

    # ============================================================
    # Serial connection
    # ============================================================
    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_box["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def connect(self):
        if self.ser and self.ser.is_open:
            messagebox.showinfo("Already connected", "Disconnect first.")
            return
        try:
            self.ser = serial.Serial(
                self.port_var.get(),
                baudrate=9600,
                bytesize=8,
                parity=serial.PARITY_NONE,
                stopbits=1,
                timeout=1.0,
                write_timeout=1.0,
            )
            self.status_var.set(f"Connected ({self.port_var.get()})")
            self.log_msg(f"CONNECTED on {self.port_var.get()} @ 9600 8N1")
        except Exception as e:
            messagebox.showerror("Connection error", str(e))
            self.log_msg(f"CONNECTION FAILED: {e}")

    def disconnect(self):
        # Cancel any running prep first
        self.prep_cancel.set()
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
                self.log_msg("DISCONNECTED")
        except Exception as e:
            self.log_msg(f"Disconnect error: {e}")
        self.status_var.set("Disconnected")
        self.set_state("Idle")
        self.fire_btn.config(state="disabled")

    # ============================================================
    # Low-level serial I/O - thread-safe
    # ============================================================
    def _send_raw(self, cmd, read_timeout=0.5):
        """
        Send a command and read until CR/LF. Returns response string (decoded,
        whitespace-stripped). Returns None on error. Caller must hold ser_lock
        if called from a worker thread.
        """
        if not self.ser or not self.ser.is_open:
            self.log_msg(f"SKIP {cmd!r} - not connected")
            return None

        try:
            # Flush any stale bytes
            self.ser.reset_input_buffer()
            payload = (cmd + "\r\n").encode("ascii")
            self.ser.write(payload)
            self.ser.flush()

            # Read until we get a line terminator or timeout
            old_timeout = self.ser.timeout
            self.ser.timeout = read_timeout
            resp_bytes = self.ser.read_until(b"\r\n", size=128)
            # Some responses may not arrive fully in one read - try one more
            time.sleep(0.05)
            extra = self.ser.read(self.ser.in_waiting or 0)
            self.ser.timeout = old_timeout

            resp = (resp_bytes + extra).decode("ascii", errors="ignore").strip()
            self.log_msg(f"TX: {cmd!r:10s} RX: {resp!r}")
            return resp
        except Exception as e:
            self.log_msg(f"SERIAL ERROR on {cmd!r}: {e}")
            return None

    def send_cmd_locked(self, cmd, read_timeout=0.5):
        """Acquire the lock and send a command. Returns response or None."""
        with self.ser_lock:
            resp = self._send_raw(cmd, read_timeout=read_timeout)
            # Manual specifies 150 ms minimum between commands
            time.sleep(0.16)
        if resp is not None:
            self.last_resp_var.set(f"{cmd} -> {resp}")
        return resp

    def send_cmd_async(self, cmd):
        """Fire a single command in a background thread."""
        threading.Thread(target=self.send_cmd_locked, args=(cmd,), daemon=True).start()

    # ============================================================
    # Interlock checking
    # ============================================================
    def check_interlocks_async(self):
        threading.Thread(target=self._check_interlocks_worker, daemon=True).start()

    def _check_interlocks_worker(self):
        if not (self.ser and self.ser.is_open):
            self._set_interlock_summary("Not connected", color="red")
            return

        self.log_msg("--- Interlock check ---")

        wor = self.send_cmd_locked("WOR")
        if not wor:
            self._set_interlock_summary("WOR query failed", color="red")
            return

        # WOR format: "I a F b S c Q d"
        i_present = self._extract_wor_field(wor, "I")
        if i_present is None:
            self._set_interlock_summary(f"Could not parse WOR: {wor!r}", color="red")
            return

        if i_present == "0":
            self._set_interlock_summary(f"WOR: {wor}\nNo interlocks present.", color="darkgreen")
            self.log_msg("WOR reports no interlocks.")
            return

        # Interlocks present - query each fault byte and decode
        all_faults = []
        for cmd, prefix, bits in [
            ("IF1", "IF1", IF1_BITS),
            ("IF2", "IF2", IF2_BITS),
            ("IF3", "IF3", IF3_BITS),
            ("IQ",  "IQS", IQ_BITS),
        ]:
            resp = self.send_cmd_locked(cmd)
            if not resp:
                all_faults.append(f"{cmd}: query failed")
                continue
            faults = parse_interlock_response(resp, bits, prefix)
            if faults:
                for f in faults:
                    all_faults.append(f"{cmd}.{f}")

        if all_faults:
            summary = "INTERLOCKS PRESENT:\n  " + "\n  ".join(all_faults)
            self._set_interlock_summary(summary, color="red")
            self.log_msg(summary.replace("\n  ", " | "))
        else:
            self._set_interlock_summary(
                "WOR says interlocks present but no specific bits set "
                "(unusual - check the laser front panel).", color="orange")

    @staticmethod
    def _extract_wor_field(wor, letter):
        """
        Extract the digit following a single-letter field in a WOR response.
        WOR format: 'I 0 F 2 S 1 Q 6'
        """
        tokens = wor.replace(":", " ").split()
        for i, tok in enumerate(tokens):
            if tok == letter and i + 1 < len(tokens):
                next_tok = tokens[i + 1]
                if next_tok and next_tok[0].isdigit():
                    return next_tok[0]
        return None

    def _set_interlock_summary(self, text, color="black"):
        # Tk color update from any thread - use after()
        self.root.after(0, lambda: self.interlock_summary_var.set(text))
        self.root.after(0, lambda: self.root.update_idletasks())

    # ============================================================
    # Pump / coolant control
    # ============================================================
    def _confirm_pump_off(self):
        """Pump OFF gets a confirmation since long off-time damages the ICE450."""
        ok = messagebox.askyesno(
            "Confirm pump OFF",
            "Turning the pump OFF for extended periods can overheat the ICE450 PFC supply.\n\n"
            "Only do this briefly (e.g. while filling).\n\nProceed?")
        if ok:
            self.send_cmd_async("PUMP0")

    def _enter_fill_mode(self):
        """Set fill mode and remind the user of the workflow."""
        self.send_cmd_async("PMOD1")
        self.log_msg("Entered FILL MODE - pump will auto-cycle on coolant level. "
                     "Send PMOD0 to return to NORMAL mode after filling.")

    def refresh_pump_status_async(self):
        """Manual one-shot refresh of pump readouts."""
        threading.Thread(target=self._pump_status_worker, daemon=True).start()

    def _pump_status_worker(self):
        """Query PUMP, PMOD, LEV, FLOW. Update the display labels."""
        if not (self.ser and self.ser.is_open):
            return

        # PUMP -> "pump : on" or "pump : off"
        resp = self.send_cmd_locked("PUMP")
        if resp:
            r = resp.lower()
            if "on" in r and "off" not in r:
                self._set_pump_var(self.pump_state_var, "ON")
            elif "off" in r:
                self._set_pump_var(self.pump_state_var, "OFF")
            else:
                self._set_pump_var(self.pump_state_var, "?")

        # PMOD -> "pmod: normal" or "pmod: fill"
        resp = self.send_cmd_locked("PMOD")
        if resp:
            r = resp.lower()
            if "fill" in r:
                self._set_pump_var(self.pump_mode_var, "FILL")
            elif "normal" in r:
                self._set_pump_var(self.pump_mode_var, "NORMAL")
            else:
                self._set_pump_var(self.pump_mode_var, "?")

        # LEV -> "level: ok" or "level: low"
        resp = self.send_cmd_locked("LEV")
        if resp:
            r = resp.lower()
            if "low" in r:
                self._set_pump_var(self.coolant_level_var, "LOW")
                self.root.after(0, lambda: self.level_label.config(foreground="red"))
            elif "ok" in r:
                self._set_pump_var(self.coolant_level_var, "OK")
                self.root.after(0, lambda: self.level_label.config(foreground="darkgreen"))
            else:
                self._set_pump_var(self.coolant_level_var, "?")
                self.root.after(0, lambda: self.level_label.config(foreground="black"))

        # FLOW -> "FLOW m.nnn lpm" e.g. "FLOW 2.440"
        resp = self.send_cmd_locked("FLOW")
        if resp:
            # Pull the first numeric token after "FLOW"
            tokens = resp.replace("lpm", "").split()
            num = "?"
            for t in tokens:
                try:
                    val = float(t)
                    num = f"{val:.2f}"
                    break
                except ValueError:
                    continue
            self._set_pump_var(self.coolant_flow_var, num)

    def _set_pump_var(self, var, text):
        self.root.after(0, lambda: var.set(text))

    def _toggle_pump_polling(self):
        """Checkbox toggled - start or stop the 2 s polling loop."""
        if self.pump_poll_active.get():
            self.log_msg("Pump auto-poll: ON (every 2 s)")
            self._schedule_pump_poll()
        else:
            self.log_msg("Pump auto-poll: OFF")

    def _schedule_pump_poll(self):
        """Recurring poll - reschedules itself via root.after every 2 s."""
        if not self.pump_poll_active.get():
            return
        if self.ser and self.ser.is_open:
            threading.Thread(target=self._pump_status_worker, daemon=True).start()
        # Reschedule even if not connected, so user can connect later
        self.root.after(2000, self._schedule_pump_poll)

    # ============================================================
    # Prep sequence (threaded) with live IQ polling
    # ============================================================
    def start_prep(self):
        if not (self.ser and self.ser.is_open):
            messagebox.showerror("Not connected", "Connect to the laser first.")
            return
        if self.prep_thread and self.prep_thread.is_alive():
            messagebox.showinfo("Busy", "Prep already running.")
            return

        self.prep_cancel.clear()
        self.fire_btn.config(state="disabled")
        self.prep_thread = threading.Thread(target=self._prep_worker, daemon=True)
        self.prep_thread.start()

    def _prep_worker(self):
        try:
            self.log_msg("--- PREP SEQUENCE START ---")
            self.set_state("Checking interlocks...")

            # Pre-flight interlock check via WOR
            wor = self.send_cmd_locked("WOR")
            if not wor:
                self.set_state("Prep ABORTED (no WOR response)")
                return
            i_present = self._extract_wor_field(wor, "I")
            if i_present == "1":
                self.log_msg("WOR shows interlocks present - aborting prep.")
                self.set_state("Prep ABORTED (interlocks present)")
                self.root.after(0, lambda: messagebox.showerror(
                    "Interlock fault",
                    "Interlocks present. Click 'Check Interlocks' to see which."))
                return

            if self.prep_cancel.is_set():
                self.set_state("Prep cancelled")
                return

            # Set Q-Switch to internal sync (required for OP single-shot)
            self.set_state("Setting Q-Switch INT (QI)...")
            resp = self.send_cmd_locked("QI")
            if not resp or "INT" not in resp.upper():
                self.log_msg(f"QI did not return expected 'QS sync: INT', got: {resp!r}")
                # Continue anyway - some firmware responses vary

            # Start flashlamp in internal sync mode (also establishes simmer)
            self.set_state("Starting flashlamp (A)...")
            resp = self.send_cmd_locked("A")
            if not resp:
                self.set_state("Prep ABORTED (A command failed)")
                return
            # Expected response: "fire auto"
            if "fire auto" not in resp.lower():
                self.log_msg(f"WARNING: A response was {resp!r}, expected 'fire auto'")
                # Don't abort - the laser may still be establishing simmer

            # Open the shutter
            self.set_state("Opening shutter (SHC1)...")
            self.send_cmd_locked("SHC1")

            # Poll IQ until the 8-second forced delay clears.
            # IQ bit a = "1" means we're still in the safety delay.
            self.log_msg("Polling IQ for 8-s safety delay clearance...")
            t0 = time.time()
            timeout_s = 15.0  # generous - the delay is 8 s
            poll_interval = 0.4
            cleared = False

            while time.time() - t0 < timeout_s:
                if self.prep_cancel.is_set():
                    self.set_state("Prep cancelled")
                    return

                elapsed = time.time() - t0
                self.set_state(f"Waiting for safety delay... {elapsed:.1f} s")

                resp = self.send_cmd_locked("IQ")
                if resp:
                    # Parse same way as the IF bytes
                    faults = parse_interlock_response(resp, IQ_BITS, "IQS")
                    # bit a description starts with "8-second"
                    delay_active = any("8-second" in f for f in faults)
                    other_faults = [f for f in faults if "8-second" not in f and "(unused)" not in f]

                    if other_faults:
                        # Some other Q-switch interlock - shutter closed, coolant cold, etc.
                        self.log_msg(f"Q-Switch interlocks during prep: {other_faults}")
                        # 'Shutter is CLOSED' will be expected briefly if SHC1 hasn't taken effect yet.
                        # Filter that out for a moment, but flag others.
                        critical = [f for f in other_faults if "Shutter" not in f]
                        if critical:
                            self.set_state(f"Prep ABORTED (Q-Sw fault: {critical})")
                            self.root.after(0, lambda c=critical: messagebox.showerror(
                                "Q-Switch interlock", "\n".join(c)))
                            return

                    if not delay_active:
                        cleared = True
                        break

                time.sleep(poll_interval)

            if not cleared:
                self.set_state("Prep ABORTED (timeout waiting for safety delay)")
                self.log_msg("IQ never reported safety delay cleared within 15 s.")
                return

            # Final state verification
            self.set_state("Verifying ready state...")
            st = self.send_cmd_locked("ST")
            self.log_msg(f"Final state string: {st!r}")

            self.set_state("READY TO FIRE")
            self.root.after(0, lambda: self.fire_btn.config(state="normal"))
            self.log_msg("--- PREP COMPLETE ---")

        except Exception as e:
            self.log_msg(f"PREP EXCEPTION: {e}")
            self.set_state(f"Prep error: {e}")

    # ============================================================
    # Fire
    # ============================================================
    def single_shot(self):
        if self.state_var.get() != "READY TO FIRE":
            messagebox.showwarning("Not ready", "Run Prep System first.")
            return

        confirm = messagebox.askyesno(
            "Confirm fire",
            "Eyewear on?\nBeam path clear?\nInterlocks closed?\n\nFire single shot now?"
        )
        if not confirm:
            return

        self.set_state("FIRING")
        self.fire_btn.config(state="disabled")
        threading.Thread(target=self._fire_worker, daemon=True).start()

    def _fire_worker(self):
        resp = self.send_cmd_locked("OP")
        self.log_msg(f"FIRE command (OP) sent. Response: {resp!r}")
        # After single shot the laser stays in fire-auto-qs but Q-switch
        # in single mode (per IQ docs). User should re-prep / cycle for next shot.
        self.set_state("SHOT FIRED - re-prep for another shot")

    # ============================================================
    # Stop
    # ============================================================
    def safe_stop(self):
        self.prep_cancel.set()
        threading.Thread(target=self._stop_worker, daemon=True).start()

    def _stop_worker(self):
        self.log_msg("--- SAFE STOP ---")
        self.send_cmd_locked("CS")     # stop Q-switch
        self.send_cmd_locked("S")      # stop flashlamp + simmer
        self.send_cmd_locked("SHC0")   # close shutter
        self.set_state("Stopped")
        self.root.after(0, lambda: self.fire_btn.config(state="disabled"))

    # ============================================================
    # State helpers
    # ============================================================
    def set_state(self, text):
        self.root.after(0, lambda: self.state_var.set(text))


def main():
    root = tk.Tk()
    app = CFRLaserGUI(root)

    def on_close():
        app.prep_cancel.set()
        try:
            if app.ser and app.ser.is_open:
                app.ser.close()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
