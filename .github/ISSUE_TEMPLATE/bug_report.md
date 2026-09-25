---
name: Bug report
about: Report a reproducible problem
title: "[Bug] One-line summary"
labels: ["bug"]
assignees: ""
---

<!-- This template only accepts reproducible problems. For feature ideas use the feature request template. -->

**What happens**

Expected behavior vs actual behavior, in a couple of sentences.

**Steps to reproduce**

1. Starting state (which page / which command / what data)
2. What you did
3. What you saw

**Environment**

- App version (Settings → About, or the installer filename) and your OS
- How you run it: from source (`python -m uvicorn`) or the packaged exe (which release?)
- Backend log errors if any (lines starting with `[backend-err]` in the terminal, or `%APPDATA%\job-workbench\main.log` for the desktop app)
- For startup problems: the app's error dialog has a "copy diagnostics" button (version / platform / log tail, home paths redacted) — please attach or paste that

**Can you reproduce it in the demo workspace?**

- Yes → it is a product bug; keep the reproduction steps above
- No → it is likely workspace / data specific; describe what is different about your workspace

**Anything else**

Screenshots / related file paths / whether it reproduces every time.
