#!/usr/bin/env python3
"""
flag_tray.py — Country flag in the system tray via ip-api.com
For Raspberry Pi OS Bookworm with Wayfire/wf-panel-pi.
Requires:
    pip install pillow requests
    sudo apt install gir1.2-ayatanaappindicator3-0.1
"""

import io
import os
import sys
import threading

import requests
from PIL import Image

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk, GLib, AyatanaAppIndicator3 as AppIndicator

# ── Configuration ──────────────────────────────────────────────────────────────
DEFAULT_REFRESH_MINUTES = 10
GEO_URL  = "http://ip-api.com/json/?fields=status,country,countryCode"
FLAG_URL = "https://flagcdn.com/w80/{code}.png"
ICON_DIR = os.path.expanduser("~/.local/share/icons")
ICON_NAME = "flag_tray_current"
ICON_PATH = os.path.join(ICON_DIR, ICON_NAME + ".png")
ICON_SIZE = (64, 64)
# ───────────────────────────────────────────────────────────────────────────────


class FlagTray:
    def __init__(self):
        self.refresh_minutes = DEFAULT_REFRESH_MINUTES
        self.country_name    = "Loading..."
        self.country_code    = ""
        self._stop_event     = threading.Event()

        os.makedirs(ICON_DIR, exist_ok=True)

        self.indicator = AppIndicator.Indicator.new(
            "flag-tray",
            "network-wireless",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_icon_theme_path(ICON_DIR)
        self.indicator.set_menu(self._build_menu())

    # ── Menu ───────────────────────────────────────────────────────────────────

    def _build_menu(self):
        self._menu = Gtk.Menu()

        self._status_item = Gtk.MenuItem(label="Loading...")
        self._status_item.set_sensitive(False)
        self._menu.append(self._status_item)

        self._menu.append(Gtk.SeparatorMenuItem())

        refresh_item = Gtk.MenuItem(label="Refresh now")
        refresh_item.connect("activate", self._on_refresh_now)
        self._menu.append(refresh_item)

        interval_item = Gtk.MenuItem(label="Set refresh interval...")
        interval_item.connect("activate", self._on_set_interval)
        self._menu.append(interval_item)

        self._menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._on_quit)
        self._menu.append(quit_item)

        self._menu.show_all()
        return self._menu

    def _update_status_label(self):
        GLib.idle_add(
            self._status_item.set_label,
            "{} — refreshes every {} min".format(
                self.country_name, self.refresh_minutes
            )
        )

    # ── Geo + flag fetching ────────────────────────────────────────────────────

    def fetch_location(self):
        try:
            r = requests.get(GEO_URL, timeout=10)
            data = r.json()
            if data.get("status") == "success":
                return data["country"], data["countryCode"].lower()
            print("[flag_tray] API response: {}".format(data), file=sys.stderr)
        except Exception as e:
            print("[flag_tray] Geo lookup failed: {}".format(e), file=sys.stderr)
        return "Unknown", ""

    def fetch_and_set_flag(self, code):
        try:
            r = requests.get(FLAG_URL.format(code=code), timeout=10)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGBA").resize(ICON_SIZE, Image.LANCZOS)
            img.save(ICON_PATH, "PNG")
            GLib.idle_add(self.indicator.set_icon_full, ICON_NAME, self.country_name)
        except Exception as e:
            print("[flag_tray] Flag download failed: {}".format(e), file=sys.stderr)

    # ── Refresh ────────────────────────────────────────────────────────────────

    def refresh(self):
        country, code = self.fetch_location()
        self.country_name = country
        self.country_code = code
        if code:
            self.fetch_and_set_flag(code)
        self._update_status_label()

    def _refresh_loop(self):
        self.refresh()
        while not self._stop_event.wait(timeout=self.refresh_minutes * 60):
            self.refresh()

    # ── Menu callbacks ─────────────────────────────────────────────────────────

    def _on_refresh_now(self, widget):
        threading.Thread(target=self.refresh, daemon=True).start()

    def _on_set_interval(self, widget):
        dialog = Gtk.Dialog(title="Refresh Interval", flags=Gtk.DialogFlags.MODAL)
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK,     Gtk.ResponseType.OK,
        )
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_keep_above(True)

        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)

        label = Gtk.Label(label="Refresh every how many minutes? (current: {})".format(
            self.refresh_minutes))
        box.pack_start(label, False, False, 0)

        spin = Gtk.SpinButton()
        spin.set_adjustment(Gtk.Adjustment(
            value=self.refresh_minutes,
            lower=1, upper=1440,
            step_increment=1, page_increment=10,
        ))
        spin.set_numeric(True)
        spin.set_activates_default(True)
        box.pack_start(spin, False, False, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.refresh_minutes = int(spin.get_value())
            self._stop_event.set()
            self._stop_event = threading.Event()
            threading.Thread(target=self._refresh_loop, daemon=True).start()
            self._update_status_label()

        dialog.destroy()

    def _on_quit(self, widget):
        self._stop_event.set()
        Gtk.main_quit()

    # ── Run ────────────────────────────────────────────────────────────────────

    def run(self):
        threading.Thread(target=self._refresh_loop, daemon=True).start()
        Gtk.main()


if __name__ == "__main__":
    FlagTray().run()