# Active Session

**Concept:** 敲酒师 (HitTheBeer) — 工作名/正式名已定：HitTheBeer / 敲酒师（2026-07-11）
**Skill:** /prototype（v2，pivot 后）
**Started:** 2026-07-11
**Review mode:** lean（CD-PLAYTEST 跳过）

## 修正后的假设（v2）
如果一个常驻屏幕角落的小窗口，在玩家正常工作时静默读取**全局**键盘输入，酒液在后台**连续**成形，偶尔浮现一杯完成的酒 + 一位客人——这会让人愿意一直开着它，并产生「我的工作真的酿出了这杯酒」的感觉。

## 为什么 pivot
v1（HTML 文本框）反馈「差很远」：把玩家关进文本框 + 按「完成」违反 GDD 3.1 陪伴优先；离散不连续；输入非真实工作输入导致反馈无说服力。根因：误把全局输入当延后技术题，但它就是「好玩」本身。详见 `prototypes/keyboard-tavern-concept/PIVOT-NOTE.md`。

## Path
桌面程序：PyQt5（边框置顶半透明小窗）+ pynput（全局键盘监听）。文件 `companion.py`。

## Scope (v2, 单一机制：全局输入 → 连续酿造 → 出酒 → 客人)
- pynput 静默统计全局按键（字母/数字/符号、节奏、停顿、相对基线），原始字符即时丢弃
- PyQt5 角落置顶小窗：酒液动画 + 阶段进度 + 实时参数提示 + 等候客人 + 最近结果
- 三阶段按真实时间连续推进，输入加速，空闲基础进度（GDD 5.4）
- 出酒：不抢焦点 toast + 匹配/品质/「为什么是它」解释（移植自 v1，修正空格 bug）
- 3 位客人偏好匹配 + 情绪对白
- 一键暂停采集 + 采集中状态指示

## Explicitly Cut（同 v1）
全局 keyhook 的生产级实现（这里是原型 spike 合并）/ 装备原料·通道卡（掌控弧线，v3）/ 固定配方·复现·设备 / 经济·商店 / 教学流程 / 鼠标点击 / 音乐美术动画 / 目标酒挑战

## Current Phase
Phase 5 — Implement（companion.py 已写入，等待玩家运行试玩 → Phase 6 debrief）

## 运行
`python prototypes/keyboard-tavern-concept/companion.py`（依赖 pynput + PyQt5）
