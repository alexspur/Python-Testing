#!/usr/bin/env python3
"""
Ross HV Relay Control Box — GUI + Pushbutton Controller
Controls 4 channels via Numato RL40001 USB relay module.
Supports simultaneous GUI and remote pushbutton control.

Hardware:
  - Numato RL40001 (4-ch USB relay, 6 GPIO, 5 ADC)
  - Phoenix Contact 2903677 intermediate relays (4PDT, 24VDC)
  - Carling LT-1561 toggle switches (ON-OFF-ON)
  - Ross Engineering HV relays (120VAC coil)
  - Remote pushbuttons on GPIO 0-3

Usage:
  python relay_control_gui.py [--port /dev/ttyACM0] [--baud 19200]
"""

import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import time
import argparse
import sys
from datetime import datetime


class NumatoController:
    """Low-level serial interface to Numato 4-channel USB relay module."""

    def __init__(self, port=None, baud=19200):
        self.ser = None
        self.port = port
        self.baud = baud
        self.lock = threading.Lock()
        self.connected = False

    def connect(self, port=None, baud=None):
        if port:
            self.port = port
        if baud:
            self.baud = baud
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.5)
            time.sleep(2)  # Wait for USB CDC initialization
            self.ser.flushInput()
            self.ser.flushOutput()
            self.connected = True
            return True
        except Exception as e:
            self.connected = False
            raise ConnectionError(f"Failed to connect to {self.port}: {e}")

    def disconnect(self):
        if self.ser and self.ser.is_open:
            # Turn all relays off on disconnect
            for ch in range(4):
                try:
                    self._send(f"relay off {ch}")
                except:
                    pass
            self.ser.close()
        self.connected = False

    def _send(self, cmd):
        """Send command and return response."""
        with self.lock:
            if not self.ser or not self.ser.is_open:
                return ""
            self.ser.flushInput()
            self.ser.write((cmd + "\r").encode())
            time.sleep(0.05)
            response = self.ser.read(self.ser.in_waiting or 64).decode(errors="ignore")
            return response.strip()

    def relay_on(self, ch):
        self._send(f"relay on {ch}")

    def relay_off(self, ch):
        self._send(f"relay off {ch}")

    def relay_read(self, ch):
        resp = self._send(f"relay read {ch}")
        # Numato returns "1" or "0" for relay state
        return "on" in resp.lower() or "1" in resp

    def gpio_read(self, gpio):
        resp = self._send(f"gpio read {gpio}")
        # Numato returns "1" or "0", not "on"/"off" for GPIO
        return "1" in resp

    @staticmethod
    def list_ports():
        """List available serial ports."""
        ports = serial.tools.list_ports.comports()
        return [(p.device, p.description) for p in ports]


