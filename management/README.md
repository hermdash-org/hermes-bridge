# Hermes Runtime Management Scripts

Simple commands to control your Hermes Runtime installation.

## Mac/Linux

```bash
# Stop Hermes
bash stop.sh

# Start Hermes
bash start.sh

# Restart Hermes
bash restart.sh

# Check status
bash status.sh

# Uninstall completely
bash uninstall.sh
```

## Windows

```cmd
# Stop Hermes
stop.bat

# Start Hermes
start.bat

# Restart Hermes
restart.bat

# Check status
status.bat

# Uninstall completely
uninstall.bat
```

## Installation Location

These scripts are located at:
- **Mac:** `~/Library/Application Support/Hermes/management/`
- **Linux:** `~/.local/share/hermes/management/`
- **Windows:** `%LOCALAPPDATA%\Hermes\management\`

## What Gets Preserved

When you uninstall, your data is preserved at:
- `~/.hermes/` (Mac/Linux)
- `%USERPROFILE%\.hermes` (Windows)

This includes:
- API keys
- Chat history
- Skills
- Automations
- Configuration

To remove data completely, delete the `~/.hermes` folder manually.
