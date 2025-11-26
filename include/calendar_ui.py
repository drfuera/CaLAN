"""
Calendar UI components for the Calendar App
"""

import calendar
import json
from datetime import datetime

import cairo
from gi.repository import Gdk, Gtk, Pango


class CalendarUI:
    def build_calendar_view(self):
        """Build the calendar view"""
        # Clear container
        for child in self.main_container.get_children():
            self.main_container.remove(child)

        # Header with month/year selectors
        self.header = self.create_header()
        self.main_container.pack_start(self.header, False, False, 0)

        # Calendar grid
        self.calendar_grid = Gtk.Grid()
        self.calendar_grid.set_column_homogeneous(True)
        self.calendar_grid.set_row_homogeneous(True)
        self.calendar_grid.set_column_spacing(2)
        self.calendar_grid.set_row_spacing(2)

        self.calendar_scroll = Gtk.ScrolledWindow()
        self.calendar_scroll.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
        )
        self.calendar_scroll.add(self.calendar_grid)
        self.main_container.pack_start(self.calendar_scroll, True, True, 0)

        self.update_calendar()
        self.show_all()

    def create_header(self):
        """Create header with month/year selectors"""
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # Full sync button - placed on left side
        sync_btn = Gtk.Button()
        sync_icon = Gtk.Image.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON)
        sync_btn.add(sync_icon)
        sync_btn.set_tooltip_text("Full sync with network")
        sync_btn.connect("clicked", self.on_full_sync_clicked)
        sync_btn.connect("enter-notify-event", self._set_cursor)
        sync_btn.connect(
            "leave-notify-event",
            lambda w, e: self._set_cursor(w, e, Gdk.CursorType.ARROW),
        )
        header_box.pack_start(sync_btn, False, False, 0)

        # Left spacer - pushes month/year to center
        left_spacer = Gtk.Label()
        header_box.pack_start(left_spacer, True, True, 0)

        # Previous month button
        prev_btn = Gtk.Button()
        prev_icon = Gtk.Image.new_from_icon_name("go-previous", Gtk.IconSize.BUTTON)
        prev_btn.add(prev_icon)
        prev_btn.set_tooltip_text("Previous month")
        prev_btn.connect("clicked", self.on_previous_month)
        prev_btn.connect("enter-notify-event", self._set_cursor)
        prev_btn.connect(
            "leave-notify-event",
            lambda w, e: self._set_cursor(w, e, Gdk.CursorType.ARROW),
        )
        header_box.pack_start(prev_btn, False, False, 0)

        # Month selector
        self.month_combo = Gtk.ComboBoxText()
        for i, month_name in enumerate(calendar.month_name[1:], 1):
            self.month_combo.append_text(month_name)
        # FIXED: Use viewing_date instead of current_date
        self.month_combo.set_active(self.viewing_date.month - 1)
        self.month_combo.connect("changed", self.on_month_changed)
        header_box.pack_start(self.month_combo, False, False, 0)

        # Year selector
        self.year_spin = Gtk.SpinButton()
        self.year_spin.set_range(1900, 2100)
        self.year_spin.set_increments(1, 10)
        # FIXED: Use viewing_date instead of current_date
        self.year_spin.set_value(self.viewing_date.year)
        self.year_spin.connect("value-changed", self.on_year_changed)
        header_box.pack_start(self.year_spin, False, False, 0)

        # Next month button
        next_btn = Gtk.Button()
        next_icon = Gtk.Image.new_from_icon_name("go-next", Gtk.IconSize.BUTTON)
        next_btn.add(next_icon)
        next_btn.set_tooltip_text("Next month")
        next_btn.connect("clicked", self.on_next_month)
        next_btn.connect("enter-notify-event", self._set_cursor)
        next_btn.connect(
            "leave-notify-event",
            lambda w, e: self._set_cursor(w, e, Gdk.CursorType.ARROW),
        )
        header_box.pack_start(next_btn, False, False, 0)

        # Right spacer for alignment
        right_spacer = Gtk.Label()
        header_box.pack_start(right_spacer, True, True, 0)

        return header_box

    def on_full_sync_clicked(self, button):
        """Handle full sync button click"""
        self.debug_logger.logger.info("Full sync button clicked")
        if hasattr(self, "multicast_sync"):
            self.multicast_sync.full_sync()

    def on_month_changed(self, combo):
        """Handle month selection change"""
        month = combo.get_active() + 1
        # FIXED: Use viewing_date instead of current_date
        year = self.viewing_date.year

        try:
            # FIXED: Update viewing_date, not current_date
            self.viewing_date = self.viewing_date.replace(month=month)
        except ValueError:
            import calendar

            last_day = calendar.monthrange(year, month)[1]
            self.viewing_date = self.viewing_date.replace(month=month, day=last_day)

        self.update_calendar()

    def on_year_changed(self, spin):
        """Handle year selection change"""
        year = int(spin.get_value())
        # FIXED: Use viewing_date instead of current_date
        month = self.viewing_date.month

        try:
            # FIXED: Update viewing_date, not current_date
            self.viewing_date = self.viewing_date.replace(year=year)
        except ValueError:
            import calendar

            last_day = calendar.monthrange(year, month)[1]
            self.viewing_date = self.viewing_date.replace(year=year, day=last_day)

        self.update_calendar()

    def update_calendar(self):
        """Update the calendar grid display"""

        # Clear existing grid
        for child in self.calendar_grid.get_children():
            self.calendar_grid.remove(child)

        # Add day headers
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, day in enumerate(days):
            label = Gtk.Label(label=day)
            label.set_markup(f"<b>{day}</b>")
            self.calendar_grid.attach(label, i, 0, 1, 1)

        # FIXED: Get calendar data from viewing_date (not current_date)
        year = self.viewing_date.year
        month = self.viewing_date.month
        cal = calendar.monthcalendar(year, month)

        # Add date cells
        # FIXED: Use current_date for "today" highlighting only
        today = self.current_date.date()
        row = 1
        next_month_day_counter = 1

        for week in cal:
            if row == 1:
                leading_zeros = sum(1 for d in week if d == 0)

            for col, day in enumerate(week):
                if day == 0:
                    if row == 1:
                        prev_month = month - 1 if month > 1 else 12
                        prev_year = year if month > 1 else year - 1
                        days_in_prev = calendar.monthrange(prev_year, prev_month)[1]
                        prev_day = days_in_prev - leading_zeros + col + 1
                        date = datetime(prev_year, prev_month, prev_day).date()
                        cell = self.create_date_cell(
                            prev_day, date, False, grayed_out=True
                        )
                    else:
                        next_month = month + 1 if month < 12 else 1
                        next_year = year if month < 12 else year + 1
                        date = datetime(
                            next_year, next_month, next_month_day_counter
                        ).date()
                        cell = self.create_date_cell(
                            next_month_day_counter, date, False, grayed_out=True
                        )
                        next_month_day_counter += 1
                    self.calendar_grid.attach(cell, col, row, 1, 1)
                else:
                    date = datetime(year, month, day).date()
                    # Check if this date is today (for highlighting)
                    cell = self.create_date_cell(day, date, date == today)
                    self.calendar_grid.attach(cell, col, row, 1, 1)
            row += 1

        self.calendar_grid.show_all()

    def create_date_cell(self, day, date, is_today, grayed_out=False):
        """Create a calendar date cell with header and content area"""
        event_box = Gtk.EventBox()

        event_box.connect(
            "realize",
            lambda w: w.get_window().set_cursor(Gdk.Cursor.new(Gdk.CursorType.ARROW)),
        )

        main_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # === HEADER BAR with darker background ===
        header_bar = Gtk.EventBox()
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header_box.set_border_width(5)

        # Day number on LEFT
        day_label = Gtk.Label()
        day_label.set_halign(Gtk.Align.START)
        if grayed_out:
            day_label.set_markup(
                f"<span foreground='#888888' size='small'>{day}</span>"
            )
        elif is_today:
            day_label.set_markup(
                f"<span weight='bold' foreground='#2196F3' size='medium'>{day}</span>"
            )
        else:
            day_label.set_markup(
                f"<span foreground='#FFFFFF' size='small'>{day}</span>"
            )
        header_box.pack_start(day_label, False, False, 0)

        # Spacer to push alarm to right
        spacer = Gtk.Label()
        header_box.pack_start(spacer, True, True, 0)

        # Alarm bell on RIGHT (if has active alarm)
        date_str = date.isoformat()
        if date_str in self.tasks:
            has_alarm = any(
                task.get("alarm", False) and not task.get("acknowledged", False)
                for task in self.tasks[date_str]
            )
            if has_alarm:
                bell = Gtk.Label()
                if grayed_out:
                    bell.set_markup("<span foreground='#CC8A22' size='small'>🔔</span>")
                else:
                    bell.set_markup("<span foreground='#FFA726' size='small'>🔔</span>")
                header_box.pack_start(bell, False, False, 0)

        header_bar.add(header_box)

        # Style header bar with darker background
        header_css = Gtk.CssProvider()
        if grayed_out:
            header_css.load_from_data(b"* { background-color: rgba(60, 60, 60, 0.4); }")
        else:
            header_css.load_from_data(b"* { background-color: rgba(40, 40, 40, 0.6); }")
        header_bar.get_style_context().add_provider(
            header_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        main_container.pack_start(header_bar, False, False, 0)

        # === CONTENT AREA for task rows ===
        content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        content_area.set_margin_start(2)
        content_area.set_margin_end(2)
        content_area.set_border_width(3)

        # Task rows (each task gets its own row)
        if date_str in self.tasks:
            for i, task in enumerate(self.tasks[date_str][:3]):
                # Wrap task row in EventBox to make it draggable
                task_event_box = Gtk.EventBox()

                task_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
                task_row.set_halign(Gtk.Align.START)

                # Color dot or attention indicator - align to top
                color_dot = Gtk.Label()
                color = task.get("color", "#4CAF50")

                # Check if task needs attention
                if task.get("needs_attention", False):
                    if grayed_out:
                        color_dot.set_markup(
                            "<span foreground='#ff4444' alpha='50%' size='small' weight='bold'>◉</span>"
                        )
                    else:
                        color_dot.set_markup(
                            "<span foreground='#ff4444' size='small' weight='bold'>◉</span>"
                        )
                    self._add_blinking_effect(color_dot)
                else:
                    if grayed_out:
                        color_dot.set_markup(
                            f"<span foreground='{color}' alpha='50%' size='small'>●</span>"
                        )
                    else:
                        color_dot.set_markup(
                            f"<span foreground='{color}' size='small'>●</span>"
                        )
                color_dot.set_valign(Gtk.Align.START)
                color_dot.set_margin_top(0)
                task_row.pack_start(color_dot, False, False, 0)

                # Task text - single line, ellipsized
                task_text = Gtk.Label()
                task_text.set_halign(Gtk.Align.START)
                task_text.set_ellipsize(Pango.EllipsizeMode.END)
                task_text.set_single_line_mode(True)
                task_text.set_valign(Gtk.Align.START)
                task_text.set_margin_top(3)

                description = task.get("description", "").strip()
                if not description:
                    description = "No description"

                if grayed_out:
                    task_text.set_markup(
                        f"<span foreground='#888888' size='x-small'>{description}</span>"
                    )
                else:
                    task_text.set_markup(
                        f"<span foreground='#CCCCCC' size='x-small'>{description}</span>"
                    )

                task_row.pack_start(task_text, True, True, 0)

                task_event_box.add(task_row)

                task_row.set_margin_start(3)
                task_row.set_margin_end(3)
                task_row.set_margin_top(0)
                task_row.set_margin_bottom(2)

                # Add colored background if task belongs to different user
                task_owner = task.get("profile_name", "")
                current_user = self.settings.get("name", "")

                if task_owner and task_owner != current_user:
                    r, g, b = self._get_user_color(task_owner)

                    task_css = Gtk.CssProvider()
                    css_data = f"* {{ background-color: rgba({r}, {g}, {b}, 0.35); border-radius: 2px; }}".encode()
                    task_css.load_from_data(css_data)
                    task_event_box.get_style_context().add_provider(
                        task_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                    )

                # Make this specific task row draggable
                task_event_box.drag_source_set(
                    Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.MOVE
                )
                task_event_box.drag_source_add_text_targets()

                task_event_box.connect("enter-notify-event", self._set_cursor)
                task_event_box.connect(
                    "leave-notify-event",
                    lambda w, e: self._set_cursor(w, e, Gdk.CursorType.ARROW),
                )

                task_id = task.get("id", str(i))

                task_event_box.connect(
                    "drag-begin", self.on_task_drag_begin, date, task_id, task
                )
                task_event_box.connect(
                    "drag-data-get", self.on_task_drag_data_get, date, task_id
                )

                content_area.pack_start(task_event_box, False, False, 0)

            # Show "+X more" if there are more than 3 tasks
            if len(self.tasks[date_str]) > 3:
                more_label = Gtk.Label()
                more_count = len(self.tasks[date_str]) - 3
                if grayed_out:
                    more_label.set_markup(
                        f"<span foreground='#888888' size='x-small'>+{more_count} more</span>"
                    )
                else:
                    more_label.set_markup(
                        f"<span size='x-small'>+{more_count} more</span>"
                    )
                more_label.set_halign(Gtk.Align.START)
                more_label.set_valign(Gtk.Align.START)
                more_label.set_margin_top(2)
                content_area.pack_start(more_label, False, False, 0)

        main_container.pack_start(content_area, True, True, 0)

        event_box.add(main_container)

        # Store state
        event_box.is_today = is_today
        event_box.is_grayed = grayed_out

        # Background for whole cell
        css_bg = Gtk.CssProvider()
        if is_today:
            css_bg.load_from_data(b"* { background-color: rgba(33, 150, 243, 0.1); }")
        else:
            css_bg.load_from_data(b"* { background-color: transparent; }")
        event_box.get_style_context().add_provider(
            css_bg, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Hover events
        event_box.connect("enter-notify-event", self.on_date_hover_enter)
        event_box.connect("leave-notify-event", self.on_date_hover_leave)

        # Border
        css_border = Gtk.CssProvider()
        if grayed_out:
            css_border.load_from_data(
                b"* { border: 1px solid #333333; border-radius: 3px; }"
            )
        else:
            css_border.load_from_data(
                b"* { border: 1px solid #1a1a1a; border-radius: 3px; }"
            )
        event_box.get_style_context().add_provider(
            css_border, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Enable drag destination
        event_box.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.MOVE)
        event_box.drag_dest_add_text_targets()
        event_box.connect("drag-motion", self.on_drag_motion, date)
        event_box.connect("drag-leave", self.on_drag_leave, date)
        event_box.connect("drag-data-received", self.on_drag_data_received, date)

        # Double-click event only for non-grayed-out dates
        if not grayed_out:
            event_box.connect("button-press-event", self.on_date_clicked, date)

        return event_box

    def on_date_clicked(self, widget, event, date):
        """Handle date cell click"""
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.show_task_view(date)
        return True

    def on_task_drag_begin(self, widget, drag_context, date, task_id, task):
        """Handle drag begin for a specific task - create visual feedback"""
        task_text = task.get("description", "Task").strip()
        if not task_text:
            task_text = "Task"

        if len(task_text) > 20:
            task_text = task_text[:17] + "..."

        text_width = max(len(task_text) * 6, 50)
        surface_height = 30

        surface = Gdk.Window.create_similar_surface(
            widget.get_window(), cairo.CONTENT_COLOR_ALPHA, text_width, surface_height
        )
        cr = cairo.Context(surface)

        cr.set_source_rgba(0.2, 0.2, 0.2, 0.9)
        cr.rectangle(0, 0, text_width, surface_height)
        cr.fill()

        cr.set_source_rgb(1, 1, 1)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(12)
        cr.move_to(5, 18)
        cr.show_text(task_text)

        Gtk.drag_set_icon_surface(drag_context, surface)

    def on_task_drag_data_get(
        self, widget, drag_context, data, info, time, date, task_id
    ):
        """Provide drag data for specific task"""
        drag_data = json.dumps({"date": date.isoformat(), "task_id": task_id})
        data.set_text(drag_data, -1)

    def on_date_hover_enter(self, widget, event):
        """Handle mouse entering date cell"""
        if widget.is_today:
            css_provider = self._css_providers["hover_today"]
        else:
            css_provider = self._css_providers["hover_normal"]

        widget.get_style_context().add_provider(
            css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        return False

    def on_date_hover_leave(self, widget, event):
        """Handle mouse leaving date cell"""
        if widget.is_today:
            css_provider = self._css_providers["hover_leave_today"]
        else:
            css_provider = self._css_providers["hover_leave_normal"]

        widget.get_style_context().add_provider(
            css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        return False

    def on_drag_motion(self, widget, drag_context, x, y, time, date):
        """Handle drag motion over date cell"""
        widget.get_style_context().add_provider(
            self._css_providers["drag_motion"], Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        Gdk.drag_status(drag_context, Gdk.DragAction.MOVE, time)
        return True

    def on_drag_leave(self, widget, drag_context, time, date):
        """Handle drag leaving date cell"""
        if widget.is_today:
            css_provider = self._css_providers["drag_leave_today"]
        else:
            css_provider = self._css_providers["drag_leave_normal"]

        widget.get_style_context().add_provider(
            css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def on_drag_data_received(
        self, widget, drag_context, x, y, data, info, time, target_date
    ):
        """Handle dropped data - move task from source to target date"""
        if data and data.get_text():
            try:
                drag_text = data.get_text()

                try:
                    drag_info = json.loads(drag_text)
                    source_date_str = drag_info["date"]
                    task_id = drag_info["task_id"]
                except (json.JSONDecodeError, KeyError):
                    source_date_str = drag_text
                    task_id = None

                source_date = datetime.fromisoformat(source_date_str).date()
                target_date_str = target_date.isoformat()

                if source_date_str == target_date_str:
                    drag_context.finish(False, False, time)
                    return

                if source_date_str in self.tasks and self.tasks[source_date_str]:
                    task_to_move = None
                    task_index = None

                    if task_id is not None:
                        for i, task in enumerate(self.tasks[source_date_str]):
                            if task.get("id", str(i)) == task_id:
                                task_to_move = task
                                task_index = i
                                break

                    if task_to_move is None:
                        task_to_move = self.tasks[source_date_str][0]
                        task_index = 0

                    # Add task to target FIRST to prevent data loss
                    if target_date_str not in self.tasks:
                        self.tasks[target_date_str] = []
                    self.tasks[target_date_str].append(task_to_move)

                    # Then remove from source
                    if task_index is not None:
                        self.tasks[source_date_str].pop(task_index)

                    if not self.tasks[source_date_str]:
                        del self.tasks[source_date_str]

                    # Update alarm_time if task has an alarm
                    if task_to_move.get("alarm") and task_to_move.get("alarm_time"):
                        try:
                            old_alarm_time = datetime.fromisoformat(
                                task_to_move["alarm_time"]
                            )
                            new_alarm_time = datetime.combine(
                                target_date, old_alarm_time.time()
                            )
                            task_to_move["alarm_time"] = new_alarm_time.isoformat()
                            task_to_move["acknowledged"] = False

                        except (ValueError, TypeError):
                            task_to_move["alarm_time"] = None

                    # Update timestamp
                    task_to_move["updated_at"] = datetime.now().isoformat()

                    # Sync with other instances via multicast
                    if hasattr(self, "multicast_sync"):
                        # Create task update with both old and new dates
                        sync_task = task_to_move.copy()
                        sync_task["date"] = target_date_str
                        sync_task["old_date"] = source_date_str
                        self.multicast_sync.broadcast_task_update(
                            sync_task, operation="move"
                        )

                    # Clean up triggered alarms
                    if hasattr(self, "triggered_alarms"):
                        task_id = task_to_move.get("id")
                        if task_id:
                            self.triggered_alarms = {
                                alarm_id
                                for alarm_id in self.triggered_alarms
                                if not alarm_id.startswith(f"{task_id}:")
                            }
                        else:
                            alarm_time_str = task_to_move.get("alarm_time")
                            if alarm_time_str:
                                self.triggered_alarms = {
                                    alarm_id
                                    for alarm_id in self.triggered_alarms
                                    if not alarm_id.startswith(f"{alarm_time_str}:")
                                }

                    self.save_tasks()
                    self.update_calendar()

                    drag_context.finish(True, False, time)
                    return

            except (ValueError, KeyError) as e:
                pass

    def on_previous_month(self, widget):
        """Navigate to previous month"""
        current_month = self.month_combo.get_active() + 1
        current_year = self.year_spin.get_value_as_int()

        if current_month == 1:
            new_month = 12
            new_year = current_year - 1
        else:
            new_month = current_month - 1
            new_year = current_year

        self.month_combo.set_active(new_month - 1)
        self.year_spin.set_value(new_year)

        try:
            # FIXED: Update viewing_date, not current_date
            self.viewing_date = self.viewing_date.replace(
                month=new_month, year=new_year
            )
        except ValueError:
            import calendar

            last_day = calendar.monthrange(new_year, new_month)[1]
            self.viewing_date = self.viewing_date.replace(
                month=new_month, year=new_year, day=last_day
            )

        self.update_calendar()

    def on_next_month(self, widget):
        """Navigate to next month"""
        current_month = self.month_combo.get_active() + 1
        current_year = self.year_spin.get_value_as_int()

        if current_month == 12:
            new_month = 1
            new_year = current_year + 1
        else:
            new_month = current_month + 1
            new_year = current_year

        self.month_combo.set_active(new_month - 1)
        self.year_spin.set_value(new_year)

        try:
            # FIXED: Update viewing_date, not current_date
            self.viewing_date = self.viewing_date.replace(
                month=new_month, year=new_year
            )
        except ValueError:
            import calendar

            last_day = calendar.monthrange(new_year, new_month)[1]
            self.viewing_date = self.viewing_date.replace(
                month=new_month, year=new_year, day=last_day
            )

        self.update_calendar()
