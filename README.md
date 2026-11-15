# TermLog

TermLog records terminal sessions in `~/termlog_logs/YYYY-MM-DD/`. Automatic integration is limited to Terminator and only operates while at least one manually started recording remains active. No background service is required.

## Installation

TermLog requires Linux, Bash, Zsh, util-linux (`script` and `flock`), gzip, and standard utilities. The BSD/macOS backend is not supported. Run `./termlog doctor` before installation. The log and state directories must be owned by the current user and inaccessible to group and other users; TermLog does not change the permissions of existing directories.

To make the `termlog` command and integration available in Zsh, first back up your `.zshrc`, then add the `source` line below. Adjust the path if you move the project:

```zsh
cp -p ~/.zshrc ~/.zshrc.termlog-backup-$(date +%Y%m%d%H%M%S)
# Add to the end of ~/.zshrc:
source /home/hernanibento/projects/termlog/termlog.zsh
```

The `source` line defines the `termlog` function in Zsh. You can also invoke the executable directly; no PATH change is required. Restart Terminator, then run `termlog doctor` and `termlog start recon`. With no active recording, a new tab opens without a prompt. While a recording is active, a new Terminator tab asks whether to start its own recording. Type `exit` or press Ctrl+D to leave the recorded shell: a manually started session returns to the previous shell, while an automatically started session closes the tab.

To roll back, remove the `source` line or restore your backup, then open a new shell. Logs are preserved. Do not overwrite later changes you want to keep when restoring an older backup.

## Configuration

Set and export preferences before the `source` line:

```zsh
export TERMLOG_MODE=ask     # ask (default), auto, or off
# export TERMLOG_DIR="$HOME/termlog_logs"
# export TERMLOG_STATE_DIR="$HOME/.local/state/termlog"
# export TERMLOG_ROTATE_DAYS=7
```

`ask` prompts only when another recording is active. `auto` also requires an existing recording; `off` disables automatic integration without affecting `termlog start`. `termlog disable` and `termlog enable` affect the current shell and its descendants, not other tabs. `termlog config` displays effective values. State is shared by user and state directory, so use the same `TERMLOG_STATE_DIR` in every tab. By default, TermLog uses `XDG_RUNTIME_DIR/termlog` if available, otherwise `XDG_STATE_HOME/termlog` (defaulting to `~/.local/state/termlog`).

Terminator sets `TERMINATOR_UUID` for each terminal. The integration compares this identifier to avoid repeated prompts in subshells and after `source ~/.zshrc`. Another terminal emulator launched from a Terminator shell may inherit this variable and be mistaken for Terminator; remove it when launching that emulator if necessary. Environment-based detection is not a security boundary.

## Commands and troubleshooting

Run `termlog help` for the command list. `status` describes the current shell, and `stop` explains how to exit the recorded shell. `list [YYYY-MM-DD]`, `show <path-or-name>`, and `rotate [days]` work with existing logs. Rotation skips active recordings. `.meta` files record the start and known end of a session; a missing `state=ended` can indicate an interruption.

If startup fails, run `termlog doctor` and check that the required commands are available and the log and state directories have restrictive permissions. If automatic startup fails after replacing the initial shell, TermLog attempts to open a usable Zsh without logging.

## Security

Recordings contain terminal output. Standard input is not recorded separately, but commands and secrets displayed by programs can still appear in logs. There is no secure pause: end the recording before sensitive operations. Flushing reduces buffered data but does not guarantee persistence after a power failure. TermLog does not send logs to external services.

Run the isolated automated tests with `python3 -m unittest discover -s tests -v`.

## Terminal display

TermLog v2.1 provides these optional environment settings:

```zsh
export TERMLOG_BANNER_STYLE=detailed  # detailed (default), minimal, or off
export TERMLOG_COLOR=auto             # auto (default), always, or never
export TERMLOG_TAB_TITLE=off          # off (default), or rec
```

The detailed banner shows the session number, sanitized label, start time, mode, log path, and exit instructions after recording starts. The minimal banner uses three lines; `off` suppresses the startup banner. A completion summary displays elapsed time and the log size in bytes. Long lines wrap to the terminal width. Invalid banner styles use the detailed layout; unknown color settings disable color. `NO_COLOR`, when set, disables color even when `TERMLOG_COLOR=always`. Auto color requires a terminal and a non-dumb `TERM`; always forces ANSI color even when redirected. Control characters and non-ASCII bytes in displayed labels and paths are removed; this does not change filenames.

`TERMLOG_TAB_TITLE=rec` is experimental and disabled by default. In a detected Terminator terminal, it sets a generic `[REC] TermLog` title without including the label or path. TermLog does not add prompt hooks, so a theme can overwrite the indicator. There is no reliable way to read the previous title: after a recording TermLog requests the generic title `Terminal`, rather than restoring the original. A terminal or theme may ignore or subsequently replace the title. The indicator may remain after a crash. No Terminator configuration is changed.

To manually validate in an existing integrated Terminator, first open a tab with no active recordings and verify there is no prompt. Run `termlog start test`, then open a new tab and accept the prompt. Check the independent banner and recording, exit both shells, and confirm a new tab opens without a prompt. Repeat with `TERMLOG_BANNER_STYLE=minimal` and `off`, and `TERMLOG_COLOR=never`. To try the optional title, export `TERMLOG_TAB_TITLE=rec` before starting a recording; verify the generic title and reset on exit. Remove those temporary exports or close the test shell to return to the defaults.
