const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const ROOT_DIR = path.resolve(__dirname, "..", "..");
const LOCAL_URL = "http://127.0.0.1:8769";
let serviceProcess = null;

function waitForServer(url, timeoutMs = 20000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      http
        .get(url, (res) => {
          res.resume();
          resolve(true);
        })
        .on("error", () => {
          if (Date.now() - started > timeoutMs) {
            reject(new Error("Local Studio service did not start in time."));
            return;
          }
          setTimeout(check, 600);
        });
    };
    check();
  });
}

function startLocalService() {
  if (serviceProcess) return;
  serviceProcess = spawn("py", ["-m", "smart_video_cut.web_app"], {
    cwd: ROOT_DIR,
    env: {
      ...process.env,
      PYTHONPATH: path.join(ROOT_DIR, "src"),
    },
    windowsHide: true,
    stdio: "ignore",
  });
  serviceProcess.on("exit", () => {
    serviceProcess = null;
  });
}

async function createWindow() {
  startLocalService();
  try {
    await waitForServer(`${LOCAL_URL}/api/check`);
  } catch (error) {
    dialog.showErrorBox("Local Studio failed to start", String(error.message || error));
  }
  const win = new BrowserWindow({
    width: 1360,
    height: 920,
    minWidth: 1100,
    minHeight: 760,
    backgroundColor: "#f6f1e8",
    title: "Smart Video Cut Local Studio",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  await win.loadURL(LOCAL_URL);
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (serviceProcess) {
    serviceProcess.kill();
    serviceProcess = null;
  }
});
