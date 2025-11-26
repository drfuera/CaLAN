"""
Modern tray icon functionality using proper app indicators
"""

import io
import logging
import os
import sys
from datetime import datetime

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

# Try to import PIL for badge functionality
try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Import debug logger
from include.debug_logger import get_debug_logger


class TrayIcon:
    def create_tray_icon(self):
        """Create system tray icon using modern approach"""
        self.debug_logger = get_debug_logger()
        self.debug_logger.logger.info("Creating modern tray icon")
        self.debug_logger.logger.info(f"Platform: {sys.platform}")

        # Store reference to main app
        self.main_app = self

        # Log icon path for debugging
        if hasattr(self, "icon_path"):
            self.debug_logger.logger.debug(
                f"Icon path: {self.icon_path}, exists: {os.path.exists(self.icon_path)}"
            )
        else:
            self.debug_logger.logger.warning("No icon_path attribute found")

        # First try AppIndicator3 if on Linux
        if sys.platform.startswith("linux"):
            # Force StatusIcon for better badge support
            self.debug_logger.logger.info(
                "Skipping AppIndicator3 to force StatusIcon for badge support"
            )
            # if self._try_app_indicator():
            #     self.debug_logger.logger.info("Using AppIndicator3 for tray")
            #     return
            # else:
            #     self.debug_logger.logger.info("AppIndicator3 failed, trying StatusIcon")

        # Fallback to native GTK StatusIcon
        if self._try_gtk_status_icon():
            self.debug_logger.logger.info("Using Gtk.StatusIcon for tray")
            return
        else:
            self.debug_logger.logger.info("StatusIcon failed, using fallback")

        # Last resort: simple fallback
        self.debug_logger.logger.warning("Using fallback tray implementation")
        self._create_fallback_tray()

    def _try_app_indicator(self):
        """Try to use AppIndicator3 (Linux)"""
        try:
            # Import AppIndicator3
            from gi.repository import AppIndicator3

            # Create app indicator
            self.app_indicator = AppIndicator3.Indicator.new(
                "calendar-app-indicator",
                self._get_icon_name(),
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
            )
            self.app_indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

            # Create and set the menu
            self._create_app_indicator_menu()

            return True

        except ImportError:
            self.debug_logger.logger.info("AppIndicator3 not available")
            return False
        except Exception as e:
            self.debug_logger.log_exception(e, "_try_app_indicator")
            return False

    def _get_icon_name(self):
        """Get the appropriate icon name or path"""
        # First try custom icon path
        if hasattr(self, "icon_path") and os.path.exists(self.icon_path):
            self.debug_logger.logger.debug(f"Using custom icon: {self.icon_path}")
            return self.icon_path

        # Fallback to system icon names
        system_icons = [
            "x-office-calendar",
            "office-calendar",
            "calendar",
            "gtk-preferences",
        ]
        for icon_name in system_icons:
            theme = Gtk.IconTheme.get_default()
            if theme.has_icon(icon_name):
                self.debug_logger.logger.debug(f"Using system icon: {icon_name}")
                return icon_name

        self.debug_logger.logger.warning("No suitable icon found, using fallback")
        return "gtk-missing-image"

    def _create_app_indicator_menu(self):
        """Create menu for AppIndicator3"""
        try:
            menu = Gtk.Menu()

            # Show/Hide item
            show_item = Gtk.MenuItem(label="Show/Hide")
            show_item.connect("activate", self._on_show_hide)
            menu.append(show_item)

            # Separator
            separator = Gtk.SeparatorMenuItem()
            menu.append(separator)

            # Quit item
            quit_item = Gtk.MenuItem(label="Quit")
            quit_item.connect("activate", self._on_quit)
            menu.append(quit_item)

            menu.show_all()
            self.app_indicator.set_menu(menu)

        except Exception as e:
            self.debug_logger.log_exception(e, "_create_app_indicator_menu")

    def _try_gtk_status_icon(self):
        """Try using Gtk.StatusIcon with improved menu handling"""
        try:
            self.tray_icon = Gtk.StatusIcon()

            # Set icon using the same method
            icon_name = self._get_icon_name()

            # Check if it's a file path or icon name
            if os.path.exists(icon_name):
                self.tray_icon.set_from_file(icon_name)
                self.debug_logger.logger.debug(
                    f"StatusIcon: Set from file: {icon_name}"
                )
            else:
                self.tray_icon.set_from_icon_name(icon_name)
                self.debug_logger.logger.debug(
                    f"StatusIcon: Set from icon name: {icon_name}"
                )

            self.tray_icon.set_tooltip_text("CaLAN")
            self.tray_icon.connect("activate", self._on_tray_activate)
            self.tray_icon.set_visible(True)

            # Store menu state for Cinnamon workaround
            self._menu_visible = False

            return True

        except Exception as e:
            self.debug_logger.log_exception(e, "_try_gtk_status_icon")
            return False

    def _create_fallback_tray(self):
        """Create fallback tray implementation"""
        self.debug_logger.logger.info("Using fallback tray - limited functionality")
        # In fallback mode, we'll just rely on the window itself
        # Users can use window controls instead of tray

    def _on_show_hide(self, widget=None):
        """Handle Show/Hide menu item"""
        self.debug_logger.logger.info("Show/Hide from tray menu")
        # Direct window restoration
        if self.main_app.get_property("visible"):
            self.main_app.hide()
        else:
            # Ensure window is fully restored and visible
            self.main_app.deiconify()
            self.main_app.present()
            self.main_app.show_all()
            self.main_app.set_keep_above(True)
            GLib.timeout_add(100, self._reset_keep_above)

    def _reset_keep_above(self):
        """Reset keep_above after a short delay"""
        self.main_app.set_keep_above(False)
        return False

    def _on_quit(self, widget=None):
        """Handle Quit menu item"""
        self.debug_logger.logger.info("Quit from tray menu")
        self.main_app.quit_application()

    def _on_tray_activate(self, icon):
        """Handle tray icon left-click (StatusIcon)"""
        self.debug_logger.logger.info("Tray icon activated")
        self._on_show_hide()

    def _on_tray_popup(self, icon, button, time):
        """Handle tray icon right-click (StatusIcon) - disabled to fix click issues"""
        # Disabled to prevent conflicts with left-click activation
        pass

    def update_tray_icon_badge(self):
        """Update tray icon with task count badge"""
        try:
            # Count today's tasks
            today_str = datetime.now().strftime("%Y-%m-%d")
            task_count = len(self.main_app.tasks.get(today_str, []))

            # Only update if task count has changed
            if (
                hasattr(self, "_last_badge_count")
                and self._last_badge_count == task_count
            ):
                return False  # FIXED: Return False to prevent infinite loop

            self._last_badge_count = task_count

            # Log which tray implementation we're using
            if hasattr(self, "app_indicator"):
                if self.debug_logger.logger.isEnabledFor(logging.INFO):
                    self.debug_logger.logger.info(
                        f"Updating AppIndicator badge with {task_count} tasks"
                    )
            elif hasattr(self, "tray_icon") and self.tray_icon:
                if self.debug_logger.logger.isEnabledFor(logging.INFO):
                    self.debug_logger.logger.info(
                        f"Updating StatusIcon badge with {task_count} tasks"
                    )
            else:
                if self.debug_logger.logger.isEnabledFor(logging.WARNING):
                    self.debug_logger.logger.warning(
                        "No tray implementation found for badge update"
                    )

            # Update based on which tray method we're using
            if hasattr(self, "app_indicator"):
                self._update_app_indicator_badge(task_count)
            elif hasattr(self, "tray_icon") and self.tray_icon:
                self._update_status_icon_badge(task_count)

        except Exception as e:
            self.debug_logger.log_exception(e, "update_tray_icon_badge")

        return False  # FIXED: Always return False when used as idle callback

    def _update_app_indicator_badge(self, task_count):
        """Update AppIndicator badge"""
        try:
            # For AppIndicator, update the menu to show task count
            menu = Gtk.Menu()

            # Task count display (non-clickable)
            if task_count > 0:
                count_label = f"Tasks today: {task_count}"
                count_item = Gtk.MenuItem(label=count_label)
                count_item.set_sensitive(False)
                menu.append(count_item)

                separator1 = Gtk.SeparatorMenuItem()
                menu.append(separator1)

            # Show/Hide
            show_item = Gtk.MenuItem(label="Show/Hide")
            show_item.connect("activate", self._on_show_hide)
            menu.append(show_item)

            separator2 = Gtk.SeparatorMenuItem()
            menu.append(separator2)

            # Quit
            quit_item = Gtk.MenuItem(label="Quit")
            quit_item.connect("activate", self._on_quit)
            menu.append(quit_item)

            menu.show_all()
            self.app_indicator.set_menu(menu)

            # Also update tooltip
            tooltip = (
                f"CaLAN - {task_count} task{'s' if task_count != 1 else ''} today"
                if task_count > 0
                else "CaLAN"
            )
            try:
                self.app_indicator.set_property("title", tooltip)
            except:
                pass

        except Exception as e:
            self.debug_logger.log_exception(e, "_update_app_indicator_badge")

    def _update_status_icon_badge(self, task_count):
        """Update StatusIcon badge"""
        if self.debug_logger.logger.isEnabledFor(logging.INFO):
            self.debug_logger.logger.info(
                f"StatusIcon badge update with {task_count} tasks"
            )

        if not PIL_AVAILABLE:
            if self.debug_logger.logger.isEnabledFor(logging.WARNING):
                self.debug_logger.logger.warning("PIL not available for badge update")
            return

        try:
            # Check if we have a valid icon path
            if not hasattr(self, "icon_path") or not self.icon_path:
                if self.debug_logger.logger.isEnabledFor(logging.WARNING):
                    self.debug_logger.logger.warning(
                        "No icon_path available for badge update"
                    )
                return

            if not os.path.exists(self.icon_path):
                if self.debug_logger.logger.isEnabledFor(logging.WARNING):
                    self.debug_logger.logger.warning(
                        f"Icon path does not exist: {self.icon_path}"
                    )
                return

            if self.debug_logger.logger.isEnabledFor(logging.INFO):
                self.debug_logger.logger.info(
                    f"Updating badge with {task_count} tasks using icon: {self.icon_path}"
                )

            # Load and modify icon with badge
            try:
                img = Image.open(self.icon_path).convert("RGBA")
            except Exception as e:
                self.debug_logger.logger.error(
                    f"Failed to load icon {self.icon_path}: {e}"
                )
                return

            if task_count > 0:
                draw = ImageDraw.Draw(img)
                width, height = img.size

                # Draw badge
                badge_size = max(int(width * 0.65), 32)
                badge_x = width - badge_size - 2
                badge_y = 2

                draw.ellipse(
                    [badge_x, badge_y, badge_x + badge_size, badge_y + badge_size],
                    fill="#f44336",
                    outline="white",
                    width=3,
                )

                # Draw number
                font = self._get_font(int(badge_size * 0.7))
                text = str(min(task_count, 99))

                if font:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]

                    text_x = badge_x + (badge_size - text_width) // 2
                    text_y = badge_y + (badge_size - text_height) // 2 - bbox[1]

                    draw.text((text_x, text_y), text, fill="white", font=font)
                else:
                    # Fallback text drawing
                    text_width = len(text) * 8
                    text_height = 12
                    text_x = badge_x + (badge_size - text_width) // 2
                    text_y = badge_y + (badge_size - text_height) // 2
                    draw.text((text_x, text_y), text, fill="white")

            # Convert to pixbuf and update icon
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)

            loader = GdkPixbuf.PixbufLoader.new_with_type("png")
            loader.write(buffer.read())
            loader.close()

            pixbuf = loader.get_pixbuf()
            self.tray_icon.set_from_pixbuf(pixbuf)

            # Update tooltip
            tooltip = (
                f"CaLAN - {task_count} task{'s' if task_count != 1 else ''} today"
                if task_count > 0
                else "CaLAN"
            )
            self.tray_icon.set_tooltip_text(tooltip)

            if self.debug_logger.logger.isEnabledFor(logging.INFO):
                self.debug_logger.logger.info("Badge update completed successfully")

        except Exception as e:
            self.debug_logger.log_exception(e, "_update_status_icon_badge")

    def _get_font(self, size):
        """Get font for badge text"""
        font_paths = self._discover_font_paths()

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    return ImageFont.truetype(font_path, size)
                except Exception:
                    continue

        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _discover_font_paths(self):
        """Discover available font paths dynamically across different systems"""
        font_paths = []

        # Common font directories across different systems
        font_dirs = [
            # Linux standard directories
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            "~/.local/share/fonts",
            "~/.fonts",
            # macOS font directories
            "/Library/Fonts",
            "/System/Library/Fonts",
            "~/Library/Fonts",
            # Windows font directory (if running under WSL or similar)
            "/mnt/c/Windows/Fonts",
            "/usr/share/windows-fonts",
        ]

        # Common bold font names to look for
        bold_font_patterns = [
            # DejaVu fonts (common on many Linux distros)
            "**/dejavu/DejaVuSans-Bold.ttf",
            "**/DejaVuSans-Bold.ttf",
            # Liberation fonts (common on Fedora, RHEL, etc.)
            "**/liberation/LiberationSans-Bold.ttf",
            "**/LiberationSans-Bold.ttf",
            # FreeFont (common on various distros)
            "**/freefont/FreeSansBold.ttf",
            "**/FreeSansBold.ttf",
            # Ubuntu fonts
            "**/ubuntu/Ubuntu-B.ttf",
            "**/Ubuntu-B.ttf",
            # Noto fonts (modern standard on many systems)
            "**/noto/NotoSans-Bold.ttf",
            "**/NotoSans-Bold.ttf",
            # Arial (common on Windows/macOS and some Linux distros)
            "**/Arial Bold.ttf",
            "**/arialbd.ttf",
            # Helvetica (common on macOS)
            "**/Helvetica Bold.ttf",
            "**/Helvetica-Bold.ttf",
            # Generic sans-serif bold fonts
            "**/*Sans*Bold*.ttf",
            "**/*sans*bold*.ttf",
        ]

        # Expand home directories and check which font directories exist
        existing_font_dirs = []
        for font_dir in font_dirs:
            expanded_dir = os.path.expanduser(font_dir)
            if os.path.exists(expanded_dir) and os.path.isdir(expanded_dir):
                existing_font_dirs.append(expanded_dir)

        # Search for fonts in existing directories
        for font_dir in existing_font_dirs:
            for pattern in bold_font_patterns:
                try:
                    # Use glob to find matching font files
                    import glob

                    search_pattern = os.path.join(font_dir, pattern)
                    matches = glob.glob(search_pattern, recursive=True)

                    for match in matches:
                        if os.path.isfile(match) and match not in font_paths:
                            font_paths.append(match)

                            # Don't log individual fonts to reduce verbosity
                except Exception:
                    continue

        # Log font discovery summary (only in debug mode)
        if hasattr(self, "debug_logger") and self.debug_logger.logger.isEnabledFor(
            logging.DEBUG
        ):
            self.debug_logger.logger.debug(
                f"Found {len(font_paths)} fonts for badge text"
            )

        # If no fonts found, fall back to original hardcoded paths
        if not font_paths:
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
            ]

        # Also try to use system fontconfig if available
        try:
            import subprocess

            result = subprocess.run(
                ["fc-match", "-f", "%{file}", "sans:bold"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and os.path.exists(result.stdout.strip()):
                system_font = result.stdout.strip()
                if system_font not in font_paths:
                    font_paths.insert(0, system_font)  # Prioritize system font
        except Exception:
            pass  # fontconfig not available, continue with other methods

        return font_paths

    def quit_application(self):
        """Clean application quit"""
        self.debug_logger.logger.debug("TrayIcon: Cleaning up")

        # Hide tray icons
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.set_visible(False)

        if hasattr(self, "app_indicator"):
            try:
                from gi.repository import AppIndicator3

                self.app_indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
            except:
                pass
