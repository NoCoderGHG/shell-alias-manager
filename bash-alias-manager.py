#!/usr/bin/env python3
# Bash Alias Manager
# GTK3 tool to manage bash aliases in ~/.bashrc
# MIT License — NoCoderGHG

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

import json
import locale
import os
import re
import subprocess
from pathlib import Path

I18N_DIR = Path(__file__).parent / "i18n"
CONFIG_DIR = Path.home() / ".config" / "alias-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"lang": "system"}


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def detect_system_lang():
    try:
        loc = locale.getlocale()[0] or ""
    except Exception:
        loc = ""
    if not loc:
        loc = os.environ.get("LANG", "")
    return "de" if loc.lower().startswith("de") else "en"


def resolve_lang(setting):
    if setting == "system":
        return detect_system_lang()
    return setting


def load_i18n(lang):
    # English is the base; other languages fall back key by key
    en = {}
    en_path = I18N_DIR / "en.json"
    if en_path.exists():
        with open(en_path) as f:
            en = json.load(f)
    if lang == "en":
        return en
    path = I18N_DIR / f"{lang}.json"
    if not path.exists():
        return en
    with open(path) as f:
        strings = json.load(f)
    for k, v in en.items():
        strings.setdefault(k, v)
    return strings


def t(strings, key, **kwargs):
    s = strings.get(key, key)
    for k, v in kwargs.items():
        s = s.replace("{" + k + "}", str(v))
    return s


class AliasDialog(Gtk.Dialog):
    def __init__(self, parent, title, alias, cmd, strings):
        super().__init__(title=title, transient_for=parent, flags=0)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )
        self.set_default_size(400, 150)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_border_width(10)

        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)

        lbl_alias = Gtk.Label(label=t(strings, "lbl_alias"))
        lbl_alias.set_halign(Gtk.Align.END)
        grid.attach(lbl_alias, 0, 0, 1, 1)

        self.alias_entry = Gtk.Entry()
        self.alias_entry.set_text(alias)
        self.alias_entry.set_hexpand(True)
        grid.attach(self.alias_entry, 1, 0, 1, 1)

        lbl_cmd = Gtk.Label(label=t(strings, "lbl_command"))
        lbl_cmd.set_halign(Gtk.Align.END)
        grid.attach(lbl_cmd, 0, 1, 1, 1)

        self.cmd_entry = Gtk.Entry()
        self.cmd_entry.set_text(cmd)
        self.cmd_entry.set_hexpand(True)
        grid.attach(self.cmd_entry, 1, 1, 1, 1)

        box.pack_start(grid, False, False, 0)
        self.show_all()

    def get_values(self):
        return self.alias_entry.get_text().strip(), self.cmd_entry.get_text().strip()


