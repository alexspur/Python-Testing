"""
Quantel CFR Laser Control - alignment + external-trigger workflow

Supports two operating modes:
  INT/INT  - laser fires via the GUI's SINGLE SHOT button (OP command).
             Use for alignment, beam path checks, energy measurements.

  EXT/EXT  - DG535 (or any external delay generator) drives Lamp In and
             Q-Switch In on the ICE450 front panel. Laser stays armed and
             fires on every external pulse pair.
             Use for synchronized pulsed-power experiments.

EXT/EXT prep sequence:
    QE       Q-switch -> external sync
    BYPASS1  flashlamp -> 0.5 us delay instead of 500 us
    E        flashlamp -> fire ext
    SHC1     open shutter
    [wait 8 s for IQ safety delay]
    CC       arm Q-switch (will then fire on Q-Switch In rising edge)

INT/INT prep sequence (manual page 33):
    QI       Q-switch -> internal sync
    A        flashlamp -> fire auto
    SHC1     open shutter
    [wait 8 s for IQ safety delay]
    -> READY (use OP to fire single shot)

Also includes:
  - Full WOR / IF1 / IF2 / IF3 / IQ interlock decoding
  - Live polling of IQ during the 8 s forced delay after flashlamp start
  - Threaded prep so the GUI does not freeze
  - Raw command/response log for debugging
  - Empirical interlock clear attempt (no documented RS-232 method exists,
    but state-transition commands sometimes work)
  - Free-form custom RS-232 command entry

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

    cleaned = resp.replace(prefix, "").replace(" ", "").strip()
    bits = "".join(c for c in cleaned if c in "01")

    if len(bits) < 8:
        return [f"(malformed response: {resp!r})"]

    bits = bits[:8]
    faults = []
    for i, (label, desc) in enumerate(bit_defs):
        if bits[i] == "1":
            faults.append(f"{label}: {desc}")
    return faults


class CFRLaserPanel:
    """A fully self-contained control panel for one CFR laser.

    Each instance owns its own serial connection, log, worker threads and
    Tk variables, so multiple panels can run side by side (e.g. one per
    laser) with independent connect/disconnect and controls.

    root  - the Toplevel/Tk, used only for .after() scheduling and dialogs.
    parent- the container frame this panel builds its widgets into.
    name  - display name for this laser (used in the log / dialogs).
    default_port - preferred COM port to preselect if present.
    """

    def __init__(self, root, parent, name="Laser", default_port=None):
        self.root = root
        self.parent = parent
        self.name = name
        self.default_port = default_port

        self.ser = None
        self.ser_lock = threading.Lock()  # serialize access from worker threads

        # State
        self.port_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Disconnected")
        self.state_var = tk.StringVar(value="Idle")
        self.last_resp_var = tk.StringVar(value="")
        self.interlock_summary_var = tk.StringVar(value="(not checked)")

        # Trigger mode: "INT/INT" for alignment, "EXT/EXT" for DG535-driven
        self.trigger_mode_var = tk.StringVar(value="INT/INT")

        # Pump readback state
        self.pump_state_var = tk.StringVar(value="--")
        self.pump_mode_var = tk.StringVar(value="--")
        self.coolant_level_var = tk.StringVar(value="--")
        self.coolant_flow_var = tk.StringVar(value="--")

        # Custom command input
        self.custom_cmd_var = tk.StringVar()
        self.custom_resp_var = tk.StringVar(value="(no command sent yet)")

        # Worker thread coordination
        self.prep_thread = None
        self.prep_cancel = threading.Event()
        self.pump_poll_active = tk.BooleanVar(value=False)

        # GUI update queue
        self.log_queue = queue.Queue()

        self.build_gui()
        self.refresh_ports()
        self.poll_log_queue()

    # ============================================================
    # GUI construction
    # ============================================================
    def build_gui(self):
        # Build everything inside the panel's container frame so multiple
        # panels can coexist. The container is made to expand.
        self.parent.rowconfigure(0, weight=1)
        self.parent.columnconfigure(0, weight=1)

        main = ttk.Frame(self.parent, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        # Scrollable container so the bottom controls remain reachable when the
        # window is shorter than the full content height (fullscreen on small
        # displays, scaled HiDPI, etc.).
        left_container = ttk.Frame(main)
        left_container.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left_container.rowconfigure(0, weight=1)
        left_container.columnconfigure(0, weight=1)

        self.left_canvas = tk.Canvas(left_container, highlightthickness=0,
                                     borderwidth=0)
        self.left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scroll = ttk.Scrollbar(left_container, orient="vertical",
                                    command=self.left_canvas.yview)
        left_scroll.grid(row=0, column=1, sticky="ns")
        self.left_canvas.configure(yscrollcommand=left_scroll.set)

        left = ttk.Frame(self.left_canvas)
        self._left_window = self.left_canvas.create_window(
            (0, 0), window=left, anchor="nw")

        def _on_left_configure(_event):
            self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))
        left.bind("<Configure>", _on_left_configure)

        def _on_canvas_configure(event):
            self.left_canvas.itemconfigure(self._left_window, width=event.width)
        self.left_canvas.bind("<Configure>", _on_canvas_configure)

        # Mousewheel scrolls the left pane only while the cursor is over it,
        # so the log's own scrollbar still works.
        def _on_mousewheel(event):
            self.left_canvas.yview_scroll(int(-event.delta / 120), "units")
        self.left_canvas.bind("<Enter>",
                              lambda _e: self.left_canvas.bind_all(
                                  "<MouseWheel>", _on_mousewheel))
        self.left_canvas.bind("<Leave>",
                              lambda _e: self.left_canvas.unbind_all(
                                  "<MouseWheel>"))

        left.columnconfigure(0, weight=1)
        left.columnconfigure(1, weight=1)

        # ---------- Connection ----------
        conn = ttk.LabelFrame(left, text="Connection", padding=6)
        conn.grid(row=0, column=0, columnspan=2, sticky="ew", pady=4)
        conn.columnconfigure(5, weight=1)

        ttk.Label(conn, text="Port:").grid(row=0, column=0)
        self.port_box = ttk.Combobox(conn, textvariable=self.port_var, width=15)
        self.port_box.grid(row=0, column=1, padx=4)
        ttk.Button(conn, text="Refresh", command=self.refresh_ports).grid(row=0, column=2)
        ttk.Button(conn, text="Connect", command=self.connect).grid(row=0, column=3, padx=4)
        ttk.Button(conn, text="Disconnect", command=self.disconnect).grid(row=0, column=4)
        ttk.Label(conn, textvariable=self.status_var, foreground="blue").grid(row=0, column=5, padx=10)

        # ---------- Instructions ----------
        instr_frame = ttk.LabelFrame(left, text="Workflow Cheat Sheet", padding=6)
        instr_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        instructions = (
            "INT/INT mode (manual single shot, manual p. 33):\n"
            "  Connect -> Check Interlocks -> select INT/INT -> Prep System -> SINGLE SHOT\n"
            "  Sends: QI, A, SHC1, [8 s safety delay], OP (per click)\n\n"
            "EXT/EXT mode (DG535 drives Lamp In + Q-Switch In):\n"
            "  Connect -> Check Interlocks -> select EXT/EXT -> Prep System\n"
            "  Sends: QE, BYPASS1, E, SHC1, [8 s safety delay], CC\n"
            "  Once ARMED, every DG535 trigger pair fires one shot. SINGLE SHOT button\n"
            "  becomes a status-check (laser fires from DG535, not from the GUI)."
        )
        instr = tk.Label(instr_frame, text=instructions, justify="left", font=("TkDefaultFont", 9))
        instr.grid(sticky="w")

        # ---------- Interlocks ----------
        ilk_frame = ttk.LabelFrame(left, text="Interlocks", padding=6)
        ilk_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        ilk_frame.columnconfigure(0, weight=1)
        ilk_frame.columnconfigure(1, weight=1)

        ttk.Button(ilk_frame, text="Check Interlocks (WOR + IF1/IF2/IF3/IQ)",
                   command=self.check_interlocks_async).grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(ilk_frame, text="Attempt Clear (empirical)",
                   command=self.attempt_clear_interlocks_async).grid(row=0, column=1, sticky="ew", padx=2)
        self.interlock_label = ttk.Label(
            ilk_frame, textvariable=self.interlock_summary_var,
            foreground="darkgreen", wraplength=600, justify="left")
        self.interlock_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)
        ilk_frame.bind(
            "<Configure>",
            lambda e: self.interlock_label.configure(wraplength=max(200, e.width - 20)),
        )

        # ---------- Pump / Coolant ----------
        pump_frame = ttk.LabelFrame(left, text="Pump & Coolant Control", padding=6)
        pump_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=4)
        for c in range(6):
            pump_frame.columnconfigure(c, weight=1)

        ttk.Label(pump_frame, text="Mode:").grid(row=0, column=0, sticky="e", padx=2)
        ttk.Button(pump_frame, text="Normal (PMOD0)",
                   command=lambda: self.send_cmd_async("PMOD0")).grid(row=0, column=1, padx=2)
        ttk.Button(pump_frame, text="Fill Mode (PMOD1)",
                   command=self._enter_fill_mode).grid(row=0, column=2, padx=2)

        ttk.Label(pump_frame, text="Pump:").grid(row=0, column=3, sticky="e", padx=(20, 2))
        ttk.Button(pump_frame, text="Pump ON (PUMP1)",
                   command=lambda: self.send_cmd_async("PUMP1")).grid(row=0, column=4, padx=2)
        ttk.Button(pump_frame, text="Pump OFF (PUMP0)",
                   command=self._confirm_pump_off).grid(row=0, column=5, padx=2)

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

        self.pump_caution_label = ttk.Label(
            pump_frame,
            text="CAUTION: Do not leave pump OFF for long periods. ICE450 PFC supply can overheat within hours.",
            foreground="dark red", wraplength=700, justify="left")
        self.pump_caution_label.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(4, 0))
        pump_frame.bind(
            "<Configure>",
            lambda e: self.pump_caution_label.configure(wraplength=max(300, e.width - 20)),
        )

        # ---------- Manual command buttons ----------
        cmd_frame = ttk.LabelFrame(left, text="Manual Commands", padding=6)
        cmd_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=4)
        for c in range(5):
            cmd_frame.columnconfigure(c, weight=1)

        ttk.Button(cmd_frame, text="Simmer (M)",
                   command=lambda: self.send_cmd_async("M")).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="Flash INT (A)",
                   command=lambda: self.send_cmd_async("A")).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="Flash EXT (E)",
                   command=lambda: self.send_cmd_async("E")).grid(row=0, column=2, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="Stop Flash (S)",
                   command=lambda: self.send_cmd_async("S")).grid(row=0, column=3, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="Q-Sw INT (QI)",
                   command=lambda: self.send_cmd_async("QI")).grid(row=0, column=4, padx=2, pady=2, sticky="ew")

        ttk.Button(cmd_frame, text="Q-Sw EXT (QE)",
                   command=lambda: self.send_cmd_async("QE")).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="Arm Q-Sw (CC)",
                   command=lambda: self.send_cmd_async("CC")).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="Stop Q-Sw (CS)",
                   command=lambda: self.send_cmd_async("CS")).grid(row=1, column=2, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="BYPASS ON (1)",
                   command=lambda: self.send_cmd_async("BYPASS1")).grid(row=1, column=3, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="BYPASS OFF (0)",
                   command=lambda: self.send_cmd_async("BYPASS0")).grid(row=1, column=4, padx=2, pady=2, sticky="ew")

        ttk.Button(cmd_frame, text="Open Shutter (SHC1)",
                   command=lambda: self.send_cmd_async("SHC1")).grid(row=2, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="Close Shutter (SHC0)",
                   command=lambda: self.send_cmd_async("SHC0")).grid(row=2, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="Query State (ST)",
                   command=lambda: self.send_cmd_async("ST")).grid(row=2, column=2, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="Status Word (WOR)",
                   command=lambda: self.send_cmd_async("WOR")).grid(row=2, column=3, padx=2, pady=2, sticky="ew")
        ttk.Button(cmd_frame, text="First Interlock (IF)",
                   command=lambda: self.send_cmd_async("IF")).grid(row=2, column=4, padx=2, pady=2, sticky="ew")

        # ---------- Custom RS-232 command ----------
        custom_frame = ttk.LabelFrame(left, text="Custom RS-232 Command", padding=6)
        custom_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=4)
        custom_frame.columnconfigure(1, weight=1)

        ttk.Label(custom_frame, text="Command:").grid(row=0, column=0, sticky="e", padx=2)
        self.custom_entry = ttk.Entry(custom_frame, textvariable=self.custom_cmd_var,
                                      font=("Courier", 10))
        self.custom_entry.grid(row=0, column=1, sticky="ew", padx=2)
        self.custom_entry.bind("<Return>", lambda e: self._send_custom_cmd())
        ttk.Button(custom_frame, text="Send", command=self._send_custom_cmd).grid(
            row=0, column=2, padx=2)

        ttk.Label(custom_frame, text="Response:").grid(row=1, column=0, sticky="ne", padx=2, pady=(4, 0))
        ttk.Label(custom_frame, textvariable=self.custom_resp_var,
                  foreground="darkblue", font=("Courier", 10),
                  wraplength=600, justify="left").grid(
            row=1, column=1, columnspan=2, sticky="ew", pady=(4, 0))

        ttk.Label(custom_frame,
                  text="Type any command from the manual (e.g. CGT, T3, X, V, EJ100). "
                       "CR/LF is added automatically.",
                  foreground="gray", font=("TkDefaultFont", 8), justify="left",
                  wraplength=600).grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 0))

        # ---------- Trigger Mode + Prep / Fire ----------
        fire_frame = ttk.LabelFrame(left, text="Trigger Mode + Workflow", padding=6)
        fire_frame.grid(row=6, column=0, columnspan=2, sticky="ew", pady=4)
        fire_frame.columnconfigure(0, weight=1)
        fire_frame.columnconfigure(1, weight=1)

        # Trigger mode selector
        mode_sub = ttk.Frame(fire_frame)
        mode_sub.grid(row=0, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Label(mode_sub, text="Trigger mode:",
                  font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Radiobutton(mode_sub, text="INT/INT (alignment, fire via GUI)",
                        variable=self.trigger_mode_var, value="INT/INT",
                        command=self._on_mode_change).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Radiobutton(mode_sub, text="EXT/EXT (DG535 fires it)",
                        variable=self.trigger_mode_var, value="EXT/EXT",
                        command=self._on_mode_change).grid(row=0, column=2, sticky="w", padx=4)

        ttk.Button(fire_frame, text="Prep System",
                   command=self.start_prep, width=18).grid(row=1, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(fire_frame, text="Stop System (safe shutdown)",
                   command=self.safe_stop, width=28).grid(row=1, column=1, padx=4, pady=4, sticky="ew")

        self.fire_btn = tk.Button(
            fire_frame, text="SINGLE SHOT (OP)",
            command=self.single_shot,
            bg="red", fg="white", font=("Arial", 14, "bold"),
            height=2, state="disabled"
        )
        self.fire_btn.grid(row=2, column=0, columnspan=2, sticky="ew", padx=4, pady=4)

        ttk.Label(fire_frame, text="State:").grid(row=3, column=0, sticky="e")
        self.state_label = ttk.Label(fire_frame, textvariable=self.state_var,
                                     font=("TkDefaultFont", 10, "bold"))
        self.state_label.grid(row=3, column=1, sticky="w")

        # Last-response footer
        ttk.Label(left, textvariable=self.last_resp_var,
                  foreground="gray").grid(row=8, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # ---------- Log (right column) ----------
        log_frame = ttk.LabelFrame(main, text="Communication Log", padding=6)
        log_frame.grid(row=0, column=1, sticky="nsew", pady=4)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = scrolledtext.ScrolledText(log_frame, height=12, width=40,
                                             font=("Courier", 9))
        self.log.grid(row=0, column=0, sticky="nsew")
        ttk.Button(log_frame, text="Clear Log",
                   command=lambda: self.log.delete("1.0", tk.END)).grid(row=1, column=0, sticky="e", pady=2)

    def _on_mode_change(self):
        """Update fire button label/state when mode is changed."""
        mode = self.trigger_mode_var.get()
        if mode == "INT/INT":
            self.fire_btn.config(text="SINGLE SHOT (OP)")
        else:
            self.fire_btn.config(text="Verify ARMED (status check)")
        # Disable the fire button until prep completes again under the new mode
        self.fire_btn.config(state="disabled")
        self.set_state("Idle (mode changed, re-run Prep)")
        self.log_msg(f"Trigger mode set to {mode}")

    # ============================================================
    # Logging helpers (thread-safe via queue)
    # ============================================================
    def log_msg(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {msg}\n")

    def poll_log_queue(self):
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
        if not self.port_var.get():
            # Prefer this panel's configured default port if it is present,
            # otherwise fall back to the first available port.
            if self.default_port and self.default_port in ports:
                self.port_var.set(self.default_port)
            elif self.default_port:
                # Show the intended port even if it is not enumerated yet.
                self.port_var.set(self.default_port)
            elif ports:
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
        if not self.ser or not self.ser.is_open:
            self.log_msg(f"SKIP {cmd!r} - not connected")
            return None

        try:
            self.ser.reset_input_buffer()
            payload = (cmd + "\r\n").encode("ascii")
            self.ser.write(payload)
            self.ser.flush()

            old_timeout = self.ser.timeout
            self.ser.timeout = read_timeout
            resp_bytes = self.ser.read_until(b"\r\n", size=128)
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
        with self.ser_lock:
            resp = self._send_raw(cmd, read_timeout=read_timeout)
            time.sleep(0.16)
        if resp is not None:
            self.last_resp_var.set(f"{cmd} -> {resp}")
        return resp

    def send_cmd_async(self, cmd):
        threading.Thread(target=self.send_cmd_locked, args=(cmd,), daemon=True).start()

    # ============================================================
    # Custom RS-232 command
    # ============================================================
    def _send_custom_cmd(self):
        cmd = self.custom_cmd_var.get().strip()
        if not cmd:
            return
        threading.Thread(target=self._custom_cmd_worker,
                         args=(cmd,), daemon=True).start()
        self.custom_cmd_var.set("")

    def _custom_cmd_worker(self, cmd):
        if not (self.ser and self.ser.is_open):
            self.root.after(0, lambda: self.custom_resp_var.set("(not connected)"))
            return
        resp = self.send_cmd_locked(cmd)
        if resp is None:
            self.root.after(0, lambda: self.custom_resp_var.set("(no response)"))
        else:
            display = resp if resp else "(empty response)"
            self.root.after(0, lambda d=display: self.custom_resp_var.set(d))

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

        i_present = self._extract_wor_field(wor, "I")
        if i_present is None:
            self._set_interlock_summary(f"Could not parse WOR: {wor!r}", color="red")
            return

        if i_present == "0":
            self._set_interlock_summary(f"WOR: {wor}\nNo interlocks present.",
                                        color="darkgreen")
            self.log_msg("WOR reports no interlocks.")
            return

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
                "WOR says interlocks present but no specific bits set.",
                color="orange")

    # ============================================================
    # Interlock clear attempt (empirical only)
    # ============================================================
    def attempt_clear_interlocks_async(self):
        if not (self.ser and self.ser.is_open):
            self.log_msg("Cannot clear: not connected")
            return
        threading.Thread(target=self._clear_interlocks_worker, daemon=True).start()

    def _clear_interlocks_worker(self):
        self.log_msg("=== ATTEMPTING TO CLEAR LATCHED INTERLOCKS (empirical) ===")
        self.log_msg("Note: manual states only cursor-up/down on remote box clears interlocks.")
        self._set_interlock_summary("Trying clearance commands...", color="blue")

        wor = self.send_cmd_locked("WOR")
        if wor and self._extract_wor_field(wor, "I") == "0":
            self.log_msg("No interlocks present (already clear).")
            self._set_interlock_summary("No interlocks present.", color="darkgreen")
            return

        attempts = [
            ("IF",      "Query first interlock (may acknowledge in some firmware)"),
            ("S",       "Stop flashlamp"),
            ("CS",      "Stop Q-switch"),
            ("SHC0",    "Close shutter"),
            ("SHC1",    "Open shutter"),
            ("SHC0",    "Close shutter again"),
            ("PMOD1",   "Switch to FILL mode"),
            ("PMOD0",   "Switch to NORMAL mode"),
            ("PMOD1",   "Back to FILL mode (steady flow)"),
            ("M",       "Simmer (re-evaluates state machine)"),
            ("S",       "Stop after simmer"),
        ]

        for cmd, desc in attempts:
            self.log_msg(f"  -> Trying: {cmd}  ({desc})")
            self.send_cmd_locked(cmd)
            time.sleep(0.4)

            wor = self.send_cmd_locked("WOR")
            if wor:
                i_present = self._extract_wor_field(wor, "I")
                if i_present == "0":
                    msg = f"INTERLOCK CLEARED after sending '{cmd}' ({desc})"
                    self.log_msg("*** " + msg + " ***")
                    self._set_interlock_summary(msg, color="darkgreen")
                    return

        self.log_msg("All empirical commands exhausted, interlock still set.")
        self.log_msg("Manual workaround: press cursor up/down on remote box, "
                     "or cycle the Key Switch.")
        self._check_interlocks_worker()
        existing = self.interlock_summary_var.get()
        self._set_interlock_summary(
            existing + "\n\n(Could not clear via RS-232. Press cursor up/down on "
                       "remote box, or cycle the Key Switch.)",
            color="red")

    @staticmethod
    def _extract_wor_field(wor, letter):
        tokens = wor.replace(":", " ").split()
        for i, tok in enumerate(tokens):
            if tok == letter and i + 1 < len(tokens):
                next_tok = tokens[i + 1]
                if next_tok and next_tok[0].isdigit():
                    return next_tok[0]
        return None

    def _set_interlock_summary(self, text, color="black"):
        self.root.after(0, lambda: self.interlock_summary_var.set(text))
        self.root.after(0, lambda: self.interlock_label.configure(foreground=color))

    # ============================================================
    # Pump / coolant control
    # ============================================================
    def _confirm_pump_off(self):
        ok = messagebox.askyesno(
            "Confirm pump OFF",
            "Turning the pump OFF for extended periods can overheat the ICE450 PFC supply.\n\n"
            "Only do this briefly (e.g. while filling).\n\nProceed?")
        if ok:
            self.send_cmd_async("PUMP0")

    def _enter_fill_mode(self):
        self.send_cmd_async("PMOD1")
        self.log_msg("Entered FILL MODE - pump runs continuously. "
                     "Send PMOD0 to return to NORMAL mode.")

    def refresh_pump_status_async(self):
        threading.Thread(target=self._pump_status_worker, daemon=True).start()

    def _pump_status_worker(self):
        if not (self.ser and self.ser.is_open):
            return

        resp = self.send_cmd_locked("PUMP")
        if resp:
            r = resp.lower()
            if "on" in r and "off" not in r:
                self._set_pump_var(self.pump_state_var, "ON")
            elif "off" in r:
                self._set_pump_var(self.pump_state_var, "OFF")
            else:
                self._set_pump_var(self.pump_state_var, "?")

        resp = self.send_cmd_locked("PMOD")
        if resp:
            r = resp.lower()
            if "fill" in r:
                self._set_pump_var(self.pump_mode_var, "FILL")
            elif "normal" in r:
                self._set_pump_var(self.pump_mode_var, "NORMAL")
            else:
                self._set_pump_var(self.pump_mode_var, "?")

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

        resp = self.send_cmd_locked("FLOW")
        if resp:
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
        if self.pump_poll_active.get():
            self.log_msg("Pump auto-poll: ON (every 2 s)")
            self._schedule_pump_poll()
        else:
            self.log_msg("Pump auto-poll: OFF")

    def _schedule_pump_poll(self):
        if not self.pump_poll_active.get():
            return
        if self.ser and self.ser.is_open:
            threading.Thread(target=self._pump_status_worker, daemon=True).start()
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
            mode = self.trigger_mode_var.get()
            self.log_msg(f"--- PREP SEQUENCE START ({mode}) ---")
            self.set_state(f"Prep starting ({mode})...")

            # ----- 1. Interlock pre-check -----
            self.set_state("Checking interlocks...")
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
                    "Interlocks present.\n\n"
                    "Click 'Check Interlocks' to see which, then 'Attempt Clear' "
                    "if it is a latched fault."))
                return

            if self.prep_cancel.is_set():
                self.set_state("Prep cancelled")
                return

            # ----- 2. Mode-specific sync setup -----
            if mode == "INT/INT":
                self.set_state("Setting Q-Switch INT (QI)...")
                resp = self.send_cmd_locked("QI")
                if not resp or "INT" not in resp.upper():
                    self.log_msg(f"QI did not return expected 'QS sync: INT', got: {resp!r}")

                self.set_state("Starting flashlamp INT (A)...")
                resp = self.send_cmd_locked("A")
                if not resp:
                    self.set_state("Prep ABORTED (A command failed)")
                    return
                if "fire auto" not in resp.lower():
                    self.log_msg(f"WARNING: A response was {resp!r}, expected 'fire auto'")

            else:  # EXT/EXT
                self.set_state("Setting Q-Switch EXT (QE)...")
                resp = self.send_cmd_locked("QE")
                if not resp or "EXT" not in resp.upper():
                    self.log_msg(f"QE did not return expected 'QS sync: EXT', got: {resp!r}")

                # BYPASS must be set BEFORE flashlamp transitions Stop -> Fire.
                # Without BYPASS1 there is a 500 us delay between Lamp In rising
                # edge and actual flashlamp fire (manual p. 42).
                self.set_state("Setting BYPASS1 (0.5 us flashlamp delay)...")
                resp = self.send_cmd_locked("BYPASS1")
                if not resp or "on" not in resp.lower():
                    self.log_msg(f"WARNING: BYPASS1 response was {resp!r}, expected 'bypass:on'")

                self.set_state("Starting flashlamp EXT (E)...")
                resp = self.send_cmd_locked("E")
                if not resp:
                    self.set_state("Prep ABORTED (E command failed)")
                    return
                if "fire ext" not in resp.lower():
                    self.log_msg(f"WARNING: E response was {resp!r}, expected 'fire ext'")

            # ----- 3. Open shutter -----
            self.set_state("Opening shutter (SHC1)...")
            self.send_cmd_locked("SHC1")

            # ----- 4. Poll the 8 s safety delay -----
            self.log_msg("Polling IQ for 8-s safety delay clearance...")
            t0 = time.time()
            timeout_s = 15.0
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
                    faults = parse_interlock_response(resp, IQ_BITS, "IQS")
                    delay_active = any("8-second" in f for f in faults)
                    other_faults = [f for f in faults if "8-second" not in f and "(unused)" not in f]

                    if other_faults:
                        self.log_msg(f"Q-Switch interlocks during prep: {other_faults}")
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

            # ----- 5. Mode-specific finish -----
            if mode == "INT/INT":
                self.set_state("Verifying ready state...")
                st = self.send_cmd_locked("ST")
                self.log_msg(f"Final state string: {st!r}")  # expect 'fire auto'

                self.set_state("READY TO FIRE")
                self.root.after(0, lambda: self.fire_btn.config(state="normal",
                                                                text="SINGLE SHOT (OP)"))
                self.log_msg("--- PREP COMPLETE (INT/INT) ---")
                self.log_msg("Click SINGLE SHOT to fire one pulse via OP.")

            else:  # EXT/EXT
                self.set_state("Arming Q-switch (CC)...")
                resp = self.send_cmd_locked("CC")
                self.log_msg(f"CC response: {resp!r}")  # expect ends with 'qs e'

                self.set_state("Verifying armed state...")
                st = self.send_cmd_locked("ST")
                self.log_msg(f"Final state string: {st!r}")  # expect 'fire ext qs e'

                wor = self.send_cmd_locked("WOR")
                self.log_msg(f"Final WOR: {wor!r}")  # expect 'I 0 F 6 S 1 Q 6'

                if st and "ext" in st.lower() and "qs" in st.lower():
                    self.set_state("ARMED - waiting for DG535 trigger")
                    self.log_msg("--- PREP COMPLETE (EXT/EXT) ---")
                    self.log_msg("Laser is armed. Every Lamp In + Q-Switch In pulse from "
                                 "the DG535 will produce one shot.")
                    self.root.after(0, lambda: self.fire_btn.config(
                        state="normal", text="Verify ARMED (status check)"))
                else:
                    self.set_state(f"Prep WARNING: state unexpected: {st}")
                    self.log_msg("Prep completed but ST string did not confirm EXT/EXT armed state.")

        except Exception as e:
            self.log_msg(f"PREP EXCEPTION: {e}")
            self.set_state(f"Prep error: {e}")

    # ============================================================
    # Fire / status check
    # ============================================================
    def single_shot(self):
        mode = self.trigger_mode_var.get()

        if mode == "INT/INT":
            if self.state_var.get() != "READY TO FIRE":
                messagebox.showwarning("Not ready", "Run Prep System first.")
                return

            confirm = messagebox.askyesno(
                "Confirm fire",
                "Eyewear on?\nBeam path clear?\nInterlocks closed?\n\nFire single shot now?"
            )
            if not confirm:
                return

            self.set_state("FIRING (OP)")
            self.fire_btn.config(state="disabled")
            threading.Thread(target=self._fire_worker_int, daemon=True).start()

        else:  # EXT/EXT - this button is now a status check
            threading.Thread(target=self._fire_worker_ext_status, daemon=True).start()

    def _fire_worker_int(self):
        """INT/INT mode: actually fires the Q-switch via OP."""
        resp = self.send_cmd_locked("OP")
        self.log_msg(f"FIRE command (OP) sent. Response: {resp!r}")
        self.set_state("SHOT FIRED - re-prep for another shot")

    def _fire_worker_ext_status(self):
        """EXT/EXT mode: GUI does not fire the laser. Verify it is armed."""
        st = self.send_cmd_locked("ST")
        wor = self.send_cmd_locked("WOR")
        self.log_msg(f"Status check: ST={st!r}  WOR={wor!r}")

        armed = bool(st and "ext" in st.lower() and "qs" in st.lower())
        if armed:
            self.set_state("ARMED - DG535 controls firing")
            self.log_msg("Confirmed armed. Trigger the DG535 to fire a shot.")
        else:
            self.set_state(f"NOT ARMED: {st}")
            self.log_msg("Laser is not in the expected EXT/EXT armed state. "
                         "Re-run Prep System.")

    # ============================================================
    # Stop
    # ============================================================
    def safe_stop(self):
        self.prep_cancel.set()
        threading.Thread(target=self._stop_worker, daemon=True).start()

    def _stop_worker(self):
        self.log_msg("--- SAFE STOP ---")
        self.send_cmd_locked("CS")    # stop Q-switch
        self.send_cmd_locked("S")     # stop flashlamp
        self.send_cmd_locked("SHC0")  # close shutter
        self.set_state("Stopped")
        self.root.after(0, lambda: self.fire_btn.config(state="disabled"))

    # ============================================================
    # State helpers
    # ============================================================
    def set_state(self, text):
        self.root.after(0, lambda: self.state_var.set(text))


# Define each laser here. Add/remove entries to control more or fewer lasers.
LASERS = [
    {"name": "Laser 1", "default_port": None},
    {"name": "Laser 2", "default_port": "COM11"},
]


def main():
    root = tk.Tk()
    root.title("CFR Laser Control - Dual (INT/INT + EXT/EXT)")

    # Resizable, maximized window with fullscreen toggle.
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)
    try:
        root.state("zoomed")
    except tk.TclError:
        root.attributes("-zoomed", True)

    fs_state = {"on": False}

    def toggle_fullscreen(_event=None):
        fs_state["on"] = not fs_state["on"]
        root.attributes("-fullscreen", fs_state["on"])

    def exit_fullscreen(_event=None):
        fs_state["on"] = False
        root.attributes("-fullscreen", False)

    root.bind("<F11>", toggle_fullscreen)
    root.bind("<Escape>", exit_fullscreen)

    # One tab per laser; each tab is a fully independent panel.
    notebook = ttk.Notebook(root)
    notebook.grid(row=0, column=0, sticky="nsew")

    panels = []
    for cfg in LASERS:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text=cfg["name"])
        panel = CFRLaserPanel(root, tab, name=cfg["name"],
                              default_port=cfg.get("default_port"))
        panels.append(panel)

    def on_close():
        for panel in panels:
            panel.prep_cancel.set()
            try:
                if panel.ser and panel.ser.is_open:
                    panel.ser.close()
            except Exception:
                pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
