"""
Comprehensive debug logging system for tray icon and sync issues
"""

import inspect
import json
import logging
import os
import threading
import traceback
from datetime import datetime
from functools import wraps

from gi.repository import GLib


class DebugLogger:
    """Advanced logging system for debugging tray icon and sync issues"""

    def __init__(self, max_log_size_mb=10):
        self.max_log_size_mb = max_log_size_mb

        # Setup main logger
        self.logger = self._setup_logger("calendar_debug")

        # Setup sync-specific logger
        self.sync_logger = self._setup_logger("calendar_sync")

        # Setup tray-specific logger
        self.tray_logger = self._setup_logger("calendar_tray")

        # State tracking
        self.last_tray_update = None
        self.last_sync_check = None
        self.last_badge_count = None
        self.last_logged_badge_count = None
        self.tray_blink_state = None
        self.sync_state = "unknown"
        self.remote_changes_detected = False
        self.unsynced_changes = False

        # Performance tracking
        self.tray_update_times = []
        self.sync_check_times = []

        # Log initialization
        self.logger.info("DebugLogger initialized")

    def _setup_logger(self, name):
        """Setup a logger with console handler only"""
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)

        # Clear existing handlers
        logger.handlers.clear()

        # Console handler only (no file logging)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)

        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s"
        )
        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)

        return logger

    def log_tray_update(self, task_count, method_caller=None, success=True, error=None):
        """Log tray icon badge updates"""
        timestamp = datetime.now()
        thread_info = f"Thread: {threading.current_thread().name}"

        # Only log TRAY_UPDATE when task count changes or it's been a while
        should_log = (
            not hasattr(self, "_last_tray_update_task_count")
            or self._last_tray_update_task_count != task_count
            or not hasattr(self, "_last_tray_update_time")
            or (timestamp - self._last_tray_update_time).total_seconds() > 30
        )

        if should_log:
            self.tray_logger.debug(
                f"TRAY_UPDATE - Tasks: {task_count}, Success: {success}, {thread_info}"
            )
            self._last_tray_update_task_count = task_count
            self._last_tray_update_time = timestamp

        # No logging for method caller - too frequent

        if error:
            self.tray_logger.error(f"TRAY_UPDATE_ERROR - {error}")
            self.tray_logger.debug(f"TRAY_UPDATE_STACK - {traceback.format_exc()}")

        # Track performance
        self.tray_update_times.append(timestamp)
        if len(self.tray_update_times) > 100:  # Keep last 100 updates
            self.tray_update_times.pop(0)

        self.last_tray_update = timestamp
        self.last_badge_count = task_count

        # Log state snapshot
        self._log_tray_state_snapshot()

    def log_sync_state_change(
        self, old_state, new_state, reason=None, remote_changes=None
    ):
        """Log sync state transitions"""
        timestamp = datetime.now()

        self.sync_logger.info(f"SYNC_STATE_CHANGE - {old_state} -> {new_state}")

        if reason:
            self.sync_logger.debug(f"SYNC_STATE_REASON - {reason}")

        if remote_changes is not None:
            self.sync_logger.debug(f"SYNC_REMOTE_CHANGES - {remote_changes}")

        self.sync_state = new_state
        self.remote_changes_detected = (
            remote_changes
            if remote_changes is not None
            else self.remote_changes_detected
        )

        # Track performance
        self.sync_check_times.append(timestamp)
        if len(self.sync_check_times) > 50:  # Keep last 50 checks
            self.sync_check_times.pop(0)

        self.last_sync_check = timestamp

        # Log detailed state
        self._log_sync_state_details()

    def log_tray_blink(self, blink_state, reason=None):
        """Log tray icon blinking state changes"""
        # Only log significant state changes, not every blink
        if reason in ["remote_changes_detected", "blink_stopped"]:
            self.tray_logger.debug(f"TRAY_BLINK - State: {blink_state}")

        self.tray_blink_state = blink_state
        self.last_blink_time = datetime.now()

    def log_unsynced_changes(self, has_changes, reason=None, task_count=None):
        """Log unsynced changes state"""
        self.sync_logger.debug(f"UNSYNCED_CHANGES - Has changes: {has_changes}")

        if reason:
            self.sync_logger.debug(f"UNSYNCED_REASON - {reason}")

        if task_count is not None:
            self.sync_logger.debug(f"UNSYNCED_TASK_COUNT - {task_count}")

        self.unsynced_changes = has_changes

    def log_remote_sync_check(
        self, has_remote_changes, remote_task_count=None, local_task_count=None
    ):
        """Log remote sync check results"""
        self.sync_logger.debug(
            f"REMOTE_SYNC_CHECK - Changes detected: {has_remote_changes}"
        )

        if remote_task_count is not None:
            self.sync_logger.debug(f"REMOTE_TASK_COUNT - {remote_task_count}")

        if local_task_count is not None:
            self.sync_logger.debug(f"LOCAL_TASK_COUNT - {local_task_count}")

        self.remote_changes_detected = has_remote_changes

    def log_pil_availability(self, pil_available, error=None):
        """Log PIL library availability"""
        self.tray_logger.info(f"PIL_AVAILABILITY - Available: {pil_available}")

        if error:
            self.tray_logger.error(f"PIL_ERROR - {error}")

    def log_icon_operations(self, operation, success=True, details=None):
        """Log icon file operations"""
        # Only log icon operations in debug mode and when they're significant
        if self.tray_logger.isEnabledFor(logging.DEBUG):
            # Don't log every set_from_pixbuf operation - too frequent
            if (
                operation != "set_from_pixbuf"
                or not hasattr(self, "_last_icon_log_time")
                or (datetime.now() - self._last_icon_log_time).total_seconds() > 30
            ):
                self.tray_logger.debug(
                    f"ICON_OPERATION - {operation}, Success: {success}"
                )
                self._last_icon_log_time = datetime.now()

        # No logging for icon details - too frequent and not critical

    def log_gtk_operations(self, operation, widget_type=None, success=True, error=None):
        """Log GTK-related operations"""
        self.logger.debug(
            f"GTK_OPERATION - {operation}, Widget: {widget_type}, Success: {success}"
        )

        if error:
            self.logger.error(f"GTK_ERROR - {error}")

    def log_timer_operations(self, timer_type, action, timer_id=None):
        """Log timer start/stop operations"""
        thread_info = f"Thread: {threading.current_thread().name}"
        self.logger.info(
            f"TIMER_{action.upper()} - Type: {timer_type}, ID: {timer_id}, {thread_info}"
        )

    def log_performance_metrics(self):
        """Log performance metrics summary"""
        if self.tray_update_times and self.tray_logger.isEnabledFor(logging.DEBUG):
            avg_tray_interval = self._calculate_average_interval(self.tray_update_times)
            self.tray_logger.debug(
                f"PERFORMANCE_TRAY - Avg update interval: {avg_tray_interval:.2f}s"
            )

        if self.sync_check_times and self.sync_logger.isEnabledFor(logging.DEBUG):
            avg_sync_interval = self._calculate_average_interval(self.sync_check_times)
            self.sync_logger.debug(
                f"PERFORMANCE_SYNC - Avg check interval: {avg_sync_interval:.2f}s"
            )

    def _calculate_average_interval(self, timestamps):
        """Calculate average interval between timestamps"""
        if len(timestamps) < 2:
            return 0

        intervals = []
        for i in range(1, len(timestamps)):
            interval = (timestamps[i] - timestamps[i - 1]).total_seconds()
            intervals.append(interval)

        return sum(intervals) / len(intervals) if intervals else 0

    def _log_tray_state_snapshot(self):
        """Log detailed tray state information"""
        # Only log tray state snapshot in debug mode and when state actually changes
        if self.tray_logger.isEnabledFor(logging.DEBUG):
            state = {
                "last_update": self.last_tray_update.isoformat()
                if self.last_tray_update
                else None,
                "current_badge_count": self.last_badge_count,
                "blink_state": self.tray_blink_state,
                "update_count": len(self.tray_update_times),
            }

            # Only log if badge count changed or it's been a while since last log
            should_log = (
                self.last_logged_badge_count != self.last_badge_count
                or not hasattr(self, "_last_tray_log_time")
                or (datetime.now() - self._last_tray_log_time).total_seconds() > 30
            )

            if should_log:
                self.tray_logger.debug(
                    f"TRAY_STATE_SNAPSHOT - {json.dumps(state, default=str)}"
                )
                self.last_logged_badge_count = self.last_badge_count
                self._last_tray_log_time = datetime.now()

    def _log_sync_state_details(self):
        """Log detailed sync state information"""
        # Only log sync state details in debug mode
        if self.sync_logger.isEnabledFor(logging.DEBUG):
            state = {
                "current_state": self.sync_state,
                "remote_changes": self.remote_changes_detected,
                "unsynced_changes": self.unsynced_changes,
                "last_check": self.last_sync_check.isoformat()
                if self.last_sync_check
                else None,
                "check_count": len(self.sync_check_times),
            }
            self.sync_logger.debug(
                f"SYNC_STATE_DETAILS - {json.dumps(state, default=str)}"
            )

    def log_comprehensive_state(self):
        """Log comprehensive application state"""
        # Only log comprehensive state in debug mode
        if self.logger.isEnabledFor(logging.DEBUG):
            state = {
                "timestamp": datetime.now().isoformat(),
                "tray": {
                    "last_update": self.last_tray_update.isoformat()
                    if self.last_tray_update
                    else None,
                    "badge_count": self.last_badge_count,
                    "blink_state": self.tray_blink_state,
                    "update_count": len(self.tray_update_times),
                },
                "sync": {
                    "state": self.sync_state,
                    "remote_changes": self.remote_changes_detected,
                    "unsynced_changes": self.unsynced_changes,
                    "last_check": self.last_sync_check.isoformat()
                    if self.last_sync_check
                    else None,
                    "check_count": len(self.sync_check_times),
                },
                "threading": {
                    "main_thread": threading.current_thread().name,
                    "active_threads": [t.name for t in threading.enumerate()],
                },
            }
            self.logger.debug("COMPREHENSIVE_STATE_DUMP")
            self.logger.debug(f"STATE_DUMP - {json.dumps(state, default=str)}")

    def log_exception(self, exception, context=None):
        """Log exceptions with context"""
        self.logger.error(f"EXCEPTION - {type(exception).__name__}: {str(exception)}")
        self.logger.error(f"EXCEPTION_CONTEXT - {context}")
        self.logger.error(f"EXCEPTION_TRACEBACK - {traceback.format_exc()}")

    def cleanup_old_logs(self):
        """Clean up old log files if they get too large"""
        # No file logging, so nothing to clean up
        pass


def log_method_call(logger_method):
    """Decorator to log method calls with arguments and return values"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get class instance (first argument for methods)
            instance = args[0] if args else None
            class_name = instance.__class__.__name__ if instance else "Unknown"

            # Log method call
            arg_names = list(inspect.signature(func).parameters.keys())
            arg_values = args[1:]  # Skip self
            arg_dict = dict(zip(arg_names[: len(arg_values)], arg_values))
            arg_dict.update(kwargs)

            logger_method(
                f"METHOD_CALL - {class_name}.{func.__name__} - Args: {arg_dict}"
            )

            try:
                result = func(*args, **kwargs)
                logger_method(
                    f"METHOD_RETURN - {class_name}.{func.__name__} - Result: {result}"
                )
                return result
            except Exception as e:
                logger_method(
                    f"METHOD_ERROR - {class_name}.{func.__name__} - Exception: {e}"
                )
                raise

        return wrapper

    return decorator


# Global debug logger instance
_debug_logger = None


def get_debug_logger():
    """Get or create the global debug logger instance"""
    global _debug_logger
    if _debug_logger is None:
        _debug_logger = DebugLogger()
    return _debug_logger


def setup_global_logging():
    """Setup global logging configuration"""
    return get_debug_logger()
