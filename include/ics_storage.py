"""
ICS/iCalendar storage functionality for CaLAN
Handles conversion between internal task format and VTODO format
"""

import os
import uuid
from datetime import datetime, timezone

from icalendar import Alarm, Calendar, Todo


class ICSStorage:
    def __init__(self, data_dir, debug_logger=None):
        """Initialize ICS storage"""
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.ics_file = os.path.join(self.data_dir, "calendar.ics")
        self.debug_logger = debug_logger

    def _log_info(self, message):
        """Log info message using debug_logger if available, otherwise print"""
        if self.debug_logger and hasattr(self.debug_logger, 'logger'):
            self.debug_logger.logger.info(message)
        else:
            print(message)

    def _log_debug(self, message):
        """Log debug message using debug_logger if available, otherwise print"""
        if self.debug_logger and hasattr(self.debug_logger, 'logger'):
            self.debug_logger.logger.debug(message)
        else:
            print(message)

    def _log_error(self, message):
        """Log error message using debug_logger if available, otherwise print"""
        if self.debug_logger and hasattr(self.debug_logger, 'logger'):
            self.debug_logger.logger.error(message)
        else:
            print(message)

    def _log_warning(self, message):
        """Log warning message using debug_logger if available, otherwise print"""
        if self.debug_logger and hasattr(self.debug_logger, 'logger'):
            self.debug_logger.logger.warning(message)
        else:
            print(message)

    def load_tasks(self):
        """Load tasks from ICS file and convert to internal format"""
        if not os.path.exists(self.ics_file):
            self._log_info(f"ICS file not found: {self.ics_file}")
            return {}

        self._log_info(
            f"ICS file found: {self.ics_file}, size: {os.path.getsize(self.ics_file)} bytes"
        )

        try:
            with open(self.ics_file, "rb") as f:
                file_content = f.read()
                self._log_debug(f"ICS file content length: {len(file_content)} bytes")
                cal = Calendar.from_ical(file_content)
                self._log_debug(f"Calendar components found: {len(list(cal.walk()))}")

            tasks = {}
            task_count = 0

            for component in cal.walk("VTODO"):
                # Skip deleted tasks
                status = component.get("STATUS", "")
                # FIXED: Handle both DELETED and CANCELLED status
                if status in ["DELETED", "CANCELLED"]:
                    self._log_debug(
                        f"Skipping deleted task: {component.get('summary', 'Unknown')}"
                    )
                    continue

                self._log_debug(
                    f"Processing VTODO component: {component.get('summary', 'Unknown')}"
                )

                # Extract task data
                task = self._vtodo_to_task(component)

                # Get date from DTSTART or DUE
                date_obj = component.get("DTSTART") or component.get("DUE")
                self._log_debug(f"Date object found: {date_obj}")
                if date_obj:
                    # Handle both datetime and date objects
                    if hasattr(date_obj.dt, "date"):
                        date_str = date_obj.dt.date().isoformat()
                    else:
                        date_str = date_obj.dt.isoformat()
                    self._log_debug(f"Date string: {date_str}")

                    if date_str not in tasks:
                        tasks[date_str] = []
                    tasks[date_str].append(task)
                    task_count += 1
                    self._log_debug(
                        f"Loaded task: {task.get('description', 'Unknown')} for date {date_str}"
                    )
                else:
                    self._log_warning(
                        f"Task without date: {task.get('description', 'Unknown')}"
                    )
                    self._log_debug(f"Component properties: {list(component.keys())}")

            self._log_info(f"Successfully loaded {task_count} tasks from {self.ics_file}")
            return tasks

        except Exception as e:
            self._log_error(f"Error loading ICS file: {e}")
            return {}

    def save_tasks(self, tasks):
        """Save tasks to ICS file, converting from internal format"""
        try:
            # Create calendar
            cal = Calendar()
            cal.add("prodid", "-//CaLAN//Calendar App//EN")
            cal.add("version", "2.0")
            cal.add("calscale", "GREGORIAN")
            cal.add("method", "PUBLISH")
            cal.add("x-wr-calname", "CaLAN Tasks")
            cal.add("x-wr-caldesc", "Task calendar for CaLAN")

            # Add all tasks as VTODO
            for date_str, task_list in tasks.items():
                for task in task_list:
                    todo = self._task_to_vtodo(task, date_str)
                    cal.add_component(todo)

            # Atomic write: write to temp file first, then rename
            temp_file = self.ics_file + ".tmp"
            backup_file = self.ics_file + ".bak"

            # Write to temporary file
            with open(temp_file, "wb") as f:
                f.write(cal.to_ical())

            # Create backup of original file if it exists
            if os.path.exists(self.ics_file):
                os.replace(self.ics_file, backup_file)

            # Atomically replace the original file
            os.replace(temp_file, self.ics_file)

            # Remove backup file if everything succeeded
            if os.path.exists(backup_file):
                os.remove(backup_file)

            self._log_debug(f"Successfully saved {len(tasks)} task dates to {self.ics_file}")
            return True

        except Exception as e:
            self._log_error(f"Error saving ICS file: {e}")

            # Restore backup if something went wrong
            if os.path.exists(backup_file) and not os.path.exists(self.ics_file):
                try:
                    os.replace(backup_file, self.ics_file)
                    self._log_info("Restored backup file after save failure")
                except Exception as restore_error:
                    self._log_error(f"Failed to restore backup: {restore_error}")

            # Clean up temporary files
            for temp_path in [temp_file, backup_file]:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass

            return False

    def _task_to_vtodo(self, task, date_str):
        """Convert internal task format to VTODO component"""
        todo = Todo()

        # UID - use existing or generate new
        uid = task.get("id", str(uuid.uuid4()))
        todo.add("uid", uid)

        # Summary (description)
        summary = task.get("description", "No description")
        todo.add("summary", summary)

        # Status - FIXED: Use proper status values
        if task.get("status") == "DELETED":
            todo.add("status", "CANCELLED")  # FIXED: Use standard status
        else:
            todo.add("status", "NEEDS-ACTION")

        # Date and time
        date_obj = datetime.fromisoformat(date_str).date()
        time_str = task.get("time", "")

        if time_str and ":" in time_str:
            try:
                hour, minute = map(int, time_str.split(":"))
                dt = datetime.combine(date_obj, datetime.min.time())
                dt = dt.replace(hour=hour, minute=minute)
                
                # FIXED: Use timezone-aware datetime
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                    
                todo.add("dtstart", dt)
                todo.add("due", dt)
            except ValueError:
                todo.add("dtstart", date_obj)
        else:
            todo.add("dtstart", date_obj)

        # Color (custom property)
        color = task.get("color", "#4CAF50")
        todo.add("x-calan-color", color)

        # Profile name (custom property)
        profile_name = task.get("profile_name", "")
        if profile_name:
            todo.add("x-calan-profile", profile_name)

        # Created and modified timestamps - FIXED: Use timezone-aware
        created_at = task.get("created_at")
        if created_at:
            created_dt = datetime.fromisoformat(created_at)
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            todo.add("created", created_dt)
        else:
            todo.add("created", datetime.now(timezone.utc))

        updated_at = task.get("updated_at")
        if updated_at:
            updated_dt = datetime.fromisoformat(updated_at)
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)
            todo.add("last-modified", updated_dt)
        else:
            todo.add("last-modified", datetime.now(timezone.utc))

        # Alarm
        if task.get("alarm") and task.get("alarm_time"):
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", f"Reminder: {summary}")

            # Calculate trigger time - FIXED: Use timezone-aware
            alarm_time = datetime.fromisoformat(task["alarm_time"])
            if alarm_time.tzinfo is None:
                alarm_time = alarm_time.replace(tzinfo=timezone.utc)
            alarm.add("trigger", alarm_time)

            # Acknowledged status (custom property)
            if task.get("acknowledged", False):
                alarm.add("x-calan-acknowledged", "TRUE")
            else:
                alarm.add("x-calan-acknowledged", "FALSE")

            todo.add_component(alarm)

        return todo

    def _vtodo_to_task(self, todo):
        """Convert VTODO component to internal task format"""
        task = {}

        # UID - BUGGFIX: Hantera None-värden korrekt
        uid = todo.get("uid")
        task["id"] = str(uid) if uid is not None else str(uuid.uuid4())

        # Summary -> description
        task["description"] = str(todo.get("summary", "No description"))

        # Status - FIXED: Handle both DELETED and CANCELLED
        status = str(todo.get("status", "NEEDS-ACTION"))
        if status in ["DELETED", "CANCELLED"]:
            task["status"] = "DELETED"

        # Time
        dtstart = todo.get("dtstart")
        if dtstart and hasattr(dtstart.dt, "hour"):
            task["time"] = dtstart.dt.strftime("%H:%M")
        else:
            task["time"] = ""

        # Color
        color = todo.get("x-calan-color")
        if color:
            task["color"] = str(color)
        else:
            task["color"] = "#4CAF50"

        # Profile name
        profile = todo.get("x-calan-profile")
        if profile:
            task["profile_name"] = str(profile)
        else:
            task["profile_name"] = ""

        # Timestamps
        created = todo.get("created")
        if created:
            task["created_at"] = created.dt.isoformat()

        modified = todo.get("last-modified")
        if modified:
            task["updated_at"] = modified.dt.isoformat()
        else:
            task["updated_at"] = datetime.now().isoformat()

        # Alarm
        task["alarm"] = False
        task["alarm_time"] = None
        task["acknowledged"] = False

        for component in todo.walk("VALARM"):
            task["alarm"] = True

            trigger = component.get("trigger")
            if trigger:
                if hasattr(trigger.dt, "isoformat"):
                    task["alarm_time"] = trigger.dt.isoformat()

            acknowledged = component.get("x-calan-acknowledged")
            if acknowledged and str(acknowledged) == "TRUE":
                task["acknowledged"] = True

        return task

    def get_all_tasks_with_metadata(self):
        """Get all tasks including deleted ones with full metadata for sync"""
        if not os.path.exists(self.ics_file):
            return {}

        try:
            with open(self.ics_file, "rb") as f:
                cal = Calendar.from_ical(f.read())

            tasks = {}

            for component in cal.walk("VTODO"):
                # Extract task data INCLUDING deleted tasks
                task = self._vtodo_to_task(component)

                # Get date from DTSTART or DUE
                date_obj = component.get("DTSTART") or component.get("DUE")
                if date_obj:
                    # Handle both datetime and date objects
                    if hasattr(date_obj.dt, "date"):
                        date_str = date_obj.dt.date().isoformat()
                    else:
                        date_str = date_obj.dt.isoformat()

                    if date_str not in tasks:
                        tasks[date_str] = []
                    tasks[date_str].append(task)

            return tasks

        except Exception as e:
            self._log_error(f"Error loading ICS file with metadata: {e}")
            return {}
