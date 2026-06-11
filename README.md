# Shell Alias Manager

GTK3 tool to manage shell aliases across multiple shells.

## Supported shells

- **bash** — `~/.bashrc`
- **zsh** — `~/.zshrc`
- **ksh** — `~/.kshrc`
- **fish** — `~/.config/fish/config.fish` (uses `abbr` syntax)
- **dash** — displayed but not supported (dash has no alias functionality)

Only shells that are both listed in `/etc/shells` and installed on the system are shown.

## Requirements

```bash
sudo apt install python3-gi gir1.2-gtk-3.0
```

## Run

```bash
python3 bash-alias-manager.py
```

## Features

- View, add, edit, and delete aliases per shell
- Correct syntax per shell (posix `alias` vs fish `abbr`)
- Shell selector with automatic detection of available shells
- Saves directly to the shell's RC file under a managed block
- Does not touch other content in the RC file
- i18n: Deutsch / English / System (auto-detect)
- Config: `~/.config/alias-manager/config.json`

## License

MIT — NoCoderGHG