class RelayControlApp:
    """Main GUI application for Ross HV Relay control."""

    # Channel labels — customize these for your setup
    CHANNEL_NAMES = [
        "Ross Relay 1",
        "Ross Relay 2",
        "Ross Relay 3",
        "Ross Relay 4",
    ]

    def __init__(self, root, port=None, baud=19200):
        self.root = root
        self.root.title("Ross HV Relay Control")
        self.root.configure(bg="#0a0e17")
        self.root.minsize(700, 580)

        # Controller
        self.ctrl = NumatoController(port, baud)

        # State tracking
        self.relay_states = [False] * 4
        self.prev_button = [False] * 4
        self.polling = False
        self.poll_thread = None

        # Log buffer
        self.log_buffer = []

        # Build UI
        self._setup_styles()
        self._build_ui()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Auto-connect if port specified
        if port:
            self.root.after(500, lambda: self._connect(port, baud))

    def _setup_styles(self):
        self.colors = {
            "bg": "#0a0e17",
            "surface": "#111827",
            "surface2": "#1a2332",
            "border": "#2a3444",
            "text": "#e2e8f0",
            "text_dim": "#8892a4",
            "accent": "#f59e0b",
            "green": "#10b981",
            "red": "#ef4444",
            "blue": "#3b82f6",
            "orange": "#f97316",
        }
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Surface.TFrame", background=self.colors["surface"])
        style.configure("TLabel",
                         background=self.colors["bg"],
                         foreground=self.colors["text"],
                         font=("Consolas", 10))
        style.configure("Header.TLabel",
                         background=self.colors["bg"],
                         foreground=self.colors["accent"],
                         font=("Consolas", 16, "bold"))
        style.configure("Sub.TLabel",
                         background=self.colors["bg"],
                         foreground=self.colors["text_dim"],
                         font=("Consolas", 9))
        style.configure("Status.TLabel",
                         background=self.colors["surface"],
                         foreground=self.colors["text_dim"],
                         font=("Consolas", 9))
        style.configure("TButton",
                         background=self.colors["surface2"],
                         foreground=self.colors["text"],
                         font=("Consolas", 10),
                         borderwidth=1,
                         relief="flat",
                         padding=(12, 6))
        style.map("TButton",
                   background=[("active", self.colors["border"])],
                   foreground=[("active", self.colors["text"])])

    def _build_ui(self):
        # Main container
        main = ttk.Frame(self.root, style="TFrame")
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        # Header
        ttk.Label(main, text="⚡ Ross HV Relay Control",
                  style="Header.TLabel").pack(anchor="w")
        ttk.Label(main, text="Numato RL40001 — 4 Channel USB Relay Controller",
                  style="Sub.TLabel").pack(anchor="w", pady=(0, 12))

        # Connection bar
        conn_frame = tk.Frame(main, bg=self.colors["surface"],
                              highlightbackground=self.colors["border"],
                              highlightthickness=1, padx=12, pady=8)
        conn_frame.pack(fill=tk.X, pady=(0, 12))

        tk.Label(conn_frame, text="PORT:", bg=self.colors["surface"],
                 fg=self.colors["text_dim"], font=("Consolas", 9)).pack(side=tk.LEFT)

        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var,
                                        width=25, font=("Consolas", 9))
        self.port_combo.pack(side=tk.LEFT, padx=(6, 8))
        self._refresh_ports()

        self.connect_btn = tk.Button(
            conn_frame, text="CONNECT", font=("Consolas", 9, "bold"),
            bg=self.colors["green"], fg="#000", activebackground="#059669",
            relief="flat", padx=12, pady=2, command=self._toggle_connection)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(conn_frame, text="↻", font=("Consolas", 11),
                  bg=self.colors["surface2"], fg=self.colors["text_dim"],
                  relief="flat", padx=6, command=self._refresh_ports).pack(side=tk.LEFT)

        self.conn_status = tk.Label(conn_frame, text="● DISCONNECTED",
                                     bg=self.colors["surface"],
                                     fg=self.colors["red"],
                                     font=("Consolas", 9, "bold"))
        self.conn_status.pack(side=tk.RIGHT)

        # Channel controls
        self.channel_frames = []
        self.state_labels = []
        self.toggle_buttons = []
        self.on_buttons = []
        self.off_buttons = []
        self.indicator_canvases = []

        channels_frame = tk.Frame(main, bg=self.colors["bg"])
        channels_frame.pack(fill=tk.X, pady=(0, 12))

        for i in range(4):
            self._build_channel_row(channels_frame, i)

        # All On / All Off buttons
        bulk_frame = tk.Frame(main, bg=self.colors["bg"])
        bulk_frame.pack(fill=tk.X, pady=(0, 12))

        tk.Button(bulk_frame, text="ALL ON", font=("Consolas", 10, "bold"),
                  bg="#065f46", fg=self.colors["green"],
                  activebackground="#047857", relief="flat",
                  padx=20, pady=6, command=self._all_on).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(bulk_frame, text="ALL OFF", font=("Consolas", 10, "bold"),
                  bg="#7f1d1d", fg=self.colors["red"],
                  activebackground="#991b1b", relief="flat",
                  padx=20, pady=6, command=self._all_off).pack(side=tk.LEFT, padx=(0, 8))

        # Pushbutton polling toggle
        self.poll_btn = tk.Button(
            bulk_frame, text="START POLLING", font=("Consolas", 9, "bold"),
            bg=self.colors["surface2"], fg=self.colors["blue"],
            activebackground=self.colors["border"], relief="flat",
            padx=12, pady=6, command=self._toggle_polling)
        self.poll_btn.pack(side=tk.RIGHT)

        self.poll_status = tk.Label(bulk_frame, text="Pushbutton polling: OFF",
                                     bg=self.colors["bg"],
                                     fg=self.colors["text_dim"],
                                     font=("Consolas", 9))
        self.poll_status.pack(side=tk.RIGHT, padx=(0, 8))

        # Log area
        log_label = tk.Label(main, text="EVENT LOG", bg=self.colors["bg"],
                              fg=self.colors["text_dim"],
                              font=("Consolas", 9, "bold"))
        log_label.pack(anchor="w", pady=(0, 4))

        log_frame = tk.Frame(main, bg=self.colors["surface"],
                              highlightbackground=self.colors["border"],
                              highlightthickness=1)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(
            log_frame, bg=self.colors["surface"], fg=self.colors["text_dim"],
            font=("Consolas", 9), relief="flat", height=8,
            insertbackground=self.colors["text_dim"],
            selectbackground=self.colors["border"],
            wrap=tk.WORD, padx=8, pady=6)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.configure(state="disabled")

        # Status bar
        self.status_bar = tk.Label(
            self.root, text="Ready", bg=self.colors["surface2"],
            fg=self.colors["text_dim"], font=("Consolas", 8),
            anchor="w", padx=8, pady=3)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _build_channel_row(self, parent, ch):
        """Build one channel control row."""
        row = tk.Frame(parent, bg=self.colors["surface"],
                       highlightbackground=self.colors["border"],
                       highlightthickness=1, padx=12, pady=10)
        row.pack(fill=tk.X, pady=(0, 4))

        # Indicator light
        canvas = tk.Canvas(row, width=20, height=20,
                           bg=self.colors["surface"],
                           highlightthickness=0)
        canvas.pack(side=tk.LEFT, padx=(0, 10))
        canvas.create_oval(2, 2, 18, 18, fill=self.colors["red"],
                           outline="#333", width=1, tags="indicator")
        self.indicator_canvases.append(canvas)

        # Channel label
        tk.Label(row, text=f"CH{ch}", bg=self.colors["surface"],
                 fg=self.colors["accent"], font=("Consolas", 11, "bold"),
                 width=4).pack(side=tk.LEFT)

        tk.Label(row, text=self.CHANNEL_NAMES[ch], bg=self.colors["surface"],
                 fg=self.colors["text"], font=("Consolas", 10),
                 width=14, anchor="w").pack(side=tk.LEFT, padx=(4, 12))

        # State label
        state_lbl = tk.Label(row, text="OFF", bg=self.colors["surface"],
                              fg=self.colors["red"],
                              font=("Consolas", 11, "bold"), width=4)
        state_lbl.pack(side=tk.LEFT, padx=(0, 16))
        self.state_labels.append(state_lbl)

        # Toggle button
        toggle_btn = tk.Button(
            row, text="TOGGLE", font=("Consolas", 9, "bold"),
            bg=self.colors["surface2"], fg=self.colors["accent"],
            activebackground=self.colors["border"], relief="flat",
            padx=10, pady=2,
            command=lambda c=ch: self._toggle_relay(c))
        toggle_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.toggle_buttons.append(toggle_btn)

        # ON button
        on_btn = tk.Button(
            row, text="ON", font=("Consolas", 9, "bold"),
            bg="#065f46", fg=self.colors["green"],
            activebackground="#047857", relief="flat",
            padx=8, pady=2,
            command=lambda c=ch: self._set_relay(c, True))
        on_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.on_buttons.append(on_btn)

        # OFF button
        off_btn = tk.Button(
            row, text="OFF", font=("Consolas", 9, "bold"),
            bg="#7f1d1d", fg=self.colors["red"],
            activebackground="#991b1b", relief="flat",
            padx=8, pady=2,
            command=lambda c=ch: self._set_relay(c, False))
        off_btn.pack(side=tk.LEFT)
        self.off_buttons.append(off_btn)

        self.channel_frames.append(row)

    # ─── Connection ──────────────────────────────────────

    def _refresh_ports(self):
        ports = NumatoController.list_ports()
        port_list = [f"{p[0]} — {p[1]}" for p in ports]
        self.port_combo["values"] = port_list
        if port_list and not self.port_var.get():
            self.port_combo.current(0)

    def _toggle_connection(self):
        if self.ctrl.connected:
            self._disconnect()
        else:
            selection = self.port_var.get()
            port = selection.split(" — ")[0] if " — " in selection else selection
            if not port:
                messagebox.showwarning("No Port", "Select a serial port first.")
                return
            self._connect(port)

    def _connect(self, port, baud=19200):
        try:
            self.ctrl.connect(port, baud)
            self.conn_status.configure(text="● CONNECTED", fg=self.colors["green"])
            self.connect_btn.configure(text="DISCONNECT", bg=self.colors["red"])
            self._log(f"Connected to {port}")
            self.status_bar.configure(text=f"Connected to {port} @ {baud} baud")

            # Read current relay states
            for ch in range(4):
                state = self.ctrl.relay_read(ch)
                self.relay_states[ch] = state
                self._update_channel_ui(ch)

        except Exception as e:
            messagebox.showerror("Connection Error", str(e))
            self._log(f"Connection failed: {e}")

    def _disconnect(self):
        self._stop_polling()
        self.ctrl.disconnect()
        self.conn_status.configure(text="● DISCONNECTED", fg=self.colors["red"])
        self.connect_btn.configure(text="CONNECT", bg=self.colors["green"])
        for ch in range(4):
            self.relay_states[ch] = False
            self._update_channel_ui(ch)
        self._log("Disconnected — all relays commanded OFF")
        self.status_bar.configure(text="Disconnected")

    # ─── Relay Control ───────────────────────────────────

    def _set_relay(self, ch, state):
        """Set a relay to a specific state. Called by GUI and pushbutton polling."""
        if not self.ctrl.connected:
            self._log(f"Cannot control CH{ch} — not connected")
            return

        try:
            if state:
                self.ctrl.relay_on(ch)
            else:
                self.ctrl.relay_off(ch)
            self.relay_states[ch] = state
            self._update_channel_ui(ch)
            action = "ON" if state else "OFF"
            self._log(f"CH{ch} ({self.CHANNEL_NAMES[ch]}) → {action}")
        except Exception as e:
            self._log(f"Error controlling CH{ch}: {e}")

    def _toggle_relay(self, ch):
        self._set_relay(ch, not self.relay_states[ch])

    def _all_on(self):
        for ch in range(4):
            self._set_relay(ch, True)

    def _all_off(self):
        for ch in range(4):
            self._set_relay(ch, False)

    def _update_channel_ui(self, ch):
        """Update the GUI elements for a channel to reflect current state."""
        state = self.relay_states[ch]
        if state:
            self.state_labels[ch].configure(text="ON", fg=self.colors["green"])
            self.indicator_canvases[ch].itemconfig(
                "indicator", fill=self.colors["green"])
        else:
            self.state_labels[ch].configure(text="OFF", fg=self.colors["red"])
            self.indicator_canvases[ch].itemconfig(
                "indicator", fill=self.colors["red"])

    # ─── Pushbutton Polling ──────────────────────────────

    def _toggle_polling(self):
        if self.polling:
            self._stop_polling()
        else:
            self._start_polling()

    def _start_polling(self):
        if not self.ctrl.connected:
            self._log("Cannot start polling — not connected")
            return
        self.polling = True
        self.poll_btn.configure(text="STOP POLLING", fg=self.colors["red"])
        self.poll_status.configure(text="Pushbutton polling: ON",
                                    fg=self.colors["green"])
        self._log("Pushbutton polling started (GPIO 0-3)")
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def _stop_polling(self):
        self.polling = False
        self.poll_btn.configure(text="START POLLING", fg=self.colors["blue"])
        self.poll_status.configure(text="Pushbutton polling: OFF",
                                    fg=self.colors["text_dim"])
        if self.poll_thread:
            self.poll_thread.join(timeout=1)
            self.poll_thread = None
        self._log("Pushbutton polling stopped")

    def _poll_loop(self):
        """Background thread: poll GPIO 0-3 for pushbutton presses.

        GPIO mapping (2 buttons per channel):
          GPIO 0 = Ch0 GREEN (ON)    GPIO 1 = Ch0 RED (OFF)
          GPIO 2 = Ch1 GREEN (ON)    GPIO 3 = Ch1 RED (OFF)

        Adjust the button_map below to match your wiring.
        """
        # Map: (gpio_pin, channel, action)
        # Only poll GPIOs that are actually wired to buttons
        # GPIO 1 is unusable (tied to relay internally)
        button_map = [
            (0, 0, "on"),    # GPIO 0 = Ch0 green (ON)
            (4, 0, "off"),   # GPIO 4 = Ch0 red (OFF)
        ]

        while self.polling and self.ctrl.connected:
            try:
                for gpio, ch, action in button_map:
                    if not self.polling:
                        break
                    current = self.ctrl.gpio_read(gpio)
                    time.sleep(0.02)

                    # Simple: if button is pressed, send the command
                    if current:
                        state = (action == "on")
                        if state:
                            self.ctrl.relay_on(ch)
                        else:
                            self.ctrl.relay_off(ch)
                        self.relay_states[ch] = state
                        time.sleep(0.05)
                        self.root.after(0, self._pushbutton_update_ui,
                                        ch, state, action)

                time.sleep(0.08)

            except Exception as e:
                self.root.after(0, self._log, f"Polling error: {e}")
                time.sleep(0.5)

    def _pushbutton_update_ui(self, ch, state, action):
        """Called on main thread to update UI after pushbutton action."""
        color = "GREEN" if action == "on" else "RED"
        self._log(f"Pushbutton CH{ch} {color} pressed")
        self._update_channel_ui(ch)

    # ─── Logging ─────────────────────────────────────────

    def _log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"

        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, entry + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    # ─── Cleanup ─────────────────────────────────────────

    def _on_close(self):
        """Clean shutdown: stop polling, turn off relays, close serial."""
        if self.polling:
            self._stop_polling()
        if self.ctrl.connected:
            self._log("Shutting down — all relays OFF")
            self.ctrl.disconnect()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(
        description="Ross HV Relay Control GUI")
    parser.add_argument("--port", "-p", type=str, default=None,
                        help="Serial port (e.g. /dev/ttyACM0 or COM3)")
    parser.add_argument("--baud", "-b", type=int, default=19200,
                        help="Baud rate (default: 19200)")
    args = parser.parse_args()

    root = tk.Tk()

    # Set icon if available
    try:
        root.iconname("Relay Control")
    except:
        pass

    app = RelayControlApp(root, port=args.port, baud=args.baud)
    root.mainloop()


if __name__ == "__main__":
    main()
