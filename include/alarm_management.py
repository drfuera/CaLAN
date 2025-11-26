"""
Alarm management functionality for the Calendar App
"""

import hashlib
import subprocess
from datetime import datetime

from gi.repository import GLib, Gtk


class AlarmManagement:
    def check_alarms(self):
        """Check for tasks with alarms that need to trigger"""
        now = datetime.now().replace(tzinfo=None)

        for date_str, tasks in list(self.tasks.items()):
            for i, task in enumerate(tasks):
                if task.get("alarm"):
                    alarm_time_str = task.get("alarm_time")
                    acknowledged = task.get("acknowledged", False)

                    # Use a stable alarm ID based on task content instead of date/index
                    task_id = task.get("id")
                    if task_id:
                        alarm_id = f"{task_id}:{alarm_time_str}"
                    else:
                        # Fallback for old tasks without ID - use description hash
                        desc_hash = hashlib.md5(
                            task.get("description", "").encode()
                        ).hexdigest()[:8]
                        alarm_id = f"{desc_hash}:{alarm_time_str}"

                    if not acknowledged and alarm_id not in self.triggered_alarms:
                        if alarm_time_str:
                            try:
                                alarm_time = datetime.fromisoformat(alarm_time_str)

                                # Make alarm_time offset-naive for comparison with now
                                if alarm_time.tzinfo is not None:
                                    alarm_time = alarm_time.replace(tzinfo=None)

                                # Only trigger alarms exactly at the set time
                                # 1. Alarm time is exactly now or has just passed
                                # 2. Not already acknowledged
                                time_diff = (now - alarm_time).total_seconds()

                                # Trigger alarm exactly at the set time (within 1 second)
                                if (
                                    0 <= time_diff <= 1
                                ):  # Exactly at alarm time or up to 1 second after
                                    self.triggered_alarms.add(alarm_id)
                                    GLib.idle_add(
                                        self.show_alarm_notification, date_str, task
                                    )
                                elif time_diff > 300:
                                    # Alarm is more than 5 minutes old - auto-acknowledge it
                                    # This prevents old alarms from showing up
                                    task["acknowledged"] = True
                                    self.save_tasks()

                            except (ValueError, TypeError):
                                pass

        return True

    def show_alarm_notification(self, date_str, task):
        """Show alarm notification dialog"""
        # Play alarm sound
        try:
            subprocess.Popen(
                [
                    "play",
                    "-n",
                    "synth",
                    "0.1",
                    "sine",
                    "150",
                    ":",
                    "synth",
                    "0.1",
                    "sine",
                    "200",
                    ":",
                    "synth",
                    "0.1",
                    "sine",
                    "300",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

        dialog = Gtk.Dialog(
            title="⏰ Task Reminder",
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        )
        dialog.set_default_size(450, 350)
        dialog.set_position(Gtk.WindowPosition.CENTER)
        dialog.set_keep_above(True)
        dialog.set_urgency_hint(True)

        content = dialog.get_content_area()
        content.set_spacing(15)
        content.set_border_width(20)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        date_label = Gtk.Label()
        date_label.set_markup(f"<b>Date:</b> {date_str}")
        date_label.set_halign(Gtk.Align.START)
        info_box.pack_start(date_label, False, False, 0)

        time_label = Gtk.Label()
        time_label.set_markup(f"<b>Time:</b> {task.get('time', 'N/A')}")
        time_label.set_halign(Gtk.Align.START)
        info_box.pack_start(time_label, False, False, 0)

        # Scrollable text area for description with proper padding
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(150)  # ~10 rows
        scroll.set_max_content_height(200)

        desc_view = Gtk.TextView()
        desc_view.set_wrap_mode(Gtk.WrapMode.WORD)
        desc_view.set_editable(False)
        desc_view.set_cursor_visible(False)

        # Add padding to the text view
        desc_view.set_left_margin(10)
        desc_view.set_right_margin(10)
        desc_view.set_top_margin(10)
        desc_view.set_bottom_margin(10)

        desc_view.get_buffer().set_text(task.get("description", "No description"))

        scroll.add(desc_view)
        info_box.pack_start(scroll, True, True, 0)

        content.pack_start(info_box, True, True, 0)

        check = Gtk.CheckButton(label="I acknowledge this alarm")
        content.pack_start(check, False, False, 0)

        discard_btn = dialog.add_button("Discard", Gtk.ResponseType.OK)
        discard_btn.set_sensitive(False)

        def on_check_toggled(widget):
            discard_btn.set_sensitive(widget.get_active())

        check.connect("toggled", on_check_toggled)

        dialog.show_all()
        dialog.present()

        response = dialog.run()
        if response == Gtk.ResponseType.OK and check.get_active():
            task["acknowledged"] = True
            self.save_tasks()

        dialog.destroy()
