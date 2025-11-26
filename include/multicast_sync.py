"""
Unicast synchronization with mDNS discovery for CaLAN calendar application
Provides network synchronization between multiple instances with automatic peer discovery
"""

import json
import logging
import socket
import subprocess
import threading
import time
import uuid

import gi

gi.require_version("Gtk", "3.0")
from datetime import datetime

import gi
from gi.repository import GLib, Gtk

gi.require_version("GLib", "2.0")
from gi.repository import GLib

try:
    from zeroconf import ServiceInfo, ServiceListener, Zeroconf

    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False
    ServiceInfo = None
    Zeroconf = None
    ServiceListener = None


class MulticastSync:
    def __init__(self, app):
        """
        Initialize multicast synchronization

        Args:
            app: The main CalendarApp instance
        """
        self.app = app
        self.logger = app.debug_logger.logger
        self.running = False
        self.socket = None
        self.listener_thread = None
        self.tasks_lock = threading.RLock()  # Lock for thread-safe task operations

        # mDNS discovery configuration
        self.service_port = 1900
        self.service_type = "_calan._udp.local."
        self.instance_name = (
            f"{self.app.settings.get('name', 'Unknown')}-{uuid.uuid4().hex[:8]}"
        )

        # Zeroconf
        self.zeroconf = None
        self.service_info = None

        # Peer management
        self.peers = {}  # {instance_id: {"ip": ip, "port": port, "last_seen": timestamp, "name": name}}
        self.peers_lock = threading.RLock()

        # Sync statistics tracking
        self.sync_stats = {"sent": 0, "received": 0, "errors": 0, "error_dates": []}

    def get_tasks_lock(self):
        """Get the tasks lock for thread-safe operations from main thread"""
        return self.tasks_lock

        self._is_user_initiated_sync = False

        # Sync settings
        self.sync_interval = 30  # seconds
        self.last_sync = None

        self.logger.info("MulticastSync initialized")

    def start_listening(self):
        """Start listening for unicast sync messages with mDNS discovery"""
        try:
            # Create UDP socket for unicast communication
            self.socket = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
            )
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Bind to service port
            self.socket.bind(("", self.service_port))

            self.running = True

            # Start listener thread
            self.listener_thread = threading.Thread(
                target=self._listener_loop, daemon=True
            )
            self.listener_thread.start()

            # Start mDNS discovery with zeroconf
            self._start_zeroconf()

            self.logger.info(f"Unicast listener started on port {self.service_port}")
            self.logger.info(f"mDNS discovery started as {self.instance_name}")

            # Start periodic cleanup of stale peers
            def cleanup_timer():
                if self.running:
                    self._cleanup_stale_peers()
                    return True
                return False

            GLib.timeout_add_seconds(120, cleanup_timer)  # Every 2 minutes

        except Exception as e:
            self.logger.error(f"Failed to start unicast listener: {e}")

    def stop_listening(self):
        """Stop listening for unicast sync messages"""
        self.running = False

        # Stop zeroconf
        self._stop_zeroconf()

        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        self.logger.info("Unicast listener stopped")

    def _get_real_ip(self):
        """Get real network IP address (not loopback)"""
        try:
            # First try to get all network interfaces and find a 192.168.x.x address
            import netifaces

            for interface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        ip = addr_info["addr"]
                        if ip.startswith("192.168."):
                            self.logger.debug(f"Found local network IP: {ip}")
                            return ip
        except:
            pass

        try:
            # Fallback: Try to connect to a public DNS to get our real IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                self.logger.debug(f"Detected real IP: {ip}")
                return ip
        except:
            # Final fallback to hostname resolution
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            self.logger.debug(f"Fallback IP from hostname: {ip}")
            return ip

    def _start_zeroconf(self):
        """Start zeroconf service discovery"""
        if not ZEROCONF_AVAILABLE:
            self.logger.warning("zeroconf not available - mDNS discovery disabled")
            return

        try:
            self.zeroconf = Zeroconf()

            # Register our own service with real network IP
            # Get real network IP address (not loopback)
            real_ip = self._get_real_ip()

            self.service_info = ServiceInfo(
                self.service_type,
                f"{self.instance_name}.{self.service_type}",
                addresses=[socket.inet_aton(real_ip)],
                port=self.service_port,
                properties={
                    "name": self.app.settings.get("name", "Unknown"),
                    "instance": self.instance_name,
                },
            )

            self.zeroconf.register_service(self.service_info)

            # Start browsing for other services
            self.zeroconf.add_service_listener(
                self.service_type, CaLANServiceListener(self)
            )

            self.logger.info("Zeroconf service registered and browsing started")

        except Exception as e:
            self.logger.error(f"Failed to start zeroconf: {e}")
            # Cleanup partial state
            if hasattr(self, "zeroconf"):
                try:
                    self.zeroconf.close()
                except:
                    pass
                self.zeroconf = None
                self.service_info = None

    def _stop_zeroconf(self):
        """Stop zeroconf service discovery"""
        if self.zeroconf and self.service_info:
            try:
                self.zeroconf.unregister_service(self.service_info)
                self.zeroconf.close()
            except Exception as e:
                self.logger.error(f"Error stopping zeroconf: {e}")
            finally:
                self.zeroconf = None
                self.service_info = None

    def _handle_service_discovered(self, info):
        """Handle discovered service from zeroconf"""
        try:
            if info.type != self.service_type:
                return

            instance_name = info.name.replace(f".{self.service_type}", "")

            # Skip our own service
            if instance_name == self.instance_name:
                return

            # Get IP address - prefer 192.168.x.x addresses over others
            ip = None
            if info.addresses:
                # First try to find a 192.168.x.x address
                for address in info.addresses:
                    candidate_ip = socket.inet_ntoa(address)
                    if candidate_ip.startswith("192.168."):
                        ip = candidate_ip
                        self.logger.debug(f"Found preferred 192.168.x.x IP: {ip}")
                        break

                # If no 192.168.x.x found, try any non-loopback address
                if ip is None:
                    for address in info.addresses:
                        candidate_ip = socket.inet_ntoa(address)
                        if not candidate_ip.startswith("127."):
                            ip = candidate_ip
                            self.logger.debug(f"Found non-loopback IP: {ip}")
                            break

                # If still no good IP found, use the first address
                if ip is None and info.addresses:
                    ip = socket.inet_ntoa(info.addresses[0])
                    self.logger.debug(f"Using first available IP: {ip}")
            else:
                ip = socket.gethostbyname(info.server)
                self.logger.debug(f"Using hostname-resolved IP: {ip}")

            # If we have a non-192.168.x.x address, try to find a better one
            if ip and not ip.startswith("192.168."):
                try:
                    # Try to resolve the server name to find 192.168.x.x addresses
                    resolved_ips = socket.getaddrinfo(info.server, None)
                    for family, type, proto, canonname, sockaddr in resolved_ips:
                        if family == socket.AF_INET:
                            resolved_ip = sockaddr[0]
                            if resolved_ip.startswith("192.168."):
                                ip = resolved_ip
                                self.logger.debug(
                                    f"Found better 192.168.x.x IP via resolution: {ip}"
                                )
                                break
                except:
                    pass

            port = info.port
            name = info.properties.get(b"name", b"Unknown").decode("utf-8")

            with self.peers_lock:
                self.peers[instance_name] = {
                    "ip": ip,
                    "port": port,
                    "last_seen": datetime.now().isoformat(),
                    "name": name,
                }

            self.logger.info(f"Discovered peer: {name} at {ip}:{port}")

        except Exception as e:
            self.logger.error(f"Error adding service: {e}")

    def _handle_service_removed(self, info):
        """Remove a service from peers"""
        try:
            instance_name = info.name.replace(f".{self.service_type}", "")

            with self.peers_lock:
                if instance_name in self.peers:
                    del self.peers[instance_name]
                    self.logger.info(f"Peer removed: {instance_name}")

        except Exception as e:
            self.logger.error(f"Error removing service: {e}")

    def _cleanup_stale_peers(self):
        """Remove peers that haven't been seen in a while"""
        cutoff_time = datetime.now().timestamp() - 120  # 2 minutes

        with self.peers_lock:
            stale_peers = []
            for instance, peer in self.peers.items():
                try:
                    last_seen = datetime.fromisoformat(peer["last_seen"]).timestamp()
                    if last_seen < cutoff_time:
                        stale_peers.append(instance)
                except:
                    stale_peers.append(instance)

            for instance in stale_peers:
                del self.peers[instance]
                self.logger.info(f"Removed stale peer: {instance}")

    def _listener_loop(self):
        """Main listener loop for unicast messages"""
        self.logger.info("Unicast listener loop started")
        while self.running and self.socket:
            try:
                self.logger.debug("Waiting for incoming unicast message...")
                data, address = self.socket.recvfrom(1024)
                self.logger.debug(f"Received {len(data)} bytes from {address}")
                self._handle_message(data, address)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:  # Only log if we're still supposed to be running
                    self.logger.error(f"Error in unicast listener: {e}")
                break
        self.logger.info("Unicast listener loop stopped")

    def _handle_message(self, data, address):
        """Handle incoming unicast message"""
        try:
            self.logger.info(
                f"Received unicast message from {address}, size: {len(data)} bytes"
            )
            message = json.loads(data.decode("utf-8"))
            message_type = message.get("type")

            self.logger.info(
                f"Message received - Type: {message_type}, From: {address}"
            )
            if message_type == "task_update":
                self.logger.debug(f"Task update details: {message}")

            if message_type == "sync_request":
                self._handle_sync_request(message, address)
            elif message_type == "sync_response":
                self._handle_sync_response(message, address)
            elif message_type == "task_update":
                self._handle_task_update(message, address)
            elif message_type == "test_message":
                self._handle_test_message(message, address)
            elif message_type == "full_sync_request":
                self._handle_full_sync_request(message)
            else:
                self.logger.warning(f"Unknown message type: {message_type}")

        except json.JSONDecodeError:
            self.logger.warning(
                f"Invalid JSON received from {address}, data: {data[:100]}"
            )
        except Exception as e:
            self.logger.error(f"Error handling unicast message: {e}")

    def _handle_sync_request(self, message, address):
        """Handle sync request from another instance"""
        self.logger.info(f"Sync request received from {address}")

        # Send our current tasks as response
        response = {
            "type": "sync_response",
            "sender": self.app.settings.get("name", "Unknown"),
            "timestamp": datetime.now().isoformat(),
            "tasks": self.app.tasks,
        }

        self._send_message(response, address)

    def _handle_sync_response(self, message, address):
        """Handle sync response from another instance"""
        self.logger.info(
            f"Sync response received from {message.get('sender', 'Unknown')}"
        )

        # Merge tasks from other instance (basic conflict resolution)
        remote_tasks = message.get("tasks", {})
        if remote_tasks:
            self._merge_tasks(remote_tasks)

    def _handle_task_update(self, message, address):
        """Handle task update from another instance"""
        task_update = message.get("task", {})
        operation = message.get("operation", "update")

        if task_update:
            self.logger.info(
                f"Task update received from {message.get('sender', 'Unknown')} - Operation: {operation}"
            )
            self.logger.debug(f"Task update content: {task_update}")

            # Track received sync operations (only from other senders)
            sender = message.get("sender")
            if operation == "full_sync" and sender != self.app.settings.get(
                "name", "Unknown"
            ):
                self.sync_stats["received"] = self.sync_stats.get("received", 0) + 1

            # For full_sync operations, use full merge logic
            if operation == "full_sync":
                # Convert single task to the format expected by _full_merge_tasks
                date_str = task_update.get("date")
                if date_str:
                    remote_tasks = {date_str: [task_update]}
                    self._full_merge_tasks(remote_tasks)
            else:
                # Pass the operation to _apply_task_update for normal operations
                self._apply_task_update(task_update, operation)

    def _merge_tasks(self, remote_tasks):
        """Merge tasks from remote instance with local tasks - preserve local changes"""
        try:
            with self.tasks_lock:
                merged = False
                for date_str, remote_task_list in remote_tasks.items():
                    if date_str not in self.app.tasks:
                        # Add new date with all remote tasks
                        self.app.tasks[date_str] = []
                        for remote_task in remote_task_list:
                            # Ensure task has all required fields
                            cleaned_task = self._clean_remote_task(remote_task)
                            self.app.tasks[date_str].append(cleaned_task)
                        merged = True
                    else:
                        # Merge individual tasks for existing date
                        local_tasks = self.app.tasks[date_str]
                        local_task_ids = {
                            task.get("id") for task in local_tasks if task.get("id")
                        }

                        for remote_task in remote_task_list:
                            remote_task_id = remote_task.get("id")
                            if remote_task_id and remote_task_id not in local_task_ids:
                                # Only add tasks that don't exist locally
                                # Ensure task has all required fields
                                cleaned_task = self._clean_remote_task(remote_task)
                                local_tasks.append(cleaned_task)
                                merged = True
                            elif remote_task_id and remote_task_id in local_task_ids:
                                # Task exists locally - only update if remote is newer
                                local_task = next(
                                    (
                                        t
                                        for t in local_tasks
                                        if t.get("id") == remote_task_id
                                    ),
                                    None,
                                )
                                if local_task:
                                    remote_updated = remote_task.get("updated_at")
                                    local_updated = local_task.get("updated_at")

                                    # If remote task is newer, update local task
                                    if remote_updated and local_updated:
                                        try:
                                            remote_time = datetime.fromisoformat(
                                                remote_updated
                                            )
                                            local_time = datetime.fromisoformat(
                                                local_updated
                                            )

                                            # Make both datetimes offset-naive for comparison
                                            if remote_time.tzinfo is not None:
                                                remote_time = remote_time.replace(
                                                    tzinfo=None
                                                )
                                            if local_time.tzinfo is not None:
                                                local_time = local_time.replace(
                                                    tzinfo=None
                                                )

                                            if remote_time > local_time:
                                                # Update local task with remote changes
                                                for key, value in remote_task.items():
                                                    if (
                                                        key != "id"
                                                    ):  # Don't change the ID
                                                        local_task[key] = value
                                                merged = True
                                        except ValueError:
                                            # If timestamp parsing fails, track as error
                                            self.sync_stats["errors"] = (
                                                self.sync_stats.get("errors", 0) + 1
                                            )
                                            self.logger.warning(
                                                f"Failed to parse timestamp for task {remote_task_id}"
                                            )
                                    elif remote_updated and not local_updated:
                                        # If local task has no timestamp, update with remote
                                        for key, value in remote_task.items():
                                            if key != "id":  # Don't change the ID
                                                local_task[key] = value
                                        merged = True

            if merged:
                self.app.save_tasks()

                # Use idle_add to update UI from main thread safely
                def safe_update_ui():
                    try:
                        if self.app.view_mode == "calendar":
                            self.app.update_calendar()
                        elif (
                            self.app.view_mode == "tasks"
                            and self.app.selected_date
                            and self.app.selected_date.isoformat() == date_str
                        ):
                            # If we're in task view for the same date, update the task list
                            self.app._show_task_list()
                        # Update tray badge from main thread
                        self.app.update_tray_icon_badge()
                    except Exception as e:
                        self.logger.error(f"Error updating UI from main thread: {e}")

                GLib.idle_add(safe_update_ui)

        except Exception as e:
            self.logger.error(f"Error in _merge_tasks: {e}")
            self.sync_stats["errors"] = self.sync_stats.get("errors", 0) + 1
            # Add error dates with specific error type
            for date_str in remote_tasks.keys():
                error_date = f"{date_str} (merge error)"
                if error_date not in self.sync_stats["error_dates"]:
                    self.sync_stats["error_dates"].append(error_date)

    def _apply_task_update(self, task_update, operation="update"):
        """Apply a single task update from remote instance"""
        try:
            with self.tasks_lock:
                task_id = task_update.get("id")
                date_str = task_update.get("date")
                # operation is now passed as parameter

                self.logger.debug(
                    f"_apply_task_update called - Operation: {operation}, Task ID: {task_id}, Date: {date_str}"
                )

                if not task_id or not date_str:
                    self.logger.warning(
                        f"Invalid task update - missing ID or date: {task_update}"
                    )
                    return

                if operation == "delete":
                    self.logger.debug(
                        f"DELETE RECEIVED: Task ID: {task_id}, Date: {date_str}"
                    )
                    # Remove task only if it exists
                    if date_str in self.app.tasks:
                        before_count = len(self.app.tasks[date_str])
                        # Check if task exists before trying to delete
                        task_exists = any(
                            task.get("id") == task_id
                            for task in self.app.tasks[date_str]
                        )

                        if task_exists:
                            self.app.tasks[date_str] = [
                                task
                                for task in self.app.tasks[date_str]
                                if task.get("id") != task_id
                            ]
                            after_count = len(self.app.tasks[date_str])
                            self.logger.debug(
                                f"DELETE PROCESSED: Tasks before: {before_count}, after: {after_count}"
                            )

                            # Remove empty date entry
                            if after_count == 0:
                                del self.app.tasks[date_str]

                            self.app.save_tasks()
                            # Use idle_add to update UI from main thread
                            if self.app.view_mode == "calendar":
                                GLib.idle_add(self.app.update_calendar)
                            elif (
                                self.app.view_mode == "tasks"
                                and self.app.selected_date
                                and self.app.selected_date.isoformat() == date_str
                            ):
                                # If we're in task view for the same date, update the task list
                                GLib.idle_add(self.app._show_task_list)
                        else:
                            self.logger.debug(
                                f"DELETE SKIPPED: Task {task_id} not found in date {date_str}"
                            )

                elif operation == "move":
                    # Handle move operation - add to new date and remove from old date
                    old_date_str = task_update.get("old_date")
                    self.logger.debug(
                        f"MOVE OPERATION: Moving task {task_id} from {old_date_str} to {date_str}"
                    )

                    # Add task to new date
                    if date_str not in self.app.tasks:
                        self.app.tasks[date_str] = []

                    # Find existing task or add new one
                    existing_index = None
                    for i, task in enumerate(self.app.tasks[date_str]):
                        if task.get("id") == task_id:
                            existing_index = i
                            break

                    if existing_index is not None:
                        # Update existing task
                        cleaned_task = self._clean_remote_task(task_update)
                        self.app.tasks[date_str][existing_index] = cleaned_task
                    else:
                        # Add new task
                        cleaned_task = self._clean_remote_task(task_update)
                        self.app.tasks[date_str].append(cleaned_task)

                    # Remove task from old date if it exists
                    if old_date_str and old_date_str in self.app.tasks:
                        before_count = len(self.app.tasks[old_date_str])
                        self.app.tasks[old_date_str] = [
                            task
                            for task in self.app.tasks[old_date_str]
                            if task.get("id") != task_id
                        ]
                        after_count = len(self.app.tasks[old_date_str])

                        # Remove empty date entry
                        if after_count == 0:
                            del self.app.tasks[old_date_str]

                        self.logger.debug(
                            f"MOVE PROCESSED: Removed from {old_date_str} - tasks before: {before_count}, after: {after_count}"
                        )

                    self.app.save_tasks()

                else:  # add or update
                    if date_str not in self.app.tasks:
                        self.app.tasks[date_str] = []

                    # Find existing task or add new one
                    existing_index = None
                    for i, task in enumerate(self.app.tasks[date_str]):
                        if task.get("id") == task_id:
                            existing_index = i
                            break

                    if existing_index is not None:
                        # For normal updates, check timestamp to avoid overwriting newer changes
                        if operation == "update":
                            remote_updated = task_update.get("updated_at")
                            local_updated = self.app.tasks[date_str][
                                existing_index
                            ].get("updated_at")

                            if remote_updated and local_updated:
                                try:
                                    remote_time = datetime.fromisoformat(remote_updated)
                                    local_time = datetime.fromisoformat(local_updated)

                                    # Make both datetimes offset-naive for comparison
                                    if remote_time.tzinfo is not None:
                                        remote_time = remote_time.replace(tzinfo=None)
                                    if local_time.tzinfo is not None:
                                        local_time = local_time.replace(tzinfo=None)

                                    if remote_time <= local_time:
                                        # Skip update if remote is not newer
                                        self.logger.debug(
                                            f"Skip update - local task is newer or same: {task_id}"
                                        )
                                        return
                                except ValueError:
                                    # If timestamp parsing fails, proceed with update
                                    pass

                        # Ensure task has all required fields when updating
                        cleaned_task = self._clean_remote_task(task_update)
                        self.app.tasks[date_str][existing_index] = cleaned_task
                    else:
                        # Ensure task has all required fields when adding
                        cleaned_task = self._clean_remote_task(task_update)
                        self.app.tasks[date_str].append(cleaned_task)

                    self.app.save_tasks()

                    # Use idle_add to update UI from main thread safely
                    def safe_update_ui():
                        try:
                            if self.app.view_mode == "calendar":
                                self.app.update_calendar()
                            elif (
                                self.app.view_mode == "tasks"
                                and self.app.selected_date
                                and self.app.selected_date.isoformat() == date_str
                            ):
                                # If we're in task view for the same date, update the task list
                                self.app._show_task_list()
                                self.app._update_task_ui(task_id, date_str)
                            # Update tray badge from main thread
                            self.app.update_tray_icon_badge()
                        except Exception as e:
                            self.logger.error(
                                f"Error updating UI from main thread: {e}"
                            )

                    GLib.idle_add(safe_update_ui)

                # Use idle_add to update UI from main thread safely for move operations
                def safe_update_ui_move():
                    try:
                        if self.app.view_mode == "calendar":
                            self.app.update_calendar()
                        elif (
                            self.app.view_mode == "tasks"
                            and self.app.selected_date
                            and (
                                self.app.selected_date.isoformat() == date_str
                                or self.app.selected_date.isoformat() == old_date_str
                            )
                        ):
                            # If we're in task view for either the old or new date, update the task list
                            self.app._show_task_list()
                        # Update tray badge from main thread
                        self.app.update_tray_icon_badge()
                    except Exception as e:
                        self.logger.error(
                            f"Error updating UI from main thread for move: {e}"
                        )

                GLib.idle_add(safe_update_ui_move)

        except Exception as e:
            self.logger.error(f"Error in _apply_task_update: {e}")
            self.sync_stats["errors"] = self.sync_stats.get("errors", 0) + 1

        except Exception as e:
            self.logger.error(f"Error in _apply_task_update: {e}")
            self.sync_stats["errors"] = self.sync_stats.get("errors", 0) + 1

    def _send_message(self, message, address=None):
        """Send unicast message to all discovered peers"""
        try:
            if not self.socket:
                return

            data = json.dumps(message).encode("utf-8")

            if address:
                # Send to specific address (unicast response)
                self.socket.sendto(data, address)
            else:
                # Send to all discovered peers via unicast
                with self.peers_lock:
                    if not self.peers:
                        self.logger.debug("No peers discovered yet")
                        return

                    sent_count = 0
                    for instance, peer in self.peers.items():
                        try:
                            peer_address = (peer["ip"], peer["port"])
                            self.socket.sendto(data, peer_address)
                            sent_count += 1
                            self.logger.debug(
                                f"Sent to peer {peer['name']} at {peer_address}"
                            )
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to send to peer {peer['name']}: {e}"
                            )

                    self.logger.debug(f"Sent message to {sent_count} peers")

        except Exception as e:
            self.logger.error(f"Error sending unicast message: {e}")

    def manual_sync(self):
        """Trigger manual synchronization with other instances"""
        self.logger.info("Manual sync triggered")

        # Send sync request to all peers
        request = {
            "type": "sync_request",
            "sender": self.app.settings.get("name", "Unknown"),
            "timestamp": datetime.now().isoformat(),
        }

        self._send_message(request)

        # Also immediately send our current tasks as a sync response
        # This ensures other instances get our data even if they don't respond
        response = {
            "type": "sync_response",
            "sender": self.app.settings.get("name", "Unknown"),
            "timestamp": datetime.now().isoformat(),
            "tasks": self.app.tasks,
        }

        self._send_message(response)

        # Re-enable sync button after a delay
        def enable_sync_button():
            if hasattr(self.app, "sync_btn"):
                self.app.sync_btn.set_sensitive(True)

        GLib.timeout_add_seconds(3, enable_sync_button)

    def full_sync(self):
        """Trigger full synchronization by sending each task individually"""
        self.logger.info("Full sync triggered")

        # Reset sync statistics
        self.sync_stats = {"sent": 0, "received": 0, "errors": 0, "error_dates": []}

        # Mark this as user-initiated sync for UI feedback
        self._is_user_initiated_sync = True

        # Get all tasks including metadata from ICS storage
        all_tasks = self.app.ics_storage.get_all_tasks_with_metadata()

        # Send each task individually as a task_update
        task_count = 0
        for date_str, task_list in all_tasks.items():
            for task in task_list:
                # Add date to task for proper handling
                task_with_date = task.copy()
                task_with_date["date"] = date_str

                # Send as individual task update
                self.broadcast_task_update(task_with_date, operation="full_sync")
                task_count += 1

        self.sync_stats["sent"] = task_count
        self.logger.info(
            f"Full sync: sent {task_count} individual tasks to {len(self.peers)} peers"
        )

        # Show sync success feedback with statistics
        self._show_sync_success(f"Full sync: {task_count} tasks sent", self.sync_stats)

    def _handle_full_sync_request(self, message):
        """Handle full sync request - respond with our tasks"""
        self.logger.info(
            f"Received full sync request from {message.get('sender', 'Unknown')}"
        )

        # Get all our tasks and send them back individually
        all_tasks = self.app.ics_storage.get_all_tasks_with_metadata()

        task_count = 0
        for date_str, task_list in all_tasks.items():
            for task in task_list:
                # Add date to task for proper handling
                task_with_date = task.copy()
                task_with_date["date"] = date_str

                # Send as individual task update
                self.broadcast_task_update(task_with_date, operation="full_sync")
                task_count += 1

        self.sync_stats["sent"] = task_count
        self.logger.info(
            f"Responded to full sync with {task_count} tasks to {len(self.peers)} peers"
        )

        # Don't show dialog for responses - only for user-initiated sync
        # Clear the user-initiated flag for responses
        self._is_user_initiated_sync = False

    def _full_merge_tasks(self, remote_tasks):
        """Full merge of tasks from remote instance - complete synchronization"""
        try:
            with self.tasks_lock:
                merged = False
                deleted_count = 0
                updated_count = 0
                added_count = 0

                # Get all local tasks with metadata
                local_tasks = self.app.ics_storage.get_all_tasks_with_metadata()

                # Create a map of all remote tasks by ID for easy lookup
                remote_task_map = {}
                for date_str, remote_task_list in remote_tasks.items():
                    for remote_task in remote_task_list:
                        task_id = remote_task.get("id")
                        if task_id:
                            remote_task_map[task_id] = {
                                "task": remote_task,
                                "date": date_str,
                            }

                # Create a map of all local tasks by ID
                local_task_map = {}
                for date_str, local_task_list in local_tasks.items():
                    for local_task in local_task_list:
                        task_id = local_task.get("id")
                        if task_id:
                            local_task_map[task_id] = {
                                "task": local_task,
                                "date": date_str,
                            }

                # Process all remote tasks
                for task_id, remote_data in remote_task_map.items():
                    remote_task = remote_data["task"]
                    remote_date = remote_data["date"]

                    if task_id in local_task_map:
                        # Task exists locally - check if it's deleted or updated
                        local_data = local_task_map[task_id]
                        local_task = local_data["task"]

                        # Check if remote task is deleted
                        if (
                            remote_task.get("status") == "DELETED"
                            and local_task.get("status") != "DELETED"
                        ):
                            # Mark local task as deleted
                            local_task["status"] = "DELETED"
                            deleted_count += 1
                            merged = True

                        # Check if remote task is newer
                        else:
                            remote_updated = remote_task.get("updated_at")
                            local_updated = local_task.get("updated_at")

                            if remote_updated and local_updated:
                                try:
                                    remote_time = datetime.fromisoformat(remote_updated)
                                    local_time = datetime.fromisoformat(local_updated)

                                    # Make both datetimes offset-naive for comparison
                                    if remote_time.tzinfo is not None:
                                        remote_time = remote_time.replace(tzinfo=None)
                                    if local_time.tzinfo is not None:
                                        local_time = local_time.replace(tzinfo=None)

                                    if remote_time > local_time:
                                        # Update local task with remote changes
                                        for key, value in remote_task.items():
                                            if key != "id":  # Don't change the ID
                                                local_task[key] = value
                                        updated_count += 1
                                        merged = True
                                except ValueError:
                                    # If timestamp parsing fails, skip update
                                    pass

                    else:
                        # Task doesn't exist locally - add it
                        if remote_task.get("status") != "DELETED":
                            if remote_date not in self.app.tasks:
                                self.app.tasks[remote_date] = []

                            # Ensure task has all required fields
                            cleaned_task = self._clean_remote_task(remote_task)
                            self.app.tasks[remote_date].append(cleaned_task)
                            added_count += 1
                            merged = True

                # Also check for tasks that exist locally but not in remote (should remain unchanged)

            if merged:
                self.app.save_tasks()

                # Use idle_add to update UI from main thread safely
                def safe_update_ui():
                    try:
                        if self.app.view_mode == "calendar":
                            self.app.update_calendar()
                        # Update tray badge from main thread
                        self.app.update_tray_icon_badge()
                    except Exception as e:
                        self.logger.error(f"Error updating UI from main thread: {e}")
                    return False

                GLib.idle_add(safe_update_ui)

                self.logger.info(
                    f"Full sync completed: {added_count} added, {updated_count} updated, {deleted_count} marked as deleted"
                )

                # Show sync success feedback only if this is user-initiated sync
                if (
                    hasattr(self, "_is_user_initiated_sync")
                    and self._is_user_initiated_sync
                ):
                    self._show_sync_success(
                        f"Full sync: +{added_count} ↑{updated_count} -{deleted_count}"
                    )

        except Exception as e:
            self.logger.error(f"Error in full sync merge: {e}")
            self.sync_stats["errors"] = self.sync_stats.get("errors", 0) + 1
            # Add error dates from the remote tasks
            for date_str in remote_tasks.keys():
                error_date = f"{date_str} (full sync error)"
                if error_date not in self.sync_stats["error_dates"]:
                    self.sync_stats["error_dates"].append(error_date)

    def _optimize_task_data(self, tasks):
        """Optimize task data to reduce message size for multicast"""
        optimized = {}
        for date_str, task_list in tasks.items():
            optimized_tasks = []
            for task in task_list:
                # Only include essential fields for sync
                optimized_task = {
                    "id": task.get("id"),
                    "description": task.get("description", ""),
                    "status": task.get("status", "NEEDS-ACTION"),
                    "time": task.get("time", ""),
                    "color": task.get("color", "#4CAF50"),
                    "profile_name": task.get("profile_name", ""),
                    "created_at": task.get("created_at"),
                    "updated_at": task.get("updated_at"),
                    "alarm": task.get("alarm", False),
                    "alarm_time": task.get("alarm_time"),
                    "acknowledged": task.get("acknowledged", False),
                }
                # Remove None values to save space
                optimized_task = {
                    k: v for k, v in optimized_task.items() if v is not None
                }
                optimized_tasks.append(optimized_task)

            if optimized_tasks:  # Only include dates that have tasks
                optimized[date_str] = optimized_tasks

        return optimized

    def _show_sync_success(self, message, sync_stats=None):
        """Show sync feedback with detailed status and close button"""
        try:
            # Create a custom dialog with detailed information
            dialog = Gtk.Dialog(
                title="Sync Status",
                transient_for=self.app,
                flags=0,
                modal=True,
            )
            dialog.set_default_size(300, 200)
            dialog.set_resizable(False)

            # Add close button
            dialog.add_button("Close", Gtk.ResponseType.CLOSE)
            dialog.set_default_response(Gtk.ResponseType.CLOSE)

            # Create content area
            content_area = dialog.get_content_area()
            content_area.set_spacing(12)
            content_area.set_margin_top(12)
            content_area.set_margin_bottom(12)
            content_area.set_margin_start(12)
            content_area.set_margin_end(12)

            # Main message label (centered)
            main_label = Gtk.Label(label=message)
            main_label.set_justify(Gtk.Justification.CENTER)
            main_label.set_line_wrap(True)
            main_label.set_max_width_chars(40)
            content_area.pack_start(main_label, False, False, 0)

            # Add separator
            separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            content_area.pack_start(separator, False, False, 6)

            # Add detailed statistics if available
            if sync_stats:
                stats_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

                sent_label = Gtk.Label(
                    label=f"📤 Sent: {sync_stats.get('sent', 0)} tasks"
                )
                sent_label.set_halign(Gtk.Align.START)
                stats_box.pack_start(sent_label, False, False, 0)

                errors = sync_stats.get("errors", 0)
                if errors > 0:
                    error_label = Gtk.Label(label=f"❌ Errors: {errors}")
                    error_label.set_halign(Gtk.Align.START)
                    stats_box.pack_start(error_label, False, False, 0)
                else:
                    success_label = Gtk.Label(label="✅ No errors")
                    success_label.set_halign(Gtk.Align.START)
                    stats_box.pack_start(success_label, False, False, 0)

                if sync_stats.get("error_dates"):
                    error_dates_label = Gtk.Label()
                    error_dates_text = "<b>Error details:</b>\n" + "\n".join(
                        sync_stats.get("error_dates", [])
                    )
                    error_dates_label.set_markup(error_dates_text)
                    error_dates_label.set_halign(Gtk.Align.START)
                    error_dates_label.set_line_wrap(True)
                    error_dates_label.set_max_width_chars(35)
                    stats_box.pack_start(error_dates_label, False, False, 6)

                content_area.pack_start(stats_box, False, False, 0)

            # Show all and run dialog
            dialog.show_all()

            # Connect response to close
            def on_response(dialog, response_id):
                dialog.destroy()

            dialog.connect("response", on_response)

        except Exception as e:
            self.logger.warning(f"Could not show sync dialog: {e}")

    def broadcast_task_update(self, task, operation="update"):
        """Broadcast task update to all discovered peers"""
        # Ensure task has date field for proper handling
        broadcast_task = task.copy()
        if "date" not in broadcast_task:
            # Try to extract date from task context if available
            if hasattr(self.app, "selected_date") and self.app.selected_date:
                broadcast_task["date"] = self.app.selected_date.isoformat()

        message = {
            "type": "task_update",
            "sender": self.app.settings.get("name", "Unknown"),
            "timestamp": datetime.now().isoformat(),
            "task": broadcast_task,
            "operation": operation,
        }

        self.logger.debug(f"Sending task update to peers: {message}")
        self._send_message(message)
        self.logger.info(
            f"Sent task {operation} to {len(self.peers)} peers: {broadcast_task.get('description', 'Unknown')}"
        )

    def _log_delete_operation(self, task, operation):
        """Debug logging for delete operations"""
        self.logger.debug(
            f"DELETE OPERATION: {operation} - Task ID: {task.get('id', 'unknown')}, "
            f"Date: {task.get('date', 'unknown')}, Description: {task.get('description', 'Unknown')}"
        )

    def _clean_remote_task(self, task):
        """Ensure remote task has all required fields"""
        cleaned_task = task.copy()

        # Ensure required fields exist
        if "id" not in cleaned_task:
            import uuid

            cleaned_task["id"] = str(uuid.uuid4())

        if "description" not in cleaned_task:
            cleaned_task["description"] = "No description"

        if "color" not in cleaned_task:
            cleaned_task["color"] = "#4CAF50"

        if "profile_name" not in cleaned_task:
            cleaned_task["profile_name"] = "Unknown"

        if "created_at" not in cleaned_task:
            from datetime import datetime

            cleaned_task["created_at"] = datetime.now().isoformat()

        if "updated_at" not in cleaned_task:
            from datetime import datetime

            cleaned_task["updated_at"] = datetime.now().isoformat()

        # Ensure alarm fields exist
        if "alarm" not in cleaned_task:
            cleaned_task["alarm"] = False

        if "alarm_time" not in cleaned_task:
            cleaned_task["alarm_time"] = None

        if "acknowledged" not in cleaned_task:
            cleaned_task["acknowledged"] = False

        return cleaned_task

    def test_mdns_discovery(self):
        """Test mDNS discovery and peer connectivity"""
        self.logger.info("Testing mDNS discovery...")

        # Show current peers
        with self.peers_lock:
            peer_count = len(self.peers)
            if peer_count > 0:
                self.logger.info(f"Discovered {peer_count} peers:")
                for instance, peer in self.peers.items():
                    self.logger.info(
                        f"  - {peer['name']} at {peer['ip']}:{peer['port']}"
                    )
            else:
                self.logger.info(
                    "No peers discovered yet - discovery may take a few seconds"
                )

        # Send test message to all peers
        test_message = {
            "type": "test_message",
            "sender": self.app.settings.get("name", "Unknown"),
            "timestamp": datetime.now().isoformat(),
            "message": "mDNS connectivity test",
        }

        self._send_message(test_message)
        self.logger.info("mDNS discovery test completed")


class CaLANServiceListener:
    """Zeroconf service listener for CaLAN discovery"""

    def __init__(self, multicast_sync):
        self.multicast_sync = multicast_sync
        self.logger = multicast_sync.logger

    def add_service(self, zeroconf, type, name):
        """Called when a service is discovered"""
        try:
            info = zeroconf.get_service_info(type, name)
            if info:
                self.multicast_sync._handle_service_discovered(info)
        except Exception as e:
            self.logger.error(f"Error in add_service: {e}")

    def remove_service(self, zeroconf, type, name):
        """Called when a service is removed"""
        try:
            info = zeroconf.get_service_info(type, name)
            if info:
                self.multicast_sync._handle_service_removed(info)
        except Exception as e:
            self.logger.error(f"Error in remove_service: {e}")

    def update_service(self, zeroconf, type, name):
        """Called when a service is updated"""
        try:
            info = zeroconf.get_service_info(type, name)
            if info:
                self.multicast_sync._handle_service_discovered(
                    info
                )  # Update with new info
        except Exception as e:
            self.logger.error(f"Error in update_service: {e}")
