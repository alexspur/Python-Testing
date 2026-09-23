# utils/system_state.py
"""
One central, thread-safe record of what every instrument is doing.

Polling threads and panel handlers push values in as they are read, commanded
or applied. At trigger time the shot logger takes a frozen deep copy, so a
background thread cannot change a value while the row is being written.

Nothing in here talks to hardware, and nothing here blocks: callers do their
(slow) I/O first and then hand the result over.

Every device section carries three bookkeeping keys:
    _source             where the values came from:
                          "readback"    queried back from the instrument
                          "commanded"   we sent it; the instrument cannot be
                                        queried, so it is unconfirmed
                          "gui_default" nothing was applied or verified this
                                        session; the GUI's own default
    _updated_monotonic  time.monotonic() when it was stamped, for age_ms()
    _updated_wall       datetime for the human-readable timestamp

Each GUI launch starts empty (a fresh process per shot), which is why
instruments are read back at connect time rather than assumed.
"""

import copy
import threading
import time
from datetime import datetime

# Where a cached value came from.
SOURCE_READBACK = "readback"
SOURCE_COMMANDED = "commanded"
SOURCE_GUI_DEFAULT = "gui_default"

UNKNOWN = "UNKNOWN"

# One section per device. dg535_laser is the only DG535 the GUI talks to; the
# screen room DG535 that triggers the Marx is not connected to this PC.
DEVICES = (
    "pressure",
    "wj1",
    "wj2",
    "bnc575",
    "dg535_laser",
    "laser1",
    "laser2",
    "relays",
    "interlocks",
    "rigol1",
    "rigol2",
    "rigol3",
)


class SystemState:
    """Latest known state of every device, guarded by one lock.

    The lock is only ever held for dict updates and deep copies, never across
    hardware I/O.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data = {name: {} for name in DEVICES}

    # ------------------------------------------------------------ writing

    def update(self, device, values, source=None):
        """Merge `values` into one device section and stamp it.

        source is one of SOURCE_* and should be passed whenever the caller
        knows how the values were obtained; it is left as-is otherwise.
        """
        with self._lock:
            section = self._data.setdefault(device, {})
            section.update(values)
            if source is not None:
                section["_source"] = source
            section["_updated_monotonic"] = time.monotonic()
            section["_updated_wall"] = datetime.now()

    def clear(self, device):
        """Forget a device's state (e.g. its link dropped)."""
        with self._lock:
            self._data[device] = {}

    # ------------------------------------------------------------ reading

    def get(self, device):
        """A copy of one device section (never the live dict)."""
        with self._lock:
            return copy.deepcopy(self._data.get(device, {}))

    def value(self, device, key, default=None):
        with self._lock:
            return self._data.get(device, {}).get(key, default)

    def snapshot(self):
        """Frozen deep copy of every device section, for one shot row."""
        with self._lock:
            return copy.deepcopy(self._data)

    # ------------------------------------------------------------ helpers

    @staticmethod
    def age_ms(section, now_monotonic=None):
        """How old a section's values are, in ms, or None if never stamped.

        Uses time.monotonic so a clock change cannot produce a negative age.
        """
        if not section:
            return None
        stamped = section.get("_updated_monotonic")
        if stamped is None:
            return None
        now = time.monotonic() if now_monotonic is None else now_monotonic
        return (now - stamped) * 1000.0

    @staticmethod
    def source_of(section):
        if not section:
            return UNKNOWN
        return section.get("_source", UNKNOWN)
