# PyInstaller hook for pynput
# pynput 在运行时用动态导入加载平台键盘/鼠标后端（win32/darwin/xorg），
# PyInstaller 静态分析看不到，必须显式声明，否则冻结后的 exe 报：
#   pynput._util ... raise ImportError  (后端找不到)
hiddenimports = [
    'pynput.keyboard._win32', 'pynput.mouse._win32', 'pynput._util.win32',
    'pynput.keyboard._darwin', 'pynput.mouse._darwin', 'pynput._util.darwin',
    'pynput.keyboard._xorg', 'pynput.mouse._xorg', 'pynput._util.xorg',
]
