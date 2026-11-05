# Keypad Studio 1.5.0

6 键小键盘控制台，适用于 `VID 5A5A / PID 2023`、`Single6VerticalAdvanced` 固件 1.002。

按键动作由电脑端执行，键盘只负责上报“第几个键被按下”。因此不需要刷写固件，就可以随时扩展新的动作类型。

公开仓库：<https://github.com/Delture/keypad-studio>（由 GitHub Actions 自动构建并发布）

## 功能

- 设备中枢主页：四张大卡片显示小键盘、M75 键盘、G04 鼠标、彩虹 2 SE 手柄的连接与电量状态，点击卡片进入对应控制页
- 6 个按键独立配置，支持双击动作
- 动作类型：组合键、文本（中文/Unicode）、打开程序/文件/文件夹/网址、运行 PowerShell/CMD、宏序列、多媒体、应用音量、鼠标、系统功能、剪贴板、窗口、图层、配置
- 应用音量：切换音量合成器中指定程序的静音/100%，不影响系统音量（默认 1 号键用于 CS2）
- 网络切换：Tailscale 连接 + TUN 关闭 ↔ Tailscale 断开 + TUN 开启（两种状态都保持 Clash Party 系统代理开启，默认 6 号键）
- 配置和图层，可随前台程序自动切换
- 外设中心：新盟 M75 键盘电量；AUSDOM G04 Ultra 鼠标电量、回报率、DPI 档位、LOD/去抖/轨迹同步/直线修正/波纹控制/省电/休眠；彩虹 2 SE 手柄实时输入、震动与 XInput 电量状态（全部直连接收器，无需官方驱动）
- 系统托盘常驻、开机自启动
- 内置自动更新：启动时检查 GitHub Releases，可在设置里下载并一键重启安装
- 配置导入/导出
- 设备状态、固件版本、原始 HID 日志

## 下载

在 [Releases](https://github.com/Delture/keypad-studio/releases/latest) 页面下载 `KeypadStudio-win64.zip`，解压到任意可写目录后运行 `KeypadStudio.exe`。不要只把 exe 单独拷出来，`_internal` 目录需要和它放在一起。

## 运行

直接运行 `KeypadStudio.exe`。首次使用如果看到“初始化 6 个按键”，点击一次即可。

- 键 01 在最左侧，键 06 在最右侧（靠近线缆）。
- 默认 1 号键：CS2 音量切换（音量合成器中未静音时静音，已静音时恢复到 100%）。CS2 未运行时按 1 号键会提示找不到音频会话。
- 默认 6 号键：网络组合切换。当前为「Tailscale 已连接 + TUN 关闭 + 系统代理开启」时，切换为「Tailscale 断开 + TUN 开启 + 系统代理开启」；其他状态则恢复前者。切换时先断开/后连接 Tailscale，避免与 TUN 网卡重叠；TUN 切换失败会自动恢复 Tailscale。
- 关闭窗口默认最小化到托盘；请在托盘菜单里退出，以停止按键监听。
- 按键动作依赖本应用在后台运行。

## 外设中心

主页的设备卡片通过外设自己的接收器或 XInput 读取状态，不依赖厂商软件。点击卡片进入对应控制页：

- 新盟 M75：电量。键盘休眠时不会响应读取，请先按一下任意键唤醒，再点「重新读取」。
- AUSDOM G04 Ultra：电量、回报率、DPI 档位与当前档位数值，以及静默高度、按键去抖、轨迹同步、直线修正、波纹控制、传感器省电、休眠时间。所有设置都会立即写入鼠标并回读校验，保存在接收器中。
- BIGBIG WON Rainbow 2 SE：通过 XInput 实时显示按键、摇杆、扳机与数据包，支持轻震/强震测试。2.4G 接收器由 USB 供电，XInput 只报告「有线供电」，不提供手柄电池百分比；这是 XInput 的限制，不是手柄故障。

小键盘卡片显示连接状态、固件版本、当前配置与图层，点击后进入按键布局页；按键页底部的「设备诊断」可以查看 HID 日志、重新初始化或校准按键。

### 关于厂商私有协议

本项目直接实现了各外设的 HID/XInput 通信，但不修改固件：

- 鼠标的回报率、DPI 与传感器设置来自对 AUSDOM 官方驱动协议的解析，写入后会回读确认。
- 键盘目前只读取电量；按键重映射、灯效和宏仍需要厂商私有协议，官方 M75 驱动使用另一套帧格式，尚未接入。
- 手柄通过 Windows XInput 提供实时输入、震动与粗粒度电量；按键重映射、体感、宏、灯效与固件升级依赖 BIGBIG WON 的私有协议，尚未接入。
- 固件升级不包含在本应用中，避免误刷导致设备无法使用。

## 软件更新

打包版会在启动时检查 GitHub Releases（可在「设置 → 软件更新」里关闭）。发现新版本后：

1. 设置页点「下载并安装」，安装包会下载到 `%TEMP%` 并在后台解压；
2. 点「重启并安装」，应用会关闭，一个小批处理等待进程退出后用 Robocopy 覆盖安装目录；
3. 完成后自动重新启动 Keypad Studio。

更新只替换程序文件，`%APPDATA%\KeypadStudio` 里的配置和日志不受影响。源码运行（`python app.py`）只能检查版本，不会自动覆盖源码。

## 数据位置

- 配置：`%APPDATA%\KeypadStudio\config.json`
- 日志：`%APPDATA%\KeypadStudio\app.log`

设置页可以直接打开数据目录，也可以导出/导入配置。

## 网络切换前置设置

6 号键的网络切换依赖 Clash Party 的两个全局快捷键：

- 打开/关闭 TUN：`Ctrl+Shift+Alt+F9`
- 打开/关闭系统代理：`Ctrl+Shift+Alt+F10`

本机已经写入 Clash Party 配置并重启生效。如果以后重装/重置 Clash Party，需要在它的「设置 → 快捷键」里重新设置这两个组合，或在 `%APPDATA%\mihomo-party\config.yaml` 中添加：

```yaml
triggerSysProxyShortcut: "Ctrl+Shift+Alt+F10"
triggerTunShortcut: "Ctrl+Shift+Alt+F9"
```

Clash Party 需要具备管理员权限才能切换 TUN；本机当前已满足。

## 恢复原厂软件

直接运行 MyKey 5.57，重新下载按键配置即可覆盖。本应用只写按键配置，不修改固件。

## 从源码运行

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

## 构建

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller==6.22.3
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed `
  --name KeypadStudio --icon assets/icon.ico `
  --add-data "web;web" --add-data "assets;assets" `
  --collect-all webview --collect-all pythonnet --collect-all clr_loader --collect-all hid `
  --collect-all pycaw --collect-all comtypes --collect-all psutil `
  --hidden-import webview.platforms.edgechromium app.py
```

产物位于 `dist\KeypadStudio`。

GitHub Actions（`.github/workflows/build.yml`）在每次推送到 `main` 时构建，并上传 `KeypadStudio-win64.zip` 工件；推送 `v*` 标签时会校验 `backend/constants.py` 里的版本号，然后自动创建 Release 并附上安装包。

```powershell
git tag v1.5.0
git push origin v1.5.0
```

图标由 `scripts/make_icon.py` 生成（需要 Pillow）。

## 第三方组件

- Tabler Icons（MIT）
- HIDAPI（BSD）
- pywebview（BSD）
- pythonnet（MIT）
- pystray（LGPL-3.0）
- Pillow（HPND）
- PyInstaller（GPL with exception）
