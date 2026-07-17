# Troubleshooting Sprite Factory Pro

## Windows SmartScreen Appears

The community release is not code-signed, so Windows may show **Windows protected your PC** or **Unknown publisher**.

Only continue when the executable came from the official [Awetspoon/SpriteFactory release page](https://github.com/Awetspoon/SpriteFactory/releases/latest). Choose **More info**, confirm the filename, then choose **Run anyway**.

## The App Does Not Open

1. Move the executable to a normal local folder such as `Downloads` or `Desktop`.
2. Confirm antivirus did not quarantine the file.
3. Try opening it again after Windows finishes extracting or scanning it.
4. Review `%LOCALAPPDATA%\image_engine_app\logs\image_engine_app.log` for the latest startup error.

When reporting a problem, include the app version, Windows version, what you clicked, and the final lines from that log. Do not include private URLs or personal files.

## PowerShell Blocks The Source Launcher

This only affects running from source, not the downloaded release executable.

Use a one-time bypass:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_app.ps1
```

## A Web Page Finds No Files

- Confirm the page opens in your normal browser.
- Try scanning that page by itself before scanning a large list.
- Enable **Include uncertain image links** when useful files do not have normal image extensions in their URLs.
- Some sites render links entirely with JavaScript; Sprite Factory reads the page's returned HTML and may not see those dynamically generated links.
- HTTP 403 or 429 normally means the site blocked or rate-limited automated requests.
- HTTP 500, 502, 503, or 504 means the remote website failed before Sprite Factory could scan it.
- A timeout means the site did not answer in time. Retry later or scan fewer pages.

Successful results remain in Found Files when another page fails. Hover the failure status to see page-level details.

## Saved Library Pages Are Missing

Use **Scan Pages > More > Save to Library** for pasted URLs, or **Find Linked Pages > More > Save Selected to Library** for discovered pages. Pages are grouped beneath their website and duplicate URLs are ignored.

Checking a website row checks all of its child pages. `Scan Checked` scans only checked pages; merely highlighting a row does not include it.

## Background Removal Looks Wrong

Import never removes a background automatically. In **Transparency**, choose Keep Background, Remove White, or Remove Black only when the source actually contains that background.

Animated GIFs can contain frame-to-frame color changes, antialiasing, or transparent disposal behavior. Start with conservative tolerance and edge settings, watch Final playback, and reset the individual control if the result is too aggressive.

## Final Does Not Match What You Expected

- Current is the original imported source.
- Final is the edited result that will be exported.
- Use the reset beside a control to restore only that setting.
- Use **Reset All** to restore the complete detected source baseline.
- Use **Refresh Final** when automatic preview is turned off.

## Batch Export Fails

- Confirm selected queue items still have readable source files.
- Choose one edit source for the run instead of combining conflicting strategies.
- Confirm the output folder exists and is writable.
- Check whether **Keep existing files** is preventing replacement.
- Select failed queue items and run them again after correcting the reported cause.

Batch works on isolated copies, so a failed run does not modify the active Workspace asset.

## Export Produces The Wrong Format Or Size

Open the teal **Export** category in Edit Settings. Confirm the export profile, format, resize percentage, target dimensions, scale method, quality, metadata, and format-specific encoding options. The teal Export button uses those same settings.

## Source Build Shows A Qt Plugin Error

Recreate the virtual environment and install the project again:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e .
```

The packaged release includes the required Qt runtime and does not require this setup.
