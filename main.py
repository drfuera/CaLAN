#!/usr/bin/env python3
"""
GTK3 Desktop Calendar Application
Features: Visual calendar, task management, alarms, system tray, ICS storage, multicast sync

        John 14:6
        I am the way, and the truth, and the life. No one comes to the Father except through me.

        Romans 6:23
        For the wages of sin is death, but the free gift of God is eternal life in Christ Jesus our Lord.

        Romans 10:13
        For everyone who calls on the name of the Lord will be saved.
"""

import logging
import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
import calendar
import hashlib
import io
import json
import secrets
import subprocess
import uuid
import warnings
from datetime import datetime, timedelta

import cairo
from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk, Pango

# Try to import PIL for badge functionality
try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

warnings.filterwarnings("ignore", category=DeprecationWarning)

# Import modules from include directory
from include.alarm_management import AlarmManagement
from include.calendar_ui import CalendarUI
from include.debug_logger import DebugLogger, get_debug_logger
from include.ics_storage import ICSStorage
from include.multicast_sync import MulticastSync
from include.task_management import TaskManagement
from include.tray_icon import TrayIcon


class CalendarApp(
    Gtk.Window,
    CalendarUI,
    TaskManagement,
    TrayIcon,
    AlarmManagement,
):
    def __init__(self):
        Gtk.Window.__init__(self, title="CaLAN")
        self.set_default_size(900, 650)
        self.set_border_width(10)

        # Initialize debug logging
        self.debug_logger = get_debug_logger()
        self.debug_logger.logger.info("CalendarApp initialized")

        # Log PIL availability
        self.debug_logger.log_pil_availability(PIL_AVAILABLE)
        if not PIL_AVAILABLE:
            self.debug_logger.logger.warning(
                "PIL not available - tray badge functionality limited"
            )

        # Data storage
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Support multiple instances on same machine
        instance_id = os.environ.get("CALAN_INSTANCE", "1")
        if instance_id != "1":
            data_dir = os.path.join(script_dir, "ical", f"instance_{instance_id}")
        else:
            data_dir = os.path.join(script_dir, "ical")

        # Initialize ICS storage BEFORE loading tasks
        self.ics_storage = ICSStorage(data_dir)

        # Initialize settings with default name
        self.settings = {"name": os.environ.get("USER", "User")}

        # Set application icon - use absolute path and verify it exists
        self.icon_path = os.path.join(script_dir, "icon.png")
        self.icon_path = os.path.abspath(self.icon_path)  # Convert to absolute path

        # Log icon status
        if os.path.exists(self.icon_path):
            self.debug_logger.logger.info(f"Icon found: {self.icon_path}")
            self.set_icon_from_file(self.icon_path)
        else:
            self.debug_logger.logger.debug(
                f"Icon not found at {self.icon_path}, using system default"
            )
            # Try to use a system icon as fallback
            try:
                self.set_icon_name("x-office-calendar")
            except:
                pass

        # Set window title for multiple instances
        if instance_id != "1":
            self.set_title(f"CaLAN (Instance {instance_id})")
        else:
            self.set_title("CaLAN")

        # Load tasks AFTER ics_storage is initialized
        self.tasks = self.load_tasks()

        # Initialize date and view state
        # FIXED: Separate actual current date from calendar viewing date
        self.current_date = (
            datetime.now()
        )  # Today's actual date (for alarms, "today" highlighting)
        self.viewing_date = (
            datetime.now()
        )  # What month/year user is viewing in calendar
        self.selected_date = None
        self.view_mode = "calendar"
        self.triggered_alarms = set()
        self.tray_blink_timer_id = None
        self.tray_blink_state = False

        # Log initial state (debug only)
        self.debug_logger.log_comprehensive_state()

        # Create reusable CSS providers for performance
        self._css_providers = self._create_css_providers()

        # Initialize multicast sync AFTER tasks are loaded but BEFORE UI is built
        self.multicast_sync = MulticastSync(self)
        self.multicast_sync.start_listening()
        self.debug_logger.logger.info("Multicast sync initialized")

        # System tray icon - MUST be created before building UI
        self.debug_logger.logger.info("Creating modern tray icon")
        self.create_tray_icon()

        # Initial badge update after tray icon is created
        self.debug_logger.logger.debug("Performing initial badge update")
        GLib.idle_add(self.update_tray_icon_badge)

        # Build UI
        self.main_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.add(self.main_container)

        self.build_calendar_view()

        # Start alarm checker
        self.debug_logger.log_timer_operations("alarm_checker", "start")
        self.alarm_timer_id = GLib.timeout_add_seconds(1, self.check_alarms)

        # Start day change checker (check every minute)
        self.debug_logger.log_timer_operations("day_change_checker", "start")
        self.day_change_timer_id = GLib.timeout_add_seconds(60, self.check_day_change)

        # Connect window signals
        self.connect("delete-event", self.on_delete_event)
        self.connect("window-state-event", self.on_window_state_event)

        # Start periodic state logging (every 5 minutes)
        self.debug_logger.log_timer_operations("periodic_state_log", "start")
        self.periodic_state_timer_id = GLib.timeout_add_seconds(
            300, self._periodic_state_log
        )

    def _create_css_providers(self):
        """Create reusable CSS providers for better performance"""
        providers = {}

        # Hover effects
        providers["hover_today"] = Gtk.CssProvider()
        providers["hover_today"].load_from_data(
            b"* { background-color: rgba(33, 150, 243, 0.15); }"
        )

        # Blink animation for attention indicator
        providers["blink_animation"] = Gtk.CssProvider()
        providers["blink_animation"].load_from_data(
            b"""
            @keyframes blink {
                0% { opacity: 1; }
                50% { opacity: 0.3; }
                100% { opacity: 1; }
            }
            """
        )

        providers["hover_normal"] = Gtk.CssProvider()
        providers["hover_normal"].load_from_data(
            b"* { background-color: rgba(33, 150, 243, 0.05); }"
        )

        providers["hover_leave_today"] = Gtk.CssProvider()
        providers["hover_leave_today"].load_from_data(
            b"* { background-color: rgba(33, 150, 243, 0.1); }"
        )

        providers["hover_leave_normal"] = Gtk.CssProvider()
        providers["hover_leave_normal"].load_from_data(
            b"* { background-color: transparent; }"
        )

        # Drag motion
        providers["drag_motion"] = Gtk.CssProvider()
        providers["drag_motion"].load_from_data(
            b"* { background-color: rgba(76, 175, 80, 0.3); border: 2px solid #4CAF50; }"
        )

        # Drag leave
        providers["drag_leave_today"] = Gtk.CssProvider()
        providers["drag_leave_today"].load_from_data(
            b"* { background-color: rgba(33, 150, 243, 0.1); border: 1px solid #1a1a1a; }"
        )

        providers["drag_leave_normal"] = Gtk.CssProvider()
        providers["drag_leave_normal"].load_from_data(
            b"* { background-color: transparent; border: 1px solid #1a1a1a; }"
        )

        # Delete button CSS (reusable)
        providers["delete_button"] = Gtk.CssProvider()
        providers["delete_button"].load_from_data(
            b"""
            button {
                background-color: #f44336;
                color: white;
                border-radius: 8px;
                padding: 0px;
                min-width: 0px;
                min-height: 0px;
                font-size: 10px;
                font-weight: bold;
                border: none;
                transition: all 200ms ease;
            }
            button:hover {
                background-color: #ff5252;
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);
            }
            button label {
                padding: 0px;
                margin: 0px;
            }
        """
        )

        # Sync success button CSS
        providers["sync_success"] = Gtk.CssProvider()
        providers["sync_success"].load_from_data(
            b"""
            .success {
                background-color: #4CAF50;
                color: white;
                border-radius: 4px;
                font-weight: bold;
                transition: all 200ms ease;
            }
        """
        )

        return providers

    def _set_cursor(self, widget, event, cursor_type=Gdk.CursorType.HAND2):
        """Set cursor on widget"""
        window = widget.get_window()
        if window:
            window.set_cursor(Gdk.Cursor.new(cursor_type))
        return False

    def _get_user_color(self, username):
        """Generate a consistent, vibrant pastel color based on username"""
        if not username:
            return (200, 200, 200)

        import unicodedata

        name = unicodedata.normalize("NFC", username.strip())

        if not name:
            return (200, 200, 200)

        # Sum all character codes
        char_sum = sum(ord(char) for char in name)

        # Generate HUE from 0-360 (full color spectrum)
        hue = (char_sum * 137) % 360

        # Fixed saturation (70%) and lightness (80%) for vibrant pastels
        saturation = 0.7
        lightness = 0.30

        # Convert HSL to RGB
        def hsl_to_rgb(h, s, l):
            h = h / 360.0
            c = (1 - abs(2 * l - 1)) * s
            x = c * (1 - abs((h * 6) % 2 - 1))
            m = l - c / 2

            if h < 1 / 6:
                r, g, b = c, x, 0
            elif h < 2 / 6:
                r, g, b = x, c, 0
            elif h < 3 / 6:
                r, g, b = 0, c, x
            elif h < 4 / 6:
                r, g, b = 0, x, c
            elif h < 5 / 6:
                r, g, b = x, 0, c
            else:
                r, g, b = c, 0, x

            return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))

        return hsl_to_rgb(hue, saturation, lightness)

    def on_window_state_event(self, widget, event):
        """Handle window state changes (minimize)"""
        if event.new_window_state & Gdk.WindowState.ICONIFIED:
            self.hide()
        return False

    def _periodic_state_log(self):
        """Periodic comprehensive state logging"""
        self.debug_logger.log_comprehensive_state()
        self.debug_logger.log_performance_metrics()
        return True

    def quit_application(self, widget=None):
        """Properly quit the application"""
        self.debug_logger.logger.debug("Application quitting")

        # Stop multicast sync
        if hasattr(self, "multicast_sync"):
            self.multicast_sync.stop_listening()

        # Stop alarm and day change timers
        if hasattr(self, "alarm_timer_id") and self.alarm_timer_id is not None:
            GLib.source_remove(self.alarm_timer_id)
            self.alarm_timer_id = None
        if (
            hasattr(self, "day_change_timer_id")
            and self.day_change_timer_id is not None
        ):
            GLib.source_remove(self.day_change_timer_id)
            self.day_change_timer_id = None
        if (
            hasattr(self, "periodic_state_timer_id")
            and self.periodic_state_timer_id is not None
        ):
            GLib.source_remove(self.periodic_state_timer_id)
            self.periodic_state_timer_id = None

        # Clean up all blinking timers
        if hasattr(self, "_attention_blink_timers"):
            for timer_id in self._attention_blink_timers.values():
                GLib.source_remove(timer_id)
            self._attention_blink_timers.clear()

        # Clean up tray blinking timer
        if (
            hasattr(self, "tray_blink_timer_id")
            and self.tray_blink_timer_id is not None
        ):
            GLib.source_remove(self.tray_blink_timer_id)
            self.tray_blink_timer_id = None

        # Log final state (debug only)
        self.debug_logger.log_comprehensive_state()
        self.debug_logger.logger.debug("Application quit complete")

        # Let the TrayIcon class handle cleanup
        super().quit_application()

        Gtk.main_quit()

    def start_tray_blinking(self):
        """Start blinking tray icon when app is minimized and new updates arrive"""
        # Delegate to TrayIcon class
        super().start_tray_blinking()

    def stop_tray_blinking(self):
        """Stop blinking tray icon and restore normal state"""
        # Delegate to TrayIcon class
        super().stop_tray_blinking()

    def on_delete_event(self, widget, event):
        """Handle window close - show quit dialog"""
        self.debug_logger.logger.info("Window close requested - showing quit dialog")

        # Create quit confirmation dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Quit CaLAN?",
        )
        dialog.format_secondary_text("Are you sure you want to quit?")

        # FIXED: Add proper spacing to content area (30px top margin)
        content_area = dialog.get_content_area()
        content_area.set_margin_top(30)
        content_area.set_margin_bottom(10)

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            self.debug_logger.logger.info("User confirmed quit")
            self.quit_application()
            return False  # Allow the window to close
        else:
            self.debug_logger.logger.info("User canceled quit - keeping window open")
            return True  # Prevent window close

    def check_day_change(self):
        """Check if day has changed and update calendar if needed"""
        now = datetime.now()

        # FIXED: Compare against actual current_date (not viewing_date)
        if now.date() != self.current_date.date():
            old_date = self.current_date
            self.current_date = now

            # Only redraw calendar to update "today" highlighting
            # Don't change viewing_date - user's navigation is preserved
            if self.view_mode == "calendar":
                self.update_calendar()

            self.debug_logger.logger.debug(
                f"Day changed from {old_date.date()} to {now.date()} - calendar redrawn, viewing_date unchanged"
            )

            # Update tray badge for new day
            GLib.idle_add(self.update_tray_icon_badge)

        return True

    def load_tasks(self):
        """Load tasks from ICS file"""
        return self.ics_storage.load_tasks()

    def save_tasks(self):
        """Save tasks to ICS file"""
        try:
            self.ics_storage.save_tasks(self.tasks)

            # Log task save
            today_str = datetime.now().strftime("%Y-%m-%d")
            task_count = len(self.tasks.get(today_str, []))
            self.debug_logger.logger.debug(
                f"Tasks saved to ICS, today's task count: {task_count}"
            )

            # Force badge update immediately
            self.debug_logger.logger.debug(
                "Forcing tray icon badge update after task save"
            )
            self.update_tray_icon_badge()
        except Exception as e:
            self.debug_logger.log_exception(e, "save_tasks")

    def _add_blinking_effect(self, widget):
        """Add blinking effect to a widget - FIXED: Remove self-assignment and add validation"""
        if not hasattr(self, "_attention_blink_timers"):
            self._attention_blink_timers = {}

        widget_id = id(widget)

        # FIXED: Validate task_ref is set instead of self-assignment
        if not hasattr(widget, "task_ref"):
            self.debug_logger.logger.warning(
                f"Widget {widget_id} missing task_ref - blinking cleanup may fail"
            )

        def blink_callback():
            if (
                hasattr(self, "_attention_blink_timers")
                and widget_id in self._attention_blink_timers
            ):
                current_opacity = widget.get_opacity()
                new_opacity = 0.3 if current_opacity > 0.5 else 1.0
                widget.set_opacity(new_opacity)
                return True
            return False

        timer_id = GLib.timeout_add(500, blink_callback)
        self._attention_blink_timers[widget_id] = timer_id

        if not hasattr(self, "_attention_widgets"):
            self._attention_widgets = {}
        self._attention_widgets[widget_id] = widget

        # Add destroy callback to clean up timer when widget is destroyed
        def on_widget_destroy(widget):
            if (
                hasattr(self, "_attention_blink_timers")
                and widget_id in self._attention_blink_timers
            ):
                GLib.source_remove(self._attention_blink_timers[widget_id])
                del self._attention_blink_timers[widget_id]
            if (
                hasattr(self, "_attention_widgets")
                and widget_id in self._attention_widgets
            ):
                del self._attention_widgets[widget_id]

        widget.connect("destroy", on_widget_destroy)

    def _stop_blinking_for_task(self, task):
        """Stop blinking effect for a specific task - FIXED: Improved cleanup with task ID matching"""
        if (
            not hasattr(self, "_attention_blink_timers")
            or not self._attention_blink_timers
        ):
            return

        # Use task ID for matching to avoid reference issues
        task_id = task.get("id")
        if not task_id:
            return

        widgets_to_remove = []
        for widget_id, widget in getattr(self, "_attention_widgets", {}).items():
            # Match by task ID instead of object identity
            if hasattr(widget, "task_ref"):
                widget_task_id = widget.task_ref.get("id")
                if widget_task_id == task_id:
                    widgets_to_remove.append(widget_id)

        # Remove only the timers and widgets for this specific task
        for widget_id in widgets_to_remove:
            if widget_id in self._attention_blink_timers:
                GLib.source_remove(self._attention_blink_timers[widget_id])
                del self._attention_blink_timers[widget_id]
            if widget_id in self._attention_widgets:
                # FIXED: Properly clean up widget state
                widget = self._attention_widgets[widget_id]
                widget.set_opacity(1.0)
                # Disconnect any signals
                if hasattr(widget, "_blink_connections"):
                    for conn_id in widget._blink_connections:
                        try:
                            widget.disconnect(conn_id)
                        except:
                            pass
                del self._attention_widgets[widget_id]

        # FIXED: Additional cleanup to prevent memory leaks
        if (
            hasattr(self, "_attention_blink_timers")
            and not self._attention_blink_timers
        ):
            del self._attention_blink_timers
        if hasattr(self, "_attention_widgets") and not self._attention_widgets:
            del self._attention_widgets


def main():
    app = CalendarApp()
    app.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
