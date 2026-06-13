#!/usr/bin/env python3
# Bash/Zsh/Ksh/Fish Alias Manager
# GTK3 tool to manage shell aliases across multiple shells
# MIT License — NoCoderGHG

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

import json
import locale
import os
import re
import shutil
import subprocess
from pathlib import Path

I18N_DIR = Path(__file__).parent / "i18n"
CONFIG_DIR = Path.home() / ".config" / "alias-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"

MANAGED_COMMENT = "# Aliases managed by Alias Manager"

# Shell definitions: name, rc file, syntax, supported
SHELLS = {
    "bash": {
        "rc": Path.home() / ".bashrc",
        "syntax": "posix",   # alias name='cmd'
    },
    "zsh": {
        "rc": Path.home() / ".zshrc",
        "syntax": "posix",
    },
    "ksh": {
        "rc": Path.home() / ".kshrc",
        "syntax": "posix",
    },
    "fish": {
        "rc": Path.home() / ".config" / "fish" / "config.fish",
        "syntax": "fish",    # abbr -a name 'cmd'
    },
    "dash": {
        "rc": None,
        "syntax": "none",    # no alias support
    },
}


def get_available_shells():
    # Return all known shells; mark unavailable ones so the UI can grey them out
    # Order: installed first, then unavailable, following /etc/shells order where possible
    listed = []
    try:
        with open("/etc/shells") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                name = Path(line).name
                if name in SHELLS and name not in listed:
                    listed.append(name)
    except FileNotFoundError:
        pass
    # Add any known shells not in /etc/shells
    for name in SHELLS:
        if name not in listed:
            listed.append(name)
    return listed


def is_shell_installed(shell_name):
    return shutil.which(shell_name) is not None


def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"lang": "system", "shell": "bash"}


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


def load_aliases_from_file(shell_name):
    shell = SHELLS.get(shell_name, {})
    syntax = shell.get("syntax")
    rc = shell.get("rc")
    aliases = {}

    if syntax == "none" or rc is None or not rc.exists():
        return aliases

    with open(rc, "r") as f:
        for line in f:
            line = line.strip()
            if syntax == "posix":
                match = re.match(r"alias\s+(\S+)='(.+)'", line)
                if not match:
                    match = re.match(r'alias\s+(\S+)="(.+)"', line)
                if match:
                    aliases[match.group(1)] = match.group(2)
            elif syntax == "fish":
                # abbr -a name 'cmd' or abbr -a name "cmd"
                match = re.match(r"abbr\s+-a\s+(\S+)\s+'(.+)'", line)
                if not match:
                    match = re.match(r'abbr\s+-a\s+(\S+)\s+"(.+)"', line)
                if match:
                    aliases[match.group(1)] = match.group(2)

    return aliases


def save_aliases_to_file(shell_name, aliases):
    shell = SHELLS.get(shell_name, {})
    syntax = shell.get("syntax")
    rc = shell.get("rc")

    if syntax == "none" or rc is None:
        return

    # Create file and parent dirs if needed
    rc.parent.mkdir(parents=True, exist_ok=True)
    if not rc.exists():
        rc.touch()

    with open(rc, "r") as f:
        lines = f.readlines()

    # Remove existing managed aliases and comment
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped == MANAGED_COMMENT:
            continue
        if syntax == "posix" and re.match(r"alias\s+\S+=['\"]", stripped):
            continue
        if syntax == "fish" and re.match(r"abbr\s+-a\s+\S+\s+['\"]", stripped):
            continue
        new_lines.append(line)

    # Trim trailing blank lines
    while new_lines and new_lines[-1].strip() == "":
        new_lines.pop()

    # Append current aliases as a single block
    new_lines.append(f"\n{MANAGED_COMMENT}\n")
    for alias, cmd in sorted(aliases.items()):
        if syntax == "posix":
            new_lines.append(f"alias {alias}='{cmd}'\n")
        elif syntax == "fish":
            new_lines.append(f"abbr -a {alias} '{cmd}'\n")

    with open(rc, "w") as f:
        f.writelines(new_lines)

    # Source the rc file in a subshell (best-effort)
    try:
        subprocess.run(["bash", "-c", f"source {rc}"], check=False)
    except Exception:
        pass


