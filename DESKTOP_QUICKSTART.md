# Swim Studio · 打开即用 / Ready to run

**无需安装 Python、Git 或下载模型。运行环境、CoTracker3 和权重已内置。**

## macOS 15 或更新版本（Apple Silicon）

解压后将 **Swim Studio.app** 拖入“应用程序”，双击打开。启动窗口会打开本机浏览器中的分析界面。保留启动窗口，分析结束后点击“退出程序”。此构建针对 Apple Silicon（M1/M2/M3/M4 等），不适用于 Intel Mac。

## Windows（64 位）

完整解压文件夹，再双击 **Swim Studio.exe**。请保留同目录下的 `_internal` 文件夹。Windows 包内置 CPU 版模型，不需要显卡驱动。不要从压缩包预览窗口直接运行。

## 分析步骤

1. 导入单动物视频。
2. 选择容器，点选轮廓或四角，填写实际尺寸。
3. 在首帧头部/眼睛选择 4–6 个点。
4. 人工标记直接刺激接触的起止时间；无接触则勾选确认。
5. 开始分析，检查轨迹，下载结果。点击“操作示意”查看图解；右上角切换语言。

模型在本机运行，首次使用也可离线。视频数据不发送到外部服务器。项目默认保存于 macOS 的 `~/Library/Application Support/Swim Studio/projects`，或 Windows 的 `%LOCALAPPDATA%\Swim Studio\projects`；更新应用不会删除项目。

## English

No Python installation, Git, dependency setup or model download is required. Extract the entire download. On an Apple Silicon Mac running macOS 15 or later, open **Swim Studio.app**. On 64-bit Windows, open **Swim Studio.exe**, keeping the `_internal` folder alongside it. The launcher opens a local browser interface. Keep the launcher open while working; use **Quit** to close the application.

Import one-animal video → calibrate arena → select head points on the first frame → review direct-contact intervals → analyse and export. The **Visual guide** includes diagrams. All analysis is local and works offline, including on first launch. The Windows build uses CPU inference. Results and projects are stored separately from the application.

## Third-party software

CoTracker is by Meta Platforms, Inc. and affiliates, under CC BY-NC 4.0. The bundle contains its source/license, a pinned model version and verified weights, plus license notices for bundled dependencies. This application is intended for non-commercial research use consistent with that license.

Release signing and platform verification status are recorded in the accompanying validation report. An unsigned build may trigger the operating system's publisher-verification dialog on another computer; a signed/notarized distribution is a separate release step.
