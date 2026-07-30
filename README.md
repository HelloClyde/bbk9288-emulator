# 步步高 BBK 9288 QEMU 模拟器

这是基于 QEMU 11.0 和
[HelloClyde/bbk9288s-qemu](https://github.com/HelloClyde/bbk9288s-qemu)
实现的 BBK 9288 硬件模拟器。9288 和 9288S 使用相同的 Epson S1C33L05
平台，但整机形态并不相同：9288 是 `320 × 240` 横屏、53 键、无触摸屏；
9288S 则是 `160 × 240` 竖屏触摸机。原 9288S/Web 控制台说明保留在
[README-9288S.md](README-9288S.md)。

源码仓库不包含步步高原厂固件、系统文件或 NAND 镜像。运行前请自行准备
有权使用的 9288 V1.5 NAND；Windows 便携发布包也应将这些文件作为独立资产
提供，不写入 Git 历史。

## 已实现

- 新 QEMU machine type：`bbk9288`，保留原 `bbk9288s` 兼容性。
- 320 × 240 LCDC、40 KiB IVRAM 及 1/2/4/8 bpp 调色板渲染。
- 9288 启动扩展窗口 `0x003A0000`，包括固件实测的初始化命令和就绪握手。
- S1C33L05 标准串行接口状态，启动所需的 TDBE 行为。
- Samsung 兼容 256 MiB NAND、2 KiB 页、64 字节 OOB、FTL 和 FAT16。
- NAND 按脏块增量回写，每 250 ms 同步一次；即使模拟器被强制结束，已经完成
  的页编程和块擦除也不会等到正常退出才落盘。
- 从 NAND 中递归定位并加载 `kernel.bin`。
- V1.5 完整文件树：根目录 `kernel.bin`、`mp3`、`系统`，共 260 个文件、
  156,310,685 字节。
- 8 行 × 7 列原机键盘矩阵：`0x00300F46` 行选通、K5/P0 七路列输入、
  K6.4 唤醒和 Timer3 去抖中断。
- 按 V1.5 内核 `0x021994DC` 的矩阵转换表映射数字、字母、翻页、删除、
  确定、功能键和四方向键。
- 16 位 Timer0/1 比较中断、四路 8 位定时器及 HSDMA 单次/连续/块传输。
- S1C33 的 `INT`、`RETD`、`BRK`、`MIRROR` 和 `MAC` 指令。
- VS1003 压缩音频数据通路；Windows 包通过 `ffplay.exe` 直接播放原固件
  从 NAND 读取并送往解码器的声音。
- Web 控制台：noVNC 320 × 240 显示、完整 53 键面板、浏览器音频、
  电源控制和 NAND 文件管理。
- Windows SDL 桌面窗口、可点击的 53 键软键盘及一键启动脚本。

当前固件可进入 V1.5 词典桌面，显示词典、翻译、语法、阅读、作文等应用
图标。已实测软键盘“确定”可关闭系统提示，方向键可移动日历选中框。
NAND 是可写的，并在运行过程中增量保存。

## 直接运行

源码构建完成后运行：

```powershell
.\run-bbk9288.ps1 -Nand .\runtime\nand-user.raw
```

如果使用 Windows 便携发布包，也可以直接双击：

```text
启动BBK9288.cmd
```

源码目录启动方式默认在 `C:\msys64\ucrt64\bin` 查找 SDL2 和构建依赖。
便携包需要包含构建产物 `bbk9288.exe` 及其运行库。

启动后会同时出现 320 × 240 模拟器窗口和“BBK 9288 — 53 键软键盘”。
直接点击软键盘即可操作；电脑键盘上的数字、字母、Enter、Delete、
PageUp/PageDown 和方向键也会走同一套原机矩阵。软键盘的 `Shift` 是锁定键：
先点 `Shift`，再点一个字母或数字即可发送组合键。

启动器会优先使用同目录或 `PATH` 中的 `ffplay.exe` 播放声音，也可通过
`-AudioPlayer <路径>` 指定，或用 `-NoAudio` 禁用。`ffplay` 本身不随源码
仓库分发。

## Web 前端

安装 NAND 文件管理依赖和 Web 依赖：

```powershell
python -m pip install -r .\requirements-bbk9288s.txt
Push-Location .\web
npm ci
Pop-Location
```

启动 9288 Web 控制台：

```powershell
.\run-bbk9288-web.ps1 -Nand .\runtime\nand-user.raw
```

也可以双击 `run-bbk9288-web.cmd`。默认页面为
`http://127.0.0.1:8000/`，启动器会同时输出可供同一局域网手机或电脑访问
的地址。Web 前端包括：

- 320 × 240 横屏 noVNC 显示，支持像素级缩放和全屏。
- 与原机布局一致的 53 键面板；电脑键盘也可直接输入。
- 固件 VS1003 压缩音频流的浏览器播放和音量控制。
- 模拟器启动、重启、连接状态和 USB 供电状态。
- NAND 维护模式、目录浏览、上传、下载、重命名和删除。

端口可按需调整：

```powershell
.\run-bbk9288-web.ps1 `
  -Nand .\runtime\nand-user.raw `
  -HttpPort 8080 `
  -WebSocketPort 6082 `
  -QmpPort 6083
```

WebSocket 和 HTTP 文件管理接口默认没有认证或传输加密，只应在可信局域网
使用。QMP 始终只监听本机。

## 构建

在 MSYS2 UCRT64 环境中：

```bash
mkdir -p _build
cd _build
../configure \
  --target-list=s1c33-softmmu \
  --without-default-features \
  --enable-tcg \
  --enable-vnc \
  --enable-pixman \
  --enable-sdl \
  --disable-sdl-image \
  --disable-werror \
  --disable-docs \
  --disable-tools
ninja qemu-system-s1c33.exe
```

确认机型：

```powershell
.\_build\qemu-system-s1c33.exe -machine help
```

输出中应同时包含 `bbk9288` 和 `bbk9288s`。

## 生成 9288 NAND

`bbk9288s_nand_image.py` 现在允许安装到 FAT 根目录，并可先清空目标。以一份
已格式化的原始 NAND 为模板：

```powershell
python -m pip install -r .\requirements-bbk9288s.txt
python .\scripts\bbk9288s_nand_image.py install `
  .\template-nand.raw `
  C:\path\to\system-tree `
  --output .\runtime\nand-user.raw `
  --flat .\runtime\nand-user.fat.img `
  --target / `
  --replace-target
```

脚本会重新生成 GBK 兼容的 FAT 短文件名，并核验
`/系统/数据/HZK_LIB.BIN`。

## 启动探针

开发时可用短时探针查看 CPU、MMIO 和 LCD：

```powershell
python .\scripts\bbk9288_probe.py `
  --nand .\runtime\nand-user.raw `
  --seconds 8
```

输出帧位于 `_build\bbk9288-probe\probe.pgm`。

## 回归测试

下面的测试会校验 CPU 新指令、V1.5 启动、LCD、键盘硬件路径、NAND 强制退出
恢复及二次启动；测试使用 NAND 副本，不修改传入的原镜像：

```powershell
.\scripts\test-bbk9288.ps1 `
  -Nand .\runtime\nand-user.raw `
  -AudioPlayer <ffplay.exe路径>
```

## 代码结构

- `hw/s1c33/bbk9288s.c`：9288/9288S 板级设备、LCD、NAND、音频、定时器、
  DMA 和输入模型。
- `target/s1c33/`：Epson S1C33 CPU 翻译、指令 helper 和反汇编。
- `scripts/bbk9288s_nand_image.py`：NAND FTL/FAT16 提取、安装与重新打包。
- `scripts/bbk9288-softkeyboard.ps1`：Windows 53 键软键盘。
- `scripts/bbk9288_probe.py`、`scripts/test-bbk9288.py`：短时探针和端到端
  回归测试。
- `web/`、`scripts/bbk9288s_web_server.py`：9288/9288S 双机型 Web
  控制台、QEMU 生命周期、浏览器音频和 NAND 管理 API。

## 资料依据

- 9288 原机 V1.2 使用说明书：规格页给出 320 × 240、53 键、256M Flash，
  外观页确认横屏键盘机且没有触摸层。
- [Epson S1C33L05 Technical Manual](https://www.epson.jp/prod/semicon/pdf/id000446.pdf)：
  CPU、40 KiB IVRAM、LCDC、NAND、串行接口及寄存器定义。
- [BBK 9288S QEMU 参考实现](https://github.com/HelloClyde/bbk9288s-qemu)：
  S1C33 CPU、NAND FTL、定时器、DMA 和 LCDC 的基础模型。

## 当前限制

- USB 和少量未被 9288 V1.5 固件当前路径使用的板级扩展寄存器仍是实验性模型。
- 音频已接通宿主播放，但仍由 `ffplay` 负责 MPEG 解码，不模拟 VS1003 内部
  的音质、模拟输出和所有 SCI 扩展行为。
- 53 键矩阵按 V1.5 内核表实现；个别功能键在不同应用中的用途由固件上下文
  决定，键帽文字采用 V1.2 使用说明书中的通用名称。
- 此项目是非官方逆向工程，与步步高、Epson 或 QEMU 项目没有隶属关系。

## 许可证

模拟器源码沿用 QEMU 的许可证体系；整体按仓库根目录 `LICENSE`、`COPYING`
和各源文件中的许可证声明发布。请勿在 Issue、PR 或提交中上传无权再分发的
原厂固件、NAND 镜像、说明书或安装包。