def make_menu_button(items, on_select, min_width=150):
    btn = Gtk.MenuButton()
    btn.set_size_request(min_width, -1)
    lbl = Gtk.Label(label=items[0] if items else "")
    btn.add(lbl)
    menu = Gtk.Menu()

    def build_menu(items, current=None):
        for child in menu.get_children():
            menu.remove(child)
        group = []
        active = current if current in items else (items[0] if items else None)
        for text in items:
            item = Gtk.RadioMenuItem.new_with_label(group, text)
            group = item.get_group()
            if text == active:
                item.set_active(True)
            def _on_activate(i, t=text):
                if i.get_active():
                    lbl.set_text(t)
                    on_select(t)
            item.connect("activate", _on_activate)
            menu.append(item)
        menu.show_all()
        if active:
            lbl.set_text(active)

    build_menu(items)
    btn.set_popup(menu)

    def update(new_items, current=None):
        build_menu(new_items, current)

    return btn, lbl, update


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
        self.available_shells = get_available_shells()
        self.current_shell = self.cfg.get("shell", "bash")
        if self.current_shell not in self.available_shells:
            self.current_shell = self.available_shells[0] if self.available_shells else "bash"

        super().__init__(title=t(self.strings, "app_title"))
        self.set_default_size(800, 500)
        self.set_border_width(10)

        self.aliases = {}
        self._build_ui()
        self.load_and_populate()

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(vbox)

        # Top bar: language + shell selector
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)

        # Language selector
        lang_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        lang_label = Gtk.Label(label=t(self.strings, "lbl_language"))
        lang_box.pack_start(lang_label, False, False, 0)
        _lang_items = [t(self.strings, k) for k in ["lang_de", "lang_en", "lang_system"]]
        _lang_codes = ["de", "en", "system"]
        _lang_current = t(self.strings, {"de": "lang_de", "en": "lang_en", "system": "lang_system"}.get(self.cfg.get("lang", "system"), "lang_system"))
        self.lang_menu_btn, self._lang_lbl, self._lang_update = make_menu_button(
            _lang_items, lambda txt: self._on_lang_selected(txt, _lang_items, _lang_codes), min_width=130
        )
        self._lang_lbl.set_text(_lang_current)
        lang_box.pack_start(self.lang_menu_btn, False, False, 0)
        top_bar.pack_start(lang_box, False, False, 0)

        # Shell selector
        shell_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        shell_label = Gtk.Label(label=t(self.strings, "lbl_shell"))
        shell_box.pack_start(shell_label, False, False, 0)
        self.shell_menu_btn, self._shell_lbl, self._shell_update = make_menu_button(
            self.available_shells, lambda s: self._on_shell_selected(s), min_width=120
        )
        if self.current_shell in self.available_shells:
            self._shell_lbl.set_text(self.current_shell)
        shell_box.pack_start(self.shell_menu_btn, False, False, 0)

        # Hint label for unsupported shells
        self.shell_hint_label = Gtk.Label()
        self.shell_hint_label.get_style_context().add_class("dim-label")
        shell_box.pack_start(self.shell_hint_label, False, False, 0)

        top_bar.pack_start(shell_box, False, False, 0)
        vbox.pack_start(top_bar, False, False, 0)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        self.add_btn = Gtk.Button(label=t(self.strings, "btn_new"))
        self.add_btn.connect("clicked", self.on_add_clicked)
        toolbar.pack_start(self.add_btn, False, False, 0)

        self.edit_btn = Gtk.Button(label=t(self.strings, "btn_edit"))
        self.edit_btn.connect("clicked", self.on_edit_clicked)
        toolbar.pack_start(self.edit_btn, False, False, 0)

        self.delete_btn = Gtk.Button(label=t(self.strings, "btn_delete"))
        self.delete_btn.connect("clicked", self.on_delete_clicked)
        toolbar.pack_start(self.delete_btn, False, False, 0)

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

        self._update_shell_ui()

    def _update_shell_ui(self):
        # Enable/disable editing based on shell support and installation status
        syntax = SHELLS.get(self.current_shell, {}).get("syntax", "none")
        installed = is_shell_installed(self.current_shell)
        supported = syntax != "none" and installed
        self.add_btn.set_sensitive(supported)
        self.edit_btn.set_sensitive(supported)
        self.delete_btn.set_sensitive(supported)

        if self.current_shell == "dash":
            self.shell_hint_label.set_text(t(self.strings, "shell_dash_hint"))
        elif not installed:
            self.shell_hint_label.set_text(t(self.strings, "shell_not_installed_hint"))
        elif not supported:
            self.shell_hint_label.set_text(t(self.strings, "shell_unknown_hint"))
        else:
            self.shell_hint_label.set_text("")

    def load_and_populate(self):
        self.aliases = load_aliases_from_file(self.current_shell)
        self.store.clear()
        for alias, cmd in sorted(self.aliases.items()):
            self.store.append([alias, cmd])

    def on_add_clicked(self, button):
        dialog = AliasDialog(self, t(self.strings, "dlg_new_title"), "", "", self.strings)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            alias, cmd = dialog.get_values()
            if alias and cmd:
                self.aliases[alias] = cmd
                save_aliases_to_file(self.current_shell, self.aliases)
                self.load_and_populate()
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
                    save_aliases_to_file(self.current_shell, self.aliases)
                    self.load_and_populate()
            dialog.destroy()

    def on_delete_clicked(self, button):
        selection = self.treeview.get_selection()
        model, treeiter = selection.get_selected()
        if treeiter:
            alias = model[treeiter][0]
            dialog = Gtk.MessageDialog(
                transient_for=self, flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=t(self.strings, "confirm_delete", alias=alias)
            )
            response = dialog.run()
            if response == Gtk.ResponseType.YES:
                del self.aliases[alias]
                save_aliases_to_file(self.current_shell, self.aliases)
                self.load_and_populate()
            dialog.destroy()

    def on_refresh_clicked(self, button):
        self.load_and_populate()

    def _on_shell_selected(self, shell):
        if shell and shell != self.current_shell:
            self.current_shell = shell
            self.cfg["shell"] = shell
            save_config(self.cfg)
            self._update_shell_ui()
            self.load_and_populate()

    def _on_lang_selected(self, text, items, codes):
        if text in items:
            code = codes[items.index(text)]
            if code != self.cfg.get("lang"):
                self.cfg["lang"] = code
                save_config(self.cfg)
                new_strings = load_i18n(resolve_lang(code))
                dialog = Gtk.MessageDialog(
                    transient_for=self, flags=0,
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