class AliasManager(Gtk.Window):
    def __init__(self):
        self.cfg = load_config()
        self.strings = load_i18n(resolve_lang(self.cfg.get("lang", "system")))

        super().__init__(title=t(self.strings, "app_title"))
        self.set_default_size(800, 500)
        self.set_border_width(10)

        self.bashrc_path = Path.home() / ".bashrc"
        self.aliases = {}
        self.load_aliases()

        self._build_ui()
        self.populate_list()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(vbox)

        # Language selector
        lang_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        lang_label = Gtk.Label(label=t(self.strings, "lbl_language"))
        lang_box.pack_start(lang_label, False, False, 0)
        self.lang_combo = Gtk.ComboBoxText()
        for code, key in [("de", "lang_de"), ("en", "lang_en"), ("system", "lang_system")]:
            self.lang_combo.append(code, t(self.strings, key))
        self.lang_combo.set_active_id(self.cfg.get("lang", "system"))
        self.lang_combo.connect("changed", self._on_lang_changed)
        lang_box.pack_start(self.lang_combo, False, False, 0)
        vbox.pack_start(lang_box, False, False, 0)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        add_btn = Gtk.Button(label=t(self.strings, "btn_new"))
        add_btn.connect("clicked", self.on_add_clicked)
        toolbar.pack_start(add_btn, False, False, 0)

        edit_btn = Gtk.Button(label=t(self.strings, "btn_edit"))
        edit_btn.connect("clicked", self.on_edit_clicked)
        toolbar.pack_start(edit_btn, False, False, 0)

        delete_btn = Gtk.Button(label=t(self.strings, "btn_delete"))
        delete_btn.connect("clicked", self.on_delete_clicked)
        toolbar.pack_start(delete_btn, False, False, 0)

        refresh_btn = Gtk.Button(label=t(self.strings, "btn_reload"))
        refresh_btn.connect("clicked", self.on_refresh_clicked)
        toolbar.pack_start(refresh_btn, False, False, 0)

        vbox.pack_start(toolbar, False, False, 0)

        # Alias list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        self.store = Gtk.ListStore(str, str)
        self.treeview = Gtk.TreeView(model=self.store)
        self.treeview.set_activate_on_single_click(False)

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(t(self.strings, "col_alias"), renderer, text=0)
        column.set_min_width(150)
        self.treeview.append_column(column)

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn(t(self.strings, "col_command"), renderer, text=1)
        column.set_expand(True)
        self.treeview.append_column(column)

        scrolled.add(self.treeview)
        vbox.pack_start(scrolled, True, True, 0)

    def load_aliases(self):
        self.aliases = {}
        if not self.bashrc_path.exists():
            return

        with open(self.bashrc_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Match aliases with valid names (no spaces in alias name)
                match = re.match(r"alias\s+(\S+)='(.+)'", line)
                if not match:
                    match = re.match(r'alias\s+(\S+)="(.+)"', line)
                if match:
                    self.aliases[match.group(1)] = match.group(2)

    def populate_list(self):
        self.store.clear()
        for alias, cmd in sorted(self.aliases.items()):
            self.store.append([alias, cmd])

    def reload_bashrc(self):
        # Source ~/.bashrc in the current shell context
        try:
            subprocess.run(['bash', '-c', f'source {self.bashrc_path}'],
                           shell=False, check=False)
        except Exception:
            pass

    def save_aliases(self):
        if not self.bashrc_path.exists():
            self.bashrc_path.touch()

        with open(self.bashrc_path, 'r') as f:
            lines = f.readlines()

        # Remove all existing alias lines and the managed-by comment
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if re.match(r"alias\s+\S+=['\"]", stripped):
                continue
            if stripped == "# Aliases managed by Alias Manager":
                continue
            new_lines.append(line)

        # Trim trailing blank lines
        while new_lines and new_lines[-1].strip() == "":
            new_lines.pop()

        # Append current aliases as a single block
        new_lines.append("\n# Aliases managed by Alias Manager\n")
        for alias, cmd in sorted(self.aliases.items()):
            new_lines.append(f"alias {alias}='{cmd}'\n")

        with open(self.bashrc_path, 'w') as f:
            f.writelines(new_lines)

        self.reload_bashrc()

    def on_add_clicked(self, button):
        dialog = AliasDialog(self, t(self.strings, "dlg_new_title"), "", "", self.strings)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            alias, cmd = dialog.get_values()
            if alias and cmd:
                self.aliases[alias] = cmd
                self.save_aliases()
                self.populate_list()

        dialog.destroy()

    def on_edit_clicked(self, button):
        selection = self.treeview.get_selection()
        model, treeiter = selection.get_selected()

        if treeiter:
            alias = model[treeiter][0]
            cmd = model[treeiter][1]

            dialog = AliasDialog(self, t(self.strings, "dlg_edit_title"), alias, cmd, self.strings)
            response = dialog.run()

            if response == Gtk.ResponseType.OK:
                new_alias, new_cmd = dialog.get_values()
                if new_alias and new_cmd:
                    if new_alias != alias:
                        del self.aliases[alias]
                    self.aliases[new_alias] = new_cmd
                    self.save_aliases()
                    self.populate_list()

            dialog.destroy()

    def on_delete_clicked(self, button):
        selection = self.treeview.get_selection()
        model, treeiter = selection.get_selected()

        if treeiter:
            alias = model[treeiter][0]
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=t(self.strings, "confirm_delete", alias=alias)
            )
            response = dialog.run()

            if response == Gtk.ResponseType.YES:
                del self.aliases[alias]
                self.save_aliases()
                self.populate_list()

            dialog.destroy()

    def on_refresh_clicked(self, button):
        self.load_aliases()
        self.populate_list()

    def _on_lang_changed(self, combo):
        new_lang = combo.get_active_id()
        if new_lang and new_lang != self.cfg.get("lang"):
            self.cfg["lang"] = new_lang
            save_config(self.cfg)
            new_strings = load_i18n(resolve_lang(new_lang))
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text=t(new_strings, "restart_hint")
            )
            dialog.run()
            dialog.destroy()


if __name__ == "__main__":
    win = AliasManager()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
