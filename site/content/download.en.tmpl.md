# Download

**Latest version: {{VERSION}}** (released {{RELEASE_DATE}})

简体中文：[下载页](download.md)

## Main channel: GitHub Releases

[Download the Windows installer](https://github.com/chenxiang6663635/job-workbench/releases/latest){ .md-button .md-button--primary }

On the release page, download `job-workbench-setup-{{VERSION}}-win64.exe` from the **Assets** section — a Windows x64 installer with wizard-style setup; no Python or Node needed.

> GitHub can be slow or unreachable from some networks. If the release page will not open, or a download keeps breaking, use the backup channel below.

## Backup channel

Leave a message in [Issues](https://github.com/chenxiang6663635/job-workbench/issues) telling us which version you need, or contact the author via the [repository](https://github.com/chenxiang6663635/job-workbench) — we will reply with a working backup download link.

To be precise: backup links are uploaded and maintained manually and may lag behind the official release; please use the main channel whenever GitHub is reachable for you.

## Unsigned installer and SmartScreen

The installer is not code-signed yet. On first run, Windows may show "Windows protected your PC" — the standard prompt for unsigned software: click **More info** → **Run anyway**.

SmartScreen reputation rebuilds per version, so **later releases may prompt again**; the missing signature does not affect auto-update (integrity is checked against the hash in `latest.yml`).

## Verify the download

**Starting with v26.9.0**, each release ships `SHA256SUMS.txt` (SHA256 hashes of the installer and `latest.yml`). After downloading, run this in PowerShell or CMD (substituting the file you actually downloaded):

```bat
certutil -hashfile job-workbench-setup-{{VERSION}}-win64.exe SHA256
```

Compare the output with the hash for the same file in `SHA256SUMS.txt` on the release page: a match means the file is intact and identical to what the publisher uploaded. To be precise, this proves **integrity**; for an unsigned build it is not proof of publisher identity.
