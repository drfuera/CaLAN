"""
ICS/iCalendar storage functionality for CaLAN
Handles conversion between internal task format and VTODO format
"""

import os
import uuid
from datetime import datetime

from icalendar import Alarm, Calendar, Todo


class ICSStorage:
    def __init__(self, data_dir):
        """Initialize ICS storage"""
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.ics_file = os.path.join(self.data_dir, "calendar.ics")

    def load_tasks(self):
        """Load tasks from ICS file and convert to internal format"""
        if not os.path.exists(self.ics_file):
            print(f"ICS file not found: {self.ics_file}")
            return {}

        print(
            f"ICS file found: {self.ics_file}, size: {os.path.getsize(self.ics_file)} bytes"
        )

        try:
            with open(self.ics_file, "rb") as f:
                file_content = f.read()
                print(f"ICS file content length: {len(file_content)} bytes")
                cal = Calendar.from_ical(file_content)
                print(f"Calendar components found: {len(list(cal.walk()))}")

            tasks = {}
            task_count = 0

            for component in cal.walk("VTODO"):
                # Skip deleted tasks
                status = component.get("STATUS", "")
                if status == "DELETED":
                    print(
                        f"Skipping deleted task: {component.get('summary', 'Unknown')}"
                    )
                    continue

                print(
                    f"Processing VTODO component: {component.get('summary', 'Unknown')}"
                )

                # Extract task data
                task = self._vtodo_to_task(component)

                # Get date from DTSTART or DUE
                date_obj = component.get("DTSTART") or component.get("DUE")
                print(f"Date object found: {date_obj}")
                if date_obj:
                    # Handle both datetime and date objects
                    if hasattr(date_obj.dt, "date"):
                        date_str = date_obj.dt.date().isoformat()
                    else:
                        date_str = date_obj.dt.isoformat()
                    print(f"Date string: {date_str}")

                    if date_str not in tasks:
                        tasks[date_str] = []
                    tasks[date_str].append(task)
                    task_count += 1
                    print(
                        f"Loaded task: {task.get('description', 'Unknown')} for date {date_str}"
                    )
                else:
                    print(
                        f"Warning: Task without date: {task.get('description', 'Unknown')}"
                    )
                    print(f"Component properties: {list(component.keys())}")

            print(f"Successfully loaded {task_count} tasks from {self.ics_file}")
            return tasks

        except Exception as e:
            print(f"Error loading ICS file: {e}")
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

            return True

        except Exception as e:
            print(f"Error saving ICS file: {e}")

            # Restore backup if something went wrong
            if os.path.exists(backup_file) and not os.path.exists(self.ics_file):
                try:
                    os.replace(backup_file, self.ics_file)
                    print("Restored backup file after save failure")
                except Exception as restore_error:
                    print(f"Failed to restore backup: {restore_error}")

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

        # Status
        if task.get("status") == "DELETED":
            todo.add("status", "DELETED")
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

        # Created and modified timestamps
        created_at = task.get("created_at")
        if created_at:
            todo.add("created", datetime.fromisoformat(created_at))
        else:
            todo.add("created", datetime.now())

        updated_at = task.get("updated_at")
        if updated_at:
            todo.add("last-modified", datetime.fromisoformat(updated_at))
        else:
            todo.add("last-modified", datetime.now())

        # Alarm
        if task.get("alarm") and task.get("alarm_time"):
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", f"Reminder: {summary}")

            # Calculate trigger time
            alarm_time = datetime.fromisoformat(task["alarm_time"])
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

        # UID
        task["id"] = str(todo.get("uid", str(uuid.uuid4())))

        # Summary -> description
        task["description"] = str(todo.get("summary", "No description"))

        # Status
        status = str(todo.get("status", "NEEDS-ACTION"))
        if status == "DELETED":
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
            print(f"Error loading ICS file with metadata: {e}")
            return {}
