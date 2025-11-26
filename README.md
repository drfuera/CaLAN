# CaLAN — GTK3 Desktop Calendar

GTK3 desktop calendar focused on fast task entry, local-first storage, live tray feedback, and zero-config multi-instance synchronization.

![CaLAN Screenshot](screenshot.png)



## Core Capabilities

- Monthly calendar with day highlighting
- Per-day task lists
- Second-level alarm engine
- System tray icon with dynamic task badge
- Standard ICS file storage
- Multicast-based peer synchronization
- True multi-instance isolation via environment variable
- Automatic midnight rollover handling
- Centralized debug logging
- Optional Pillow-based tray badge rendering



## Runtime Requirements

- Python 3.8+
- GTK3 / PyGObject
- Cairo
- Optional: Pillow (tray badges)

### Debian / Ubuntu

    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-pil

---

## Layout

    .
    ├── main.py
    ├── icon.png
    ├── ical/
    │   └── calendar data (auto-created)
    └── include/
        ├── alarm_management.py
        ├── calendar_ui.py
        ├── debug_logger.py
        ├── ics_storage.py
        ├── multicast_sync.py
        ├── task_management.py
        └── tray_icon.py

---

## Startup

    python3 main.py

---

## Multi-Instance Mode

    CALAN_INSTANCE=2 python3 main.py
    CALAN_INSTANCE=3 python3 main.py

Each instance uses a dedicated directory:

    ical/instance_<N>/

---

## Data Model

- All tasks stored as standard ICS files
- Local-only persistence
- Human-readable backups
- Safe for manual inspection and versioning

---

## Network Synchronization

CaLAN uses **UDP multicast** for real-time peer discovery and task propagation.  
No servers, cloud services, or manual pairing are required.

### How It Works

- Each running instance joins a fixed multicast group on the local network
- When tasks change, a compact update packet is broadcast to the group
- All listening peers receive the update simultaneously
- Remote changes are merged into the local task store
- Updates are immediately reflected in the UI and tray badge

The multicast listener starts automatically during application startup and runs continuously in the background.

### Why This Works Reliably

- Multicast operates at the network layer and requires no central coordination
- All peers receive identical packets at the same time
- No NAT traversal or routing configuration is required on LAN
- Failure of one instance does not affect others
- Sync traffic is extremely small and low-latency
- Conflicts are minimized because storage remains local and authoritative

This design guarantees:
- Zero configuration
- No single point of failure
- Deterministic peer behavior on trusted networks

---

## Tray Behavior

- Tray icon created at startup
- Live badge reflects current-day workload
- Badge renderer falls back gracefully when Pillow is unavailable

---

## Exit Handling

- Window close triggers confirmation dialog
- Tray continues operating when minimized
- Full shutdown stops alarms, sync, and timers cleanly

---

## License

Not yet defined.
