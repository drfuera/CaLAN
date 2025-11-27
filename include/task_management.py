"""
Task management functionality for the Calendar App
"""

import json
import uuid
from datetime import datetime, timezone

from gi.repository import Gdk, GLib, Gtk, Pango


class TaskManagement:
    def show_task_view(self, date):
        """Show clean, functional task management view"""
        # FIXED: Save current tasks before switching to new date
        if (
            hasattr(self, "selected_date")
            and self.selected_date
            and self.view_mode == "tasks"
            and self.selected_date != date
        ):
            self.save_current_tasks()

        # CRITICAL: Set selected_date BEFORE clearing container
        self.selected_date = date
        self.view_mode = "tasks"

        # Clear container
        for child in self.main_container.get_children():
            self.main_container.remove(child)

        # CRITICAL: Clear task_list reference
        if hasattr(self, "task_list"):
            delattr(self, "task_list")

        # Header with icon buttons
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header_box.set_border_width(12)
        header_box.set_margin_bottom(8)

        # Back button
        back_btn = Gtk.Button.new_from_icon_name(
            "go-previous-symbolic", Gtk.IconSize.BUTTON
        )
        back_btn.set_tooltip_text("Back to calendar")
        back_btn.connect("clicked", self.close_task_view)
        header_box.pack_start(back_btn, False, False, 0)

        # Title
        title_label = Gtk.Label()
        title_label.set_markup(
            f"<span size='x-large'><b>{date.strftime('%B %d, %Y')}</b></span>"
        )
        title_label.set_xalign(0.5)
        header_box.pack_start(title_label, True, True, 0)

        # Add task button
        add_btn = Gtk.Button.new_from_icon_name(
            "list-add-symbolic", Gtk.IconSize.BUTTON
        )
        add_btn.set_tooltip_text("Add new task")
        add_btn.connect("clicked", self.add_task)
        header_box.pack_start(add_btn, False, False, 0)

        self.main_container.pack_start(header_box, False, False, 0)

        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_container.pack_start(separator, False, False, 0)

        # Main content area
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.main_container.pack_start(self.content_box, True, True, 0)

        # Show appropriate content
        task_count = len(self.tasks.get(date.isoformat(), []))
        if task_count == 0:
            self._show_empty_state()
        else:
            self._show_task_list()

        self.main_container.show_all()

    def _show_empty_state(self):
        """Show empty state"""
        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        empty_box.set_halign(Gtk.Align.CENTER)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_margin_top(60)

        empty_icon = Gtk.Label(label="📋")
        empty_icon.get_style_context().add_class(Gtk.STYLE_CLASS_DIM_LABEL)
        empty_box.pack_start(empty_icon, False, False, 0)

        empty_text = Gtk.Label(label="No tasks for this day")
        empty_text.get_style_context().add_class(Gtk.STYLE_CLASS_DIM_LABEL)
        empty_box.pack_start(empty_text, False, False, 0)

        self.content_box.pack_start(empty_box, True, True, 0)

    def _show_task_list(self):
        """Show task list"""

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_min_content_height(200)

        self.task_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.task_list.set_border_width(12)

        # Populate tasks
        date_str = self.selected_date.isoformat()
        for task in self.tasks[date_str]:
            self._add_task_row(task)

        scrolled.add(self.task_list)
        self.content_box.pack_start(scrolled, True, True, 0)
        self.content_box.set_vexpand(True)
        self.content_box.set_hexpand(True)

    def _is_valid_time(self, time_str):
        """Check if time string is valid HH:MM format"""
        if not time_str or len(time_str) != 5 or time_str.count(":") != 1:
            return False

        try:
            parts = time_str.split(":")
            if len(parts) != 2:
                return False

            hours = int(parts[0])
            minutes = int(parts[1])

            return 0 <= hours <= 23 and 0 <= minutes <= 59
        except (ValueError, IndexError):
            return False

    def _add_task_row(self, task):
        """Add a clean task row to the list"""

        # Main frame

        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        frame.task = task

        # Main container

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.set_border_width(12)
        frame.add(main_box)

        # Top row: Controls

        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Time input

        time_entry = Gtk.Entry()
        time_entry.set_placeholder_text("HH:MM")
        time_entry.set_text(task.get("time", ""))
        time_entry.set_max_length(5)
        time_entry.set_width_chars(6)
        time_entry.task = task
        time_entry.connect("key-release-event", self.on_time_key_release)
        time_entry.connect("changed", self.on_time_changed)
        controls_box.pack_start(time_entry, False, False, 0)

        # Color button

        color_btn = Gtk.Button()
        color_btn.set_tooltip_text("Change color")
        color_btn.set_size_request(32, 32)

        color_draw = Gtk.DrawingArea()
        color_draw.set_size_request(20, 20)
        color_draw.task_ref = task  # Store task reference for blinking cleanup
        color_draw.connect("draw", self.draw_color_circle)

        color_btn.connect(
            "clicked", lambda w: self.on_color_button_click(task, color_draw)
        )
        color_btn.add(color_draw)
        controls_box.pack_start(color_btn, False, False, 0)

        # Alarm box (contains both icon and checkbox)

        alarm_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        # Alarm icon
        alarm_icon = Gtk.Label(label="🔔")
        alarm_box.pack_start(alarm_icon, False, False, 0)

        # Alarm checkbox
        alarm_check = Gtk.CheckButton()
        alarm_check.set_active(task.get("alarm", False))
        alarm_check.set_tooltip_text("Set alarm")
        alarm_check.time_entry = time_entry
        alarm_check.connect("toggled", self.on_alarm_toggled, task)
        alarm_box.pack_start(alarm_check, False, False, 0)

        controls_box.pack_start(alarm_box, False, False, 0)

        # Store references for visibility control
        frame.alarm_box = alarm_box
        frame.alarm_check = alarm_check
        frame.alarm_icon = alarm_icon

        # Check initial time validity and set visibility
        time_str = task.get("time", "")
        is_valid = self._is_valid_time(time_str)

        alarm_box.set_visible(is_valid)
        alarm_box.set_no_show_all(not is_valid)

        # User name centered between alarm and delete

        user_name = task.get("profile_name", self.settings.get("name", ""))
        if user_name and user_name.strip():
            name_label = Gtk.Label()
            name_label.set_markup(f"<small>👤 {user_name}</small>")
            name_label.set_halign(Gtk.Align.CENTER)
            name_label.get_style_context().add_class(Gtk.STYLE_CLASS_DIM_LABEL)
            controls_box.pack_start(name_label, True, True, 0)
        else:
            spacer = Gtk.Box()
            controls_box.pack_start(spacer, True, True, 0)

        # Delete button

        delete_btn = Gtk.Button.new_from_icon_name(
            "edit-delete-symbolic", Gtk.IconSize.BUTTON
        )
        delete_btn.set_tooltip_text("Delete task")
        delete_btn.connect("clicked", self.delete_task, frame)
        controls_box.pack_start(delete_btn, False, False, 0)

        main_box.pack_start(controls_box, False, False, 0)

        # Description area

        desc_scroll = Gtk.ScrolledWindow()
        desc_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        desc_scroll.set_min_content_height(60)
        desc_scroll.set_max_content_height(120)
        desc_scroll.set_size_request(-1, 80)

        desc_view = Gtk.TextView()
        desc_view.set_wrap_mode(Gtk.WrapMode.WORD)
        desc_view.set_left_margin(8)
        desc_view.set_right_margin(8)
        desc_view.set_top_margin(8)
        desc_view.set_bottom_margin(8)

        # Focus handling
        desc_view.connect("focus-in-event", self._on_desc_focus_in)
        desc_view.connect("focus-out-event", self._on_desc_focus_out)

        desc_buffer = desc_view.get_buffer()
        desc_buffer.set_text(task.get("description", ""))

        def enforce_character_limit(buffer):
            """Enforce 10K character limit and handle paste operations"""
            MAX_DESCRIPTION_LENGTH = 10000

            # Get current text
            start_iter = buffer.get_start_iter()
            end_iter = buffer.get_end_iter()
            current_text = buffer.get_text(start_iter, end_iter, True)

            # Check if text exceeds limit
            if len(current_text) > MAX_DESCRIPTION_LENGTH:
                # Truncate to limit
                truncated_text = current_text[:MAX_DESCRIPTION_LENGTH]
                buffer.set_text(truncated_text)

                # Move cursor to end
                end_iter = buffer.get_end_iter()
                buffer.place_cursor(end_iter)

                # Log warning for debugging
                self.debug_logger.logger.warning(
                    f"Task description truncated to {MAX_DESCRIPTION_LENGTH} characters"
                )

        def on_description_changed(buffer):
            """Handle text changes with character limit enforcement"""
            enforce_character_limit(buffer)
            task["updated_at"] = datetime.now().isoformat()

        # Connect change handler
        desc_buffer.connect("changed", on_description_changed)

        # Also connect to paste handling to catch large pastes
        def on_paste_clipboard(text_view, clipboard):
            """Handle paste operations with character limit"""
            try:
                clipboard.request_text(
                    self._on_clipboard_text_received, (text_view, task)
                )

            except Exception as e:
                self.debug_logger.logger.error(f"Clipboard error: {e}")
            return True  # Stop default paste handler

        # Connect paste signal
        desc_view.connect("paste-clipboard", on_paste_clipboard)

        # Add text view directly to scroll (no frame to avoid X11 issues)
        desc_scroll.add(desc_view)
        main_box.pack_start(desc_scroll, True, True, 0)

        # Store references
        frame.time_entry = time_entry
        frame.desc_view = desc_view
        frame.color_draw = color_draw  # Store for blinking cleanup

        self.task_list.pack_start(frame, False, False, 0)

    def _on_clipboard_text_received(self, clipboard, text, user_data):
        """Process pasted text with character limit"""
        try:
            if not text:
                return

            text_view, task = user_data
            MAX_DESCRIPTION_LENGTH = 10000

            # Get current text
            buffer = text_view.get_buffer()
            start_iter = buffer.get_start_iter()
            end_iter = buffer.get_end_iter()
            current_text = buffer.get_text(start_iter, end_iter, True)

            # Calculate available space
            available_chars = MAX_DESCRIPTION_LENGTH - len(current_text)

            if available_chars <= 0:
                # No space left
                self.debug_logger.logger.warning(
                    "Cannot paste - task description at maximum length"
                )
                return

            # Truncate pasted text if needed
            if len(text) > available_chars:
                text = text[:available_chars]
                self.debug_logger.logger.warning(
                    f"Pasted text truncated to {available_chars} characters"
                )

            # Insert text at cursor position
            buffer.insert_at_cursor(text)

            # Enforce limit again after paste
            def enforce_character_limit(buffer):
                """Enforce character limit on text buffer"""
                text = buffer.get_text(
                    buffer.get_start_iter(), buffer.get_end_iter(), True
                )
                if len(text) > MAX_DESCRIPTION_LENGTH:
                    buffer.set_text(text[:MAX_DESCRIPTION_LENGTH])
                    buffer.place_cursor(buffer.get_end_iter())

            enforce_character_limit(buffer)
            task["updated_at"] = datetime.now().isoformat()
        except Exception as e:
            self.debug_logger.logger.error(f"Error in clipboard text processing: {e}")

    def _on_desc_focus_in(self, text_view, event):
        """Handle focus in on description field"""
        return False

    def _on_desc_focus_out(self, text_view, event):
        """Handle focus out from description field"""
        self.save_current_tasks()
        return False

    def draw_color_circle(self, widget, cr):
        """Draw clean color circle"""
        task = widget.task_ref
        color_hex = task.get("color", "#4CAF50")

        # Parse hex color
        r = int(color_hex[1:3], 16) / 255.0
        g = int(color_hex[3:5], 16) / 255.0
        b = int(color_hex[5:7], 16) / 255.0

        # Draw filled circle
        cr.arc(10, 10, 6, 0, 2 * 3.14159)
        cr.set_source_rgb(r, g, b)
        cr.fill()

        # Draw border
        cr.arc(10, 10, 6, 0, 2 * 3.14159)
        cr.set_source_rgb(0.7, 0.7, 0.7)
        cr.set_line_width(1)
        cr.stroke()

        return False

    def on_time_key_release(self, entry, event):
        """Handle time entry with auto-formatting and alarm visibility control"""
        key = event.keyval
        keyname = Gdk.keyval_name(key)

        # Always validate after ANY key press (including BackSpace/Delete)
        text = entry.get_text()

        # If navigation keys, just validate and return
        if keyname in ["Left", "Right", "Home", "End", "Tab", "Shift_L", "Shift_R"]:
            is_valid = self._is_valid_time(text)
            self._update_alarm_visibility(entry, is_valid)
            return False

        # Handle BackSpace/Delete - validate immediately
        if keyname in ["BackSpace", "Delete"]:
            is_valid = self._is_valid_time(text)
            self._update_alarm_visibility(entry, is_valid)
            entry.task["time"] = text
            self.save_current_tasks()
            return False

        digits = "".join(c for c in text if c.isdigit())

        if len(digits) > 4:
            digits = digits[:4]

        formatted = ""
        cursor_pos = len(digits)

        if len(digits) == 0:
            entry.set_text("")
            entry.task["time"] = ""
            self._update_alarm_visibility(entry, False)
            self.save_current_tasks()
            return False

        if len(digits) >= 1:
            hours = digits[: min(2, len(digits))]
            if len(hours) == 2:
                hours_int = int(hours)
                if hours_int > 23:
                    hours = "23"
            formatted = hours
            cursor_pos = len(formatted)

        if len(digits) >= 3:
            formatted += ":"
            minutes = digits[2 : min(4, len(digits))]
            if len(minutes) == 2:
                minutes_int = int(minutes)
                if minutes_int > 59:
                    minutes = "59"
            elif len(minutes) == 1:
                if int(minutes[0]) > 5:
                    minutes = "5"
            formatted += minutes
            cursor_pos = len(formatted)

        if formatted != text:
            entry.set_text(formatted)
            entry.set_position(cursor_pos)

        entry.task["time"] = entry.get_text()

        # Validate time and update alarm visibility
        is_valid = self._is_valid_time(entry.get_text())
        self._update_alarm_visibility(entry, is_valid)

        self.save_current_tasks()
        return False

    def _update_alarm_visibility(self, time_entry, is_valid):
        """Update visibility of alarm controls based on time validity"""
        # Find the frame containing this time entry
        parent = time_entry.get_parent()
        while parent and not isinstance(parent, Gtk.Frame):
            parent = parent.get_parent()

        if not parent or not hasattr(parent, "alarm_box"):
            return

        frame = parent
        task = time_entry.task

        if is_valid:
            # Show alarm controls
            frame.alarm_box.set_visible(True)
            frame.alarm_box.set_no_show_all(False)
            frame.alarm_box.show_all()
        else:
            # Hide alarm controls and disable alarm if it was enabled
            if task.get("alarm", False):
                task["alarm"] = False
                task["alarm_time"] = None
                task["acknowledged"] = False
                if hasattr(frame, "alarm_check"):
                    frame.alarm_check.set_active(False)
                self.save_current_tasks()

            frame.alarm_box.set_visible(False)
            frame.alarm_box.set_no_show_all(True)

    def on_time_changed(self, entry):
        """Update alarm time if alarm is active and time changes"""
        task = entry.task
        time_str = entry.get_text()

        task["updated_at"] = datetime.now().isoformat()
        self.save_current_tasks()

        # Only process alarm time if time is valid
        if not self._is_valid_time(time_str):
            return

        if task.get("alarm") and time_str and ":" in time_str and len(time_str) == 5:
            try:
                hour, minute = map(int, time_str.split(":"))
                if self.selected_date:
                    alarm_datetime = datetime.combine(
                        self.selected_date, datetime.min.time()
                    )
                    alarm_datetime = alarm_datetime.replace(hour=hour, minute=minute)

                    # FIXED: Validate alarm time is in the future
                    if alarm_datetime > datetime.now():
                        task["alarm_time"] = alarm_datetime.isoformat()
                        task["acknowledged"] = False
                        date_str = self.selected_date.isoformat()
                        self.triggered_alarms = {
                            aid
                            for aid in self.triggered_alarms
                            if not aid.startswith(f"{date_str}:")
                        }
                        self.save_current_tasks()
                    else:
                        # Alarm time is in the past - show warning and disable alarm
                        self.debug_logger.logger.warning(
                            f"Alarm time {alarm_datetime} is in the past - disabling alarm"
                        )
                        task["alarm"] = False
                        task["alarm_time"] = None
                        # Update UI to reflect disabled alarm
                        parent = entry.get_parent()
                        while parent and not isinstance(parent, Gtk.Frame):
                            parent = parent.get_parent()
                        if parent and hasattr(parent, "alarm_check"):
                            parent.alarm_check.set_active(False)
                        self.save_current_tasks()
            except (ValueError, AttributeError):
                pass

    def on_color_button_click(self, task, draw_area):
        """Open color chooser"""
        dialog = Gtk.ColorChooserDialog(title="Choose Task Color", transient_for=self)
        dialog.set_modal(True)

        # Set current color
        rgba = Gdk.RGBA()
        if rgba.parse(task.get("color", "#4CAF50")):
            dialog.set_rgba(rgba)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            selected_color = dialog.get_rgba()
            hex_color = "#{:02x}{:02x}{:02x}".format(
                int(selected_color.red * 255),
                int(selected_color.green * 255),
                int(selected_color.blue * 255),
            )
            task["color"] = hex_color
            task["updated_at"] = datetime.now().isoformat()
            draw_area.queue_draw()
            self.save_current_tasks()

            # Broadcast color change
            if hasattr(self, "multicast_sync"):
                task["date"] = self.selected_date.isoformat()
                self.multicast_sync.broadcast_task_update(task, "update")

        dialog.destroy()

    def on_alarm_toggled(self, check, task):
        """Handle alarm toggle"""
        was_alarm = task.get("alarm", False)
        new_alarm_state = check.get_active()
        self.debug_logger.logger.debug(
            f"on_alarm_toggled: was_alarm={was_alarm}, new_alarm_state={new_alarm_state}"
        )

        if was_alarm != new_alarm_state:
            # Validate alarm time before saving
            if new_alarm_state:
                time_entry = check.time_entry
                time_str = time_entry.get_text()
                self.debug_logger.logger.debug(
                    f"Alarm enabled, time_str='{time_str}', has time_entry={hasattr(check, 'time_entry')}"
                )

                # Check if time is valid
                if not self._is_valid_time(time_str):
                    self.debug_logger.logger.debug("Invalid time format for alarm")
                    check.set_active(False)
                    return

                try:
                    hour, minute = map(int, time_str.split(":"))
                    if self.selected_date:
                        alarm_datetime = datetime.combine(
                            self.selected_date, datetime.min.time()
                        )
                        alarm_datetime = alarm_datetime.replace(
                            hour=hour, minute=minute
                        )

                        # FIXED: Validate alarm time is in the future
                        if alarm_datetime <= datetime.now():
                            self.debug_logger.logger.warning(
                                f"Alarm time {alarm_datetime} is in the past - cannot enable alarm"
                            )
                            # Show user feedback
                            dialog = Gtk.MessageDialog(
                                transient_for=self,
                                flags=0,
                                message_type=Gtk.MessageType.WARNING,
                                buttons=Gtk.ButtonsType.OK,
                                text="Cannot set alarm in the past",
                            )
                            dialog.format_secondary_text(
                                "Please set an alarm time in the future."
                            )
                            dialog.run()
                            dialog.destroy()
                            check.set_active(False)
                            return

                        # Always allow alarm setting for future times
                        task["alarm_time"] = alarm_datetime.isoformat()
                        task["acknowledged"] = False
                        self.debug_logger.logger.debug(
                            f"Alarm time set: {alarm_datetime}"
                        )
                except (ValueError, AttributeError) as e:
                    # Invalid time format, don't enable alarm
                    self.debug_logger.logger.debug(f"Invalid time format: {e}")
                    check.set_active(False)
                    return

            task["alarm"] = new_alarm_state
            task["updated_at"] = datetime.now().isoformat()
            self.debug_logger.logger.debug(
                f"Task alarm set to {new_alarm_state}, saving..."
            )

            self.save_current_tasks()

            # Broadcast alarm change
            if hasattr(self, "multicast_sync"):
                task["date"] = self.selected_date.isoformat()
                self.multicast_sync.broadcast_task_update(task, "update")
        elif not task["alarm"] and was_alarm:
            task["alarm_time"] = None
            task["acknowledged"] = False
            self.save_current_tasks()

    def save_current_tasks(self):
        """Save currently displayed tasks"""
        if self.view_mode != "tasks" or not self.selected_date:
            self.debug_logger.logger.debug(
                "save_current_tasks: Not in task view or no selected date"
            )
            return

        if not hasattr(self, "task_list") or not self.task_list:
            self.debug_logger.logger.debug("save_current_tasks: No task list")
            return

        date_str = self.selected_date.isoformat()
        tasks = []
        has_changes = False

        self.debug_logger.logger.debug(
            f"save_current_tasks: Processing tasks for date {date_str}"
        )

        for frame in self.task_list.get_children():
            if hasattr(frame, "task"):
                task = frame.task
                task_id = task.get("id", "unknown")

                # Get time
                if hasattr(frame, "time_entry"):
                    old_time = task.get("time", "")
                    new_time = frame.time_entry.get_text()
                    if old_time != new_time:
                        self.debug_logger.logger.debug(
                            f"save_current_tasks: Time changed for task {task_id}: '{old_time}' -> '{new_time}'"
                        )
                        task["time"] = new_time
                        task["updated_at"] = datetime.now().isoformat()
                        has_changes = True
                    else:
                        task["time"] = new_time

                # Get description
                if hasattr(frame, "desc_view"):
                    buffer = frame.desc_view.get_buffer()
                    start = buffer.get_start_iter()
                    end = buffer.get_end_iter()
                    new_description = buffer.get_text(start, end, False)

                    # Final safety check: enforce 10K character limit
                    MAX_DESCRIPTION_LENGTH = 10000
                    if len(new_description) > MAX_DESCRIPTION_LENGTH:
                        new_description = new_description[:MAX_DESCRIPTION_LENGTH]
                        self.debug_logger.logger.warning(
                            f"save_current_tasks: Task description truncated to {MAX_DESCRIPTION_LENGTH} characters"
                        )

                    old_description = task.get("description", "")
                    if old_description != new_description:
                        self.debug_logger.logger.debug(
                            f"save_current_tasks: Description changed for task {task_id}: '{old_description}' -> '{new_description}'"
                        )
                        task["description"] = new_description
                        task["updated_at"] = datetime.now().isoformat()
                        has_changes = True
                    else:
                        task["description"] = new_description

                # Get alarm state
                if hasattr(frame, "alarm_check"):
                    old_alarm = task.get("alarm", False)
                    new_alarm = frame.alarm_check.get_active()
                    if old_alarm != new_alarm:
                        self.debug_logger.logger.debug(
                            f"save_current_tasks: Alarm changed for task {task_id}: {old_alarm} -> {new_alarm}"
                        )
                        task["alarm"] = new_alarm
                        task["updated_at"] = datetime.now().isoformat()
                        has_changes = True

                # Clear needs_attention flag
                if "needs_attention" in task:
                    self.debug_logger.logger.debug(
                        f"save_current_tasks: Clearing needs_attention for task {task_id}"
                    )
                    del task["needs_attention"]
                    self._stop_blinking_for_task(task)
                    has_changes = True

                tasks.append(task)

        if tasks:
            self.tasks[date_str] = tasks
        elif date_str in self.tasks:
            self.debug_logger.logger.debug(
                f"save_current_tasks: Removing date {date_str} from tasks (no tasks left)"
            )
            del self.tasks[date_str]
            has_changes = True

        if has_changes:
            self.debug_logger.logger.debug(
                f"save_current_tasks: Saving {len(tasks)} tasks for date {date_str}"
            )
            self.save_tasks()

            # Broadcast task updates for all modified tasks
            if hasattr(self, "multicast_sync"):
                for task in tasks:
                    task["date"] = date_str
                    self.multicast_sync.broadcast_task_update(task, "update")
        else:
            self.debug_logger.logger.debug("save_current_tasks: No changes detected")

    def delete_task(self, widget, frame):
        """Delete a task - remove completely from tasks and ICS"""
        if not self.selected_date:
            return

        date_str = self.selected_date.isoformat()
        task_to_remove = getattr(frame, "task", None)

        if task_to_remove and date_str in self.tasks:
            if task_to_remove in self.tasks[date_str]:
                # Remove task completely from tasks
                self.tasks[date_str].remove(task_to_remove)
                if not self.tasks[date_str]:
                    del self.tasks[date_str]

        # Remove from UI
        if hasattr(self, "task_list"):
            self.task_list.remove(frame)

        # FIXED: Immediate save to prevent data loss
        self.save_tasks()

        # Broadcast delete operation
        if hasattr(self, "multicast_sync") and task_to_remove:
            task_to_remove["date"] = date_str
            self.multicast_sync.broadcast_task_update(task_to_remove, "delete")

        # Update UI if no tasks left
        date_str = self.selected_date.isoformat()
        if len(self.tasks.get(date_str, [])) == 0:
            for child in self.content_box.get_children():
                self.content_box.remove(child)
            self._show_empty_state()
            self.content_box.show_all()

            # Also update calendar view to remove task indicators
            if hasattr(self, "update_calendar"):
                self.update_calendar()

    def close_task_view(self, widget):
        """Close task view and return to calendar"""
        if self.selected_date:
            self.save_current_tasks()

        self.view_mode = "calendar"
        for child in self.main_container.get_children():
            self.main_container.remove(child)

        if hasattr(self, "header"):
            self.main_container.pack_start(self.header, False, False, 0)
        if hasattr(self, "calendar_scroll"):
            self.main_container.pack_start(self.calendar_scroll, True, True, 0)

        self.update_calendar()
        self.show_all()

    def add_task(self, widget):
        """Add a new task"""
        if not self.selected_date:
            return

        task = {
            "id": str(uuid.uuid4()),
            "time": "",
            "description": "",
            "color": "#4CAF50",
            "alarm": False,
            "alarm_time": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "profile_name": self.settings.get("name", ""),
        }

        date_str = self.selected_date.isoformat()
        if date_str not in self.tasks:
            self.tasks[date_str] = []
        self.tasks[date_str].append(task)

        if "needs_attention" in task:
            del task["needs_attention"]
            self._stop_blinking_for_task(task)

        # FIXED: Save immediately to prevent data loss
        self.save_tasks()

        # Update UI
        if len(self.tasks[date_str]) == 1:
            # Clear content box and show task list directly
            for child in self.content_box.get_children():
                self.content_box.remove(child)
            self._show_task_list()
            self.content_box.show_all()
            if hasattr(self, "task_list") and self.task_list:
                self.task_list.show_all()
            self.main_container.show_all()

            # Debug: Force immediate refresh and log visibility
            self.debug_logger.logger.info(
                f"Content box visible: {self.content_box.get_visible()}"
            )
            self.debug_logger.logger.info(
                f"Content box allocated size: {self.content_box.get_allocated_width()}x{self.content_box.get_allocated_height()}"
            )
            self.main_container.queue_draw()
            while Gtk.events_pending():
                Gtk.main_iteration()

        else:
            self._add_task_row(task)
            self.task_list.show_all()
            self.main_container.queue_draw()

    def _update_task_ui(self, task_id, date_str):
        """Update UI for a specific task when synced from multicast"""
        if not hasattr(self, "task_list") or not self.task_list:
            return

        # Get the actual task data from storage (not just the UI frame)
        actual_task = None
        if date_str in self.tasks:
            for t in self.tasks[date_str]:
                if t.get("id") == task_id:
                    actual_task = t
                    break

        if not actual_task:
            return

        # Find the task frame with matching ID
        for frame in self.task_list.get_children():
            if hasattr(frame, "task") and frame.task.get("id") == task_id:
                # Update the frame's task data with the actual data
                frame.task.update(actual_task)
                task = frame.task

                # Update alarm checkbox if it exists
                if hasattr(frame, "alarm_check"):
                    current_alarm_state = frame.alarm_check.get_active()
                    new_alarm_state = task.get("alarm", False)

                    if current_alarm_state != new_alarm_state:
                        # Block signal to avoid triggering save_current_tasks
                        frame.alarm_check.handler_block_by_func(self.on_alarm_toggled)
                        frame.alarm_check.set_active(new_alarm_state)
                        frame.alarm_check.handler_unblock_by_func(self.on_alarm_toggled)

                # Update alarm time if it exists
                if hasattr(frame, "alarm_time") and task.get("alarm_time"):
                    current_alarm_time = frame.alarm_time.get_text()
                    new_alarm_time = task.get("alarm_time", "")
                    if current_alarm_time != new_alarm_time:
                        frame.alarm_time.set_text(new_alarm_time)

                # Update time entry if it exists
                if hasattr(frame, "time_entry"):
                    current_time = frame.time_entry.get_text()
                    new_time = task.get("time", "")
                    if current_time != new_time:
                        frame.time_entry.set_text(new_time)
                        # Update alarm visibility based on new time
                        is_valid = self._is_valid_time(new_time)
                        self._update_alarm_visibility(frame.time_entry, is_valid)

                # Update description if it exists
                if hasattr(frame, "desc_view"):
                    buffer = frame.desc_view.get_buffer()
                    current_text = buffer.get_text(
                        buffer.get_start_iter(), buffer.get_end_iter(), False
                    )
                    new_text = task.get("description", "")
                    if current_text != new_text:
                        buffer.set_text(new_text)

                # Update profile name if it exists (user indicator)
                if hasattr(frame, "user_label"):
                    current_user = frame.user_label.get_text()
                    new_user = task.get("profile_name", "")
                    if current_user != new_user:
                        frame.user_label.set_text(new_user)

                # Update color visually (the draw area will update on next redraw)
                if hasattr(frame, "draw_area"):
                    frame.draw_area.queue_draw()

                break
