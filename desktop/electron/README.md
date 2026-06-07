# Smart Video Cut Local Studio Electron Shell

This is the P1 desktop-shell scaffold for the local web app.

## Run

```powershell
cd desktop\electron
npm install
npm start
```

The shell starts `py -m smart_video_cut.web_app` from the repository root with `PYTHONPATH=src`, waits for `http://127.0.0.1:8769/api/check`, then opens the local Studio UI.

## Package

```powershell
cd desktop\electron
npm install
npm run package:win
```

The portable Windows build is written under `release\electron`.
