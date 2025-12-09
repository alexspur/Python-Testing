# utils/connect_memory.py
import json
import os

MEM_FILE = "connection_memory.json"

default_data = {
    "DG535_COM": "COM4",
    "BNC575_COM": "COM5",
    "Arduino_COM": "COM8",
    "WJ_COM": "COM6",

    "Rigol1_VISA": "USB0::0x1AB1::0x0514::DS7A232900210::0::INSTR",
    "Rigol2_VISA": "USB0::0x1AB1::0x0514::DS7A230800035::0::INSTR",
    "Rigol3_VISA": "USB0::0x1AB1::0x0514::DS7A233300256::0::INSTR"
}

def load_memory():
    if not os.path.exists(MEM_FILE):
        return default_data.copy()
    try:
        with open(MEM_FILE, "r") as f:
            data = json.load(f)
        return {**default_data, **data}
    except:
        return default_data.copy()

def save_memory(key, value):
    """Update one field in memory and write file."""
    data = load_memory()          # load existing memory
    data[key] = value             # update the value
    with open(MEM_FILE, "w") as f:
        json.dump(data, f, indent=2)
