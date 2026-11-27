# ContextTrace Chrome Connector

## What it does

- The extension captures visible page text on HTTP(S) pages after the page loads.
- It does not read input values, password fields, textareas, selects, buttons, or editable regions.
- The extension obtains its bearer token from the local Native Messaging host. The token is not typed by the user and is not stored in extension storage.
- The backend stores the browser source and page text through `/browser/source` and `/browser/content`.

## Install (Windows / Chrome)

1. Start ContextTrace backend once. It creates `%USERPROFILE%\\.contexttrace\\browser-token` automatically.
2. Open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and select this `browser/extension` folder.
3. Copy the extension ID shown on the extension card.
4. Open PowerShell in the project root and run:

   ```powershell
   .\browser\setup_chrome.ps1 -ExtensionId YOUR_32_CHARACTER_EXTENSION_ID
   ```

5. Restart Chrome. No bearer token entry is required.

## Backend

Start from the project `src` directory using the existing environment:

```powershell
..\.venv\Scripts\python.exe -m backend
```

The default backend address is `http://127.0.0.1:8765`.

## Remove

Remove the extension from `chrome://extensions`, then remove the registry key:

```powershell
Remove-Item 'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.contexttrace.auth' -Recurse -Force
```

The token file can be deleted separately after stopping the backend if you want to revoke the local credential.
