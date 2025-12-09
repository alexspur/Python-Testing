# utils/serial_tools.py
import serial.tools.list_ports


def list_serial_ports() -> list[str]:
    ports = serial.tools.list_ports.comports()
    return [p.device for p in ports]
