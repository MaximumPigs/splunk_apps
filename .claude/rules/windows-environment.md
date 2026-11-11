# Windows environment (the owner develops on Windows)

No `paths` frontmatter: this loads every session.

- **Never write repository files with PowerShell** (`Set-Content`, `Out-File`,
  `Add-Content`, `>` in PowerShell). `Get-Content` reads with the ANSI codepage
  and corrupts UTF-8; PowerShell 5.1 `-Encoding utf8` always writes a BOM. Both
  look fine in the terminal. Use the file tools, or Python with
  `encoding="utf-8"`. The bash guard hook denies these cmdlets.
- The repo is on `D:`, temp folders on `C:`. `os.path.relpath` raises across
  drives; use `splk.paths.display()` for display paths.
- `MAX_PATH`: long paths break `python -m venv` (`ensurepip` fails with
  "Non-UTF-8 code starting with '\x90'") and `git commit -F`. Create venvs and
  commit-message files under `C:\Temp\`.
- Do not pass multi-line messages to `git commit -m` via PowerShell
  here-strings: quotes and parentheses are re-tokenised into pathspecs. Use
  `git commit -F <short path>`.
- `Invoke-WebRequest -SkipCertificateCheck` does not exist in PowerShell 5.1
  (and raw REST to 8089 goes through `splk` anyway).
- `Set-Location` does not always persist between tool calls: use absolute paths
  and `git -C <path>`.
- A fresh shell may need its PATH reloaded:
  `$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`.
- Two AppInspect checks (`check_idx_binary_compatibility`,
  `check_symlink_outside_app`) only run on Linux/macOS and show as warnings
  locally; CI clears them.
- Splunk Web is `http://localhost:8000` (not `splunk.home:8000`); splunkd is
  `localhost:8089`. Never type the owner's password anywhere.
