# PROTOTYPE - NOT FOR PRODUCTION
# Question: 一个常驻屏幕角落的小窗口，静默读取全局键盘输入，酒在后台连续成形——
#           这是否让人愿意一直开着它，并感到“我的工作真的酿出了这杯酒”？
# Date: 2026-07-11
# Run:  python companion.py     (needs: pip install pynput PyQt5)
# Note: pynput 是系统级键盘钩子，杀毒软件可能误报；原始字符即时丢弃，仅留聚合值（GDD 17.4）。

import sys, time, threading, random, math
from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QFont
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout
from pynput import keyboard

# ============================ CONFIG ============================
STAGE_SEC        = 35.0   # 满活跃下单阶段秒数；空闲约 3x
SHOW_SEC         = 3.5    # 出酒后“展示/暂停采集”秒数
TOAST_MS         = 6500   # toast 自动消失
ACTIVITY_WINDOW  = 3.0    # 近 N 秒按键计入活跃度
ACTIVITY_FULL    = 12     # 近窗内 N 键视为满活跃
TARGET_BREW_KEYS = 60     # 满完成度所需按键数（仅影响品质，不阻塞酿造）
PAUSE_MS         = 380.0
BURST_MS         = 150.0
DEFAULT_BASELINE = 220.0
FALLBACK_SIM     = 0.40

BEERS = [
    dict(id='lager', name='酒馆基础拉格', roast=.05, body=.30, bitterness=.10, aroma=.15, fruit=.10, nut=.05, spice=.05, warm=.35, tags=['清爽','淡色'], color='#f1c95b'),
    dict(id='pale',  name='黄昏淡艾尔',   roast=.18, body=.55, bitterness=.38, aroma=.40, fruit=.40, nut=.15, spice=.15, warm=.60, tags=['麦香','温暖'], color='#d99a3e'),
    dict(id='ipa',   name='花园花香IPA',  roast=.20, body=.50, bitterness=.82, aroma=.45, fruit=.25, nut=.15, spice=.25, warm=.80, tags=['苦','花香'],   color='#caa83c'),
    dict(id='amber', name='焦糖琥珀艾尔', roast=.62, body=.60, bitterness=.40, aroma=.38, fruit=.30, nut=.55, spice=.20, warm=.55, tags=['焦糖','圆润'], color='#b5722e'),
    dict(id='stout', name='夜班坚果世涛', roast=.93, body=.80, bitterness=.50, aroma=.30, fruit=.15, nut=.85, spice=.20, warm=.45, tags=['深色','坚果'], color='#4a2a17'),
    dict(id='wheat', name='果园小麦啤',   roast=.16, body=.50, bitterness=.15, aroma=.52, fruit=.82, nut=.15, spice=.30, warm=.74, tags=['果香','柔和'], color='#e3b964'),
]
EXPERIMENT = dict(id='exp', name='酒馆实验酒', tags=['实验','未知'], color='#9a7b5a')
SHORT = dict(lager='拉格', pale='淡艾', ipa='IPA', amber='琥珀', stout='世涛', wheat='小麦')
FEAT = ['roast','body','bitterness','aroma','fruit','nut','spice','warm']
W    = dict(roast=1.3, body=1.0, bitterness=1.2, aroma=1.0, fruit=0.9, nut=0.9, spice=0.8, warm=1.1)
MAXDIST = sum(W[f] for f in FEAT)

GUESTS = [
    dict(id='acan', name='阿灿', role='夜班工人', emoji='👷', prefers=['清爽','淡色','柔和'],
         love='哈——就是这种收工后来一杯的感觉。清爽，不抢戏。', like='嗯，挺顺口的。再来一杯也行。', neutral='还行吧，能喝。', dislike='这杯有点冲，不太像我。', gift='蜂蜜'),
    dict(id='lan',  name='小岚', role='会计',     emoji='🧮', prefers=['焦糖','坚果','深色','圆润'],
         love='这焦糖味儿对极了，像我加班算账时手里那杯。', like='不错，有厚度。', neutral='一般般吧。', dislike='太淡了，没劲儿。', gift='咖啡豆'),
    dict(id='mu',   name='阿木', role='程序员',   emoji='💻', prefers=['苦','花香','麦香'],
         love='苦得正好，花香留在舌根——这就是我写代码到凌晨想要的那口。', like='嗯，有点意思。', neutral='还行，能喝。', dislike='不够劲，写不动代码。', gift='柑橘皮'),
    dict(id='qiao', name='乔姨', role='花店老板', emoji='💐', prefers=['花香','果香','柔和'],
         love='这香气像清晨刚剪下来的花，给我留一壶。', like='闻起来很舒服，我会慢慢喝。', neutral='味道挺稳当。', dislike='苦味盖住花香了。', gift='接骨木花'),
    dict(id='luo',  name='洛洛', role='旅行画师', emoji='🎨', prefers=['果香','温暖','圆润'],
         love='颜色和味道都很有层次，我想把这杯画下来。', like='有点新鲜，适合边画边喝。', neutral='不坏，但还少一点故事。', dislike='太板正了，不像旅行。', gift='晒干橙片'),
    dict(id='bo',   name='老博', role='退休水手', emoji='⚓', prefers=['深色','苦','坚果'],
         love='够沉、够苦，像回港前那阵海风。再来一杯！', like='这杯压得住夜里的寒气。', neutral='能陪我坐一会儿。', dislike='轻飘飘的，没站稳。', gift='烟熏木片'),
]

clamp = lambda v,a,b: a if v<a else b if v>b else v
PCT = lambda x: round(x*100)

def lerp_color(a, b, t):
    ah = int(a[1:],16); bh = int(b[1:],16)
    ar,ag,ab2 = (ah>>16)&255,(ah>>8)&255,ah&255
    br,bg,bb2 = (bh>>16)&255,(bh>>8)&255,bh&255
    return QColor(round(ar+(br-ar)*t), round(ag+(bg-ag)*t), round(ab2+(bb2-ab2)*t))

# ============================ STATE ============================
class BrewStats:
    def __init__(self): self.reset()
    def reset(self):
        self.letters=0; self.digits=0; self.symbols=0; self.key_count=0
        self.pauses=0
        self.last_t=0.0; self.last_kind=None
        self.intervals=[]; self.recent=[]          # intervals(ms)，近窗按键时间戳
        self.run_len=0; self.run_lengths=[]        # 连续段（无停顿）长度统计

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.stats = BrewStats()
        self.history = []
        self.discovered = set()
        self.cup_count = 0
        self.ratio_history = []          # 历次 (lr,dr,sr)，用于个人比例基线（GDD 17.2）
        self.guests = {g['id']: dict(present=True, rel=0, count=0, best_name=None,
                                    best_stars=0, mood=None, line=None, consume=0.0) for g in GUESTS}
        self.last_result = None
        self.paused = False
        self.stage = 0
        self.stage_prog = 0.0
        self.show_timer = 0.0

# ============================ INPUT ============================
def classify(key):
    char = ''
    try: char = key.char or ''
    except AttributeError: char = ''
    if char == '':
        if key == keyboard.Key.space: char = ' '
        else: return None
    if char.isalpha(): return 'letter'
    if char.isdigit(): return 'digit'
    if char.isspace(): return 'space'
    if char.isprintable(): return 'symbol'
    return None

def make_on_press(state):
    def on_press(key):
        kind = classify(key)
        if kind is None: return
        now = time.perf_counter()
        with state.lock:
            if state.paused or state.show_timer > 0: return
            s = state.stats
            if s.last_t > 0:
                dt = (now - s.last_t) * 1000.0
                if dt < 25.0 and kind == s.last_kind:
                    return  # 折损长按自动重复（GDD 5.5）
                s.intervals.append(dt)
                if dt > PAUSE_MS:              # 一段连续输入结束
                    s.pauses += 1
                    if s.run_len > 0: s.run_lengths.append(s.run_len)
                    s.run_len = 1
                else:
                    s.run_len += 1
            else:
                s.run_len = 1
            s.last_t = now; s.last_kind = kind
            if   kind == 'letter': s.letters += 1
            elif kind == 'digit':  s.digits += 1
            elif kind == 'symbol': s.symbols += 1
            s.key_count += 1          # space 也计入活跃度
            s.recent.append(now)
    return on_press

# ============================ FLAVOR / MATCH ============================
def compute_flavor(s, baseline_ms, ready, baseline_ratios=None):
    ratio_total = max(1, s.letters + s.digits + s.symbols)   # 空格不计入比例
    lr = s.letters/ratio_total; dr = s.digits/ratio_total; sr = s.symbols/ratio_total
    active = s.key_count
    # 比例相对【个人基线】的偏离（GDD 17.2：避免职业固定产出）。首杯无基线 → 偏离 0。
    if baseline_ratios:
        plr, pdr, psr = baseline_ratios
    else:
        plr, pdr, psr = lr, dr, sr
    d_lr = lr - plr; d_dr = dr - pdr; d_sr = sr - psr
    # 速度（相对自身）
    cur_mean = (sum(s.intervals)/len(s.intervals)) if s.intervals else DEFAULT_BASELINE
    warm = clamp(0.5 + (baseline_ms - cur_mean)/baseline_ms, 0, 1) if ready else 0.5
    completion = clamp(active/TARGET_BREW_KEYS, 0, 1)
    # 连续度：来自“无停顿的连续段平均长度”，而非“快间隔占比”（后者几乎恒为 1，会让苦度永远拉满）
    runs = s.run_lengths[:]
    if s.run_len > 0: runs.append(s.run_len)
    mean_run = (sum(runs)/len(runs)) if runs else 1.0
    continuity = clamp((mean_run - 5)/18.0, 0, 1)    # ~5 键/段→0；23+→1
    fragmentation = 1 - continuity
    # 风味映射：偏离驱动 roast/spice/fruit，连续度驱动 bitter，碎片化驱动 aroma
    roast  = clamp(max(0.0, d_dr)*4.0 + 0.04, 0, 1)
    nut    = clamp(roast*0.7 + max(0.0, d_dr)*2.0, 0, 1)
    spice  = clamp(max(0.0, d_sr)*4.0 + 0.04, 0, 1)
    fruit  = clamp(max(0.0, d_lr)*3.0 + max(0.0, warm-0.5)*0.8 + fragmentation*0.3, 0, 1)
    bitter = clamp(continuity*0.95 + max(0.0, warm-0.5)*0.3, 0, 1)
    aroma  = clamp(fragmentation*0.7 + max(0.0, 0.5-warm)*0.4 + 0.08, 0, 1)
    body   = clamp(0.35 + completion*0.3, 0, 1)
    vec = dict(roast=roast, body=body, bitterness=bitter, aroma=aroma,
               fruit=fruit, nut=nut, spice=spice, warm=warm)
    return dict(vec=vec, lr=lr, dr=dr, sr=sr, mean_run=mean_run, continuity=continuity,
                d_lr=d_lr, d_dr=d_dr, d_sr=d_sr,
                warm=warm, completion=completion, active=active, ready=ready)

def match_beer(vec, completion=1.0):
    if completion < 0.22:           # 输入过少 → 基础拉格（GDD 5.4：完全空闲也产出基础酒）
        return BEERS[0], 0.55
    best, bd = None, 1e9
    for b in BEERS:
        d = sum(W[f]*abs(vec[f]-b[f]) for f in FEAT)
        if d < bd: bd, best = d, b
    return best, 1 - bd/MAXDIST

def top_reasons(f, n):
    r = []
    if   f['d_dr'] > 0.05: r.append((f['d_dr']+0.25, f"数字占比 {PCT(f['dr'])}%（比你平时高）→ 烘烤度上升，焦糖/坚果/深色"))
    if   f['d_sr'] > 0.05: r.append((f['d_sr']+0.25, f"符号占比 {PCT(f['sr'])}%（比你平时高）→ 香料/草本/野性"))
    if   f['d_lr'] > 0.05: r.append((f['d_lr']+0.25, f"字母占比 {PCT(f['lr'])}%（比你平时高）→ 果香通道充能，水果/酯香"))
    if   f['continuity'] > 0.45: r.append((f['continuity'],     f"长段连续输入（平均 {f['mean_run']:.0f} 键/段）→ 苦度上升"))
    if   f['continuity'] < 0.20 and f['active'] > 10: r.append((0.30, "短促、频繁停顿的碎片化输入 → 香气保留"))
    if   f['warm'] > 0.62: r.append((f['warm']-0.5,  "节奏比你平均快 → 暖发酵，艾尔/活跃/果香"))
    elif f['warm'] < 0.38: r.append((0.5-f['warm'],  "节奏比你平均慢 → 冷发酵，拉格/干净/清爽"))
    if not f['ready'] and f['active'] > 4: r.append((0.1, "（首杯正在建立你的节奏与比例基线）"))
    if f['completion'] < 0.22 and f['active'] >= 0: r.append((0.15, "输入较少 → 走向稳定、清淡的基础酒"))
    r.sort(key=lambda x: -x[0])
    return [t for _,t in r[:n]]

def pick_guest(beer, stars, is_exp):
    best, best_score = GUESTS[0], -1
    for g in GUESTS:
        sc = 0
        for t in beer['tags']:
            if t in g['prefers']:
                sc += len(g['prefers']) - g['prefers'].index(t)
        if sc > best_score: best_score, best = sc, g
    aff = best_score/5.0
    if is_exp or best_score == 0: mood = 'neutral' if stars >= 3 else 'dislike'
    elif aff >= 0.6 and stars >= 4: mood = 'love'
    elif aff >= 0.3 or stars >= 3:  mood = 'like'
    else: mood = 'neutral'
    return best, mood

# caller MUST hold state.lock
def do_complete(state):
    s = state.stats
    if s.run_len > 0: s.run_lengths.append(s.run_len); s.run_len = 0   # 收尾当前连续段
    if state.history:
        allint = [x for sub in state.history for x in sub]
        baseline_ms = sum(allint)/len(allint); ready = True
    else:
        baseline_ms = DEFAULT_BASELINE; ready = False
    baseline_ratios = (None if not state.ratio_history else
                       tuple(sum(x[i] for x in state.ratio_history)/len(state.ratio_history) for i in range(3)))
    f = compute_flavor(s, baseline_ms, ready, baseline_ratios)
    beer, sim = match_beer(f['vec'], f['completion'])
    is_exp = sim < FALLBACK_SIM
    result_beer = EXPERIMENT if is_exp else beer
    quality = int(clamp(round(45 + 25*sim*clamp(f['completion']*2,0,1) + 15*f['completion'] + random.uniform(-3,3)), 20, 95))
    stars = 5 if quality>=85 else 4 if quality>=75 else 3 if quality>=65 else 2 if quality>=55 else 1
    g, mood = pick_guest(result_beer, stars, is_exp)
    gs = state.guests[g['id']]                       # 客人持久状态：关系/喝过/最爱/心情
    gs['present'] = True
    gs['rel'] = max(0, gs['rel'] + {'love':3,'like':1,'neutral':0,'dislike':-1}[mood])
    gs['count'] += 1
    if stars > gs['best_stars']:
        gs['best_stars'] = stars; gs['best_name'] = result_beer['name']
    gs['mood'] = mood; gs['line'] = g[mood]; gs['consume'] = SHOW_SEC
    reasons = top_reasons(f, 2)
    if len(s.intervals) > 3: state.history.append(list(s.intervals))
    ratio_total = max(1, s.letters + s.digits + s.symbols)
    state.ratio_history.append((s.letters/ratio_total, s.digits/ratio_total, s.symbols/ratio_total))
    new = (not is_exp) and (result_beer['id'] not in state.discovered)
    if not is_exp: state.discovered.add(result_beer['id'])
    state.cup_count += 1
    state.last_result = dict(
        name=result_beer['name'], stars=stars, quality=quality, reasons=reasons,
        sim=sim, closest=beer['name'], is_exp=is_exp, guest=g, mood=mood, new=new,
        color=result_beer.get('color','#9a7b5a'), tags=list(result_beer['tags']))
    s.reset()
    state.stage = 0; state.stage_prog = 0.0
    state.show_timer = SHOW_SEC

# ============================ UI ============================
class VatWidget(QWidget):
    def __init__(self):
        super().__init__(); self.setFixedSize(72, 96)
        self.level = 0.25; self.color = QColor('#f1c95b')
    def set_liquid(self, level, color):
        self.level = clamp(level, 0, 1); self.color = QColor(color); self.update()
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor('#6a4d2e'), 2))
        p.setBrush(QBrush(QColor(26,17,10,235)))
        p.drawRoundedRect(QRectF(3, 3, w-6, h-6), 10, 12)
        lh = max(2.0, (h-14) * self.level)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(self.color))
        p.drawRoundedRect(QRectF(5, h-9-lh, w-10, lh), 7, 7)

LABEL = "color:#f3e3c5; font-size:13px;"
MUTED = "color:#b89b73; font-size:12px;"
SMALL = "color:#b89b73; font-size:11px;"
HINT  = "color:#d99a3e; font-size:12px;"

class TavernScene(QWidget):
    """960px 酒馆大厅：客人闲逛、落座，员工巡场；出酒后完成一整段送酒与消费反馈。"""
    FLOOR_Y = 142
    BAR_LEFT = 610
    BAR_TOP = 91

    def __init__(self, on_guest_click):
        super().__init__(); self.setFixedHeight(180)
        self.on_guest_click = on_guest_click
        self.gstates = {}
        self.fig = {}
        for i, g in enumerate(GUESTS):
            x = 62.0 + i*88.0
            self.fig[g['id']] = dict(x=x, tx=x, off=i*1.7, lane=i%2,
                                     mode='wander', timer=random.uniform(0, 3), bubble='',
                                     face='', fx=[])
        self.service = None
        self.server = dict(x=585.0, tx=585.0, mode='patrol', timer=0.0, carry=False)
        self.cleaner = dict(x=150.0, tx=370.0, timer=0.0)
        self.t = 0.0; self.staff_bob = 0.0; self.ambient_timer = 2.2
        self.timer = QTimer(self); self.timer.timeout.connect(self.advance); self.timer.start(50)

    def update_guests(self, gstates):
        self.gstates = gstates or {}

    def trigger_serve(self, gid, beer_name, guest, mood):
        f = self.fig.get(gid)
        if not f: return
        table_x = max(95.0, min(535.0, f['x']))
        f.update(mode='wait_service', tx=table_x, timer=0.0, beer=beer_name,
                 bubble='', reaction=guest[mood],
                 face={'love':'😍','like':'🙂','neutral':'😐','dislike':'😟'}.get(mood,''))
        self.server.update(mode='pickup', tx=self.BAR_LEFT+52, timer=0.0, carry=False)
        self.service = dict(gid=gid, beer=beer_name, mood=mood, phase='pour', timer=0.0)

    def advance(self):
        dt = 0.05; self.t += dt
        self.staff_bob = math.sin(self.t*1.8)*2
        self.ambient_timer -= dt
        for gid, f in self.fig.items():
            if not self.gstates.get(gid, {}).get('present'):
                continue
            m = f['mode']; f['timer'] += dt
            if m == 'wander':
                if f['timer'] > 2.8 + (f['off'] % 2):
                    f['timer'] = 0.0; f['tx'] = random.uniform(38, 565)
                    if random.random() < .28: f['mode'] = 'chat'; f['timer'] = 0.0
                f['x'] += clamp(f['tx']-f['x'], -24*dt, 24*dt)
            elif m == 'chat':
                if f['timer'] > 1.8: f['mode'] = 'wander'; f['timer'] = 0.0
            elif m == 'wait_service':
                f['x'] += clamp(f['tx']-f['x'], -55*dt, 55*dt)
            elif m == 'drink':
                nh = []
                for symbol, hx, hy, age in f['fx']:
                    age += dt
                    if age < 1.8: nh.append((symbol, hx, hy-age*24, age))
                f['fx'] = nh
                if f['timer'] > 2.4:
                    f['mode'] = 'return'; f['timer'] = 0.0
                    f['tx'] = random.uniform(38, 565); f['bubble'] = ''
            elif m == 'return':
                f['x'] += clamp(f['tx']-f['x'], -60*dt, 60*dt)
                if abs(f['x']-f['tx']) < 4 or f['timer'] > 2.2:
                    f['mode'] = 'wander'; f['timer'] = 0.0

        # 服务员有自己的巡场节奏；出酒时从吧台取杯，再走到客人面前交付。
        sv = self.server; sv['timer'] += dt
        if self.service:
            job = self.service; job['timer'] += dt
            guest = self.fig[job['gid']]
            if job['phase'] == 'pour' and job['timer'] > .65:
                job.update(phase='deliver', timer=0.0); sv.update(mode='deliver', tx=guest['x']+28, carry=True)
            elif job['phase'] == 'deliver':
                sv['tx'] = guest['x']+28
                sv['x'] += clamp(sv['tx']-sv['x'], -115*dt, 115*dt)
                if abs(sv['x']-sv['tx']) < 5:
                    job.update(phase='react', timer=0.0); sv['carry'] = False
                    guest.update(mode='drink', timer=0.0, bubble=guest['reaction'])
                    effect = '♥' if job['mood'] in ('love','like') else '…'
                    guest['fx'] = [(effect, guest['x'], 94, 0.0), ('+消费', guest['x']+22, 103, 0.0)]
            elif job['phase'] == 'react' and job['timer'] > 1.8:
                self.service = None; sv.update(mode='return', tx=self.BAR_LEFT+25, timer=0.0)
        else:
            if sv['mode'] in ('return','deliver','pickup'):
                sv['x'] += clamp(sv['tx']-sv['x'], -75*dt, 75*dt)
                if abs(sv['x']-sv['tx']) < 5: sv.update(mode='patrol', timer=0.0)
            elif sv['timer'] > 3.0:
                sv.update(tx=random.uniform(430, 650), timer=0.0)
            else:
                sv['x'] += clamp(sv['tx']-sv['x'], -30*dt, 30*dt)

        # 清洁员工在桌区来回移动，和服务员形成不同的工作动线。
        cl = self.cleaner; cl['timer'] += dt
        cl['x'] += clamp(cl['tx']-cl['x'], -18*dt, 18*dt)
        if abs(cl['x']-cl['tx']) < 5:
            cl['tx'] = random.uniform(90, 390); cl['timer'] = 0.0

        if self.ambient_timer <= 0 and not self.service:
            visible = [f for gid, f in self.fig.items() if self.gstates.get(gid, {}).get('present')]
            if visible:
                f = random.choice(visible); f['bubble'] = random.choice(('今晚挺热闹', '再坐一会儿', '闻到麦香了'))
                QTimer.singleShot(1600, lambda f=f: f.update(bubble='') if f['mode'] != 'drink' else None)
            self.ambient_timer = random.uniform(4.5, 7.0)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(40,27,16))); p.drawRect(0,0,w,h)
        # 背景分区：左侧桌区，中部通道，右侧吧台/酒架。
        p.setBrush(QBrush(QColor(217,154,62,24)))
        for lx in (120, 350, 750): p.drawEllipse(QRectF(lx-70,-45,140,120))
        p.setBrush(QBrush(QColor(30,20,12))); p.drawRect(0, self.FLOOR_Y, w, h-self.FLOOR_Y)
        p.setPen(QPen(QColor(77,50,29), 1))
        for x in range(0, w, 48): p.drawLine(x, self.FLOOR_Y, x+28, h)
        # 窗、桌椅与公告板让空间看起来像大厅，而不是状态面板。
        p.setBrush(QBrush(QColor(24,35,42))); p.setPen(QPen(QColor('#6a4d2e'),2))
        p.drawRoundedRect(QRectF(28,18,118,48),5,5)
        p.drawLine(87,18,87,66); p.drawLine(28,42,146,42)
        p.setBrush(QBrush(QColor(80,51,27))); p.setPen(Qt.NoPen)
        for tx in (135, 345, 520):
            p.drawRoundedRect(QRectF(tx-34,116,68,8),4,4); p.drawRect(tx-3,124,6,23)
        p.setBrush(QBrush(QColor(62,40,22))); p.drawRoundedRect(QRectF(465,22,108,48),4,4)
        p.setPen(QColor('#d99a3e')); p.setFont(QFont("Microsoft YaHei",8))
        p.drawText(QRectF(470,27,98,38), Qt.AlignCenter|Qt.TextWordWrap, "今日酒单\n键盘酿造 · 随机风味")
        # 右侧吧台与酒架。
        p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(54,35,19))); p.drawRect(self.BAR_LEFT,18,w-self.BAR_LEFT-14,56)
        for y in (35,58): p.setBrush(QBrush(QColor(101,67,34))); p.drawRect(self.BAR_LEFT+10,y,w-self.BAR_LEFT-34,3)
        bottle_colors = ('#b5722e','#d99a3e','#6f3f24')
        for i, x in enumerate(range(self.BAR_LEFT+22, w-22, 34)):
            p.setBrush(QBrush(QColor(bottle_colors[i % len(bottle_colors)]))); p.drawRoundedRect(QRectF(x,25,8,12),2,2)
        p.setBrush(QBrush(QColor(74,48,26))); p.drawRect(self.BAR_LEFT, self.BAR_TOP, w-self.BAR_LEFT, 11)
        p.setBrush(QBrush(QColor(58,37,20))); p.drawRect(self.BAR_LEFT, self.BAR_TOP+11, w-self.BAR_LEFT, 55)
        # 工作人员：酒保固定出杯，服务员走全场，清洁员工在桌区巡场。
        p.setFont(QFont("Microsoft YaHei", 20)); p.setPen(QColor('#f3e3c5'))
        p.drawText(QRectF(728,57+self.staff_bob,54,30), Qt.AlignCenter, "🧑‍🍳")
        p.setFont(QFont("Microsoft YaHei",7)); p.setPen(QColor('#b89b73')); p.drawText(QRectF(728,82,54,10),Qt.AlignCenter,"酒保 · 调酒")
        self._staff(p, self.server['x'], 119, "🧑‍💼", "服务员", self.server['carry'])
        self._staff(p, self.cleaner['x'], 151, "🧹", "清洁", False)
        if self.service and self.service['phase'] == 'pour':
            self._bubble(p, 755, 56, "正在准备这杯")
        # 客人
        for g in GUESTS:
            f = self.fig[g['id']]; gs = self.gstates.get(g['id'], {})
            if not gs.get('present'): continue
            bob = math.sin(self.t*3 + f['off'])*2
            gx = f['x']; gy = (111 if f['lane']==0 else 137) + bob
            p.setPen(QColor('#b89b73')); p.setFont(QFont("Microsoft YaHei", 8))
            p.drawText(QRectF(gx-30, gy-34, 60, 11), Qt.AlignCenter, g['name'])
            hearts = min(5, (gs.get('rel',0) or 0)//2)
            p.setPen(QColor('#e06b6b')); p.setFont(QFont("Microsoft YaHei", 7))
            p.drawText(QRectF(gx-22, gy-23, 44, 10), Qt.AlignCenter, ('♥'*hearts) or '·')
            p.setPen(Qt.NoPen); p.setFont(QFont("Microsoft YaHei", 17))
            p.drawText(QRectF(gx-14, gy-14, 30, 30), Qt.AlignCenter, g['emoji'])
            if f['face'] and f['mode'] == 'drink':
                p.setFont(QFont("Microsoft YaHei", 10))
                p.drawText(QRectF(gx+8, gy-8, 18, 18), Qt.AlignCenter, f['face'])
            if f['bubble']:
                self._bubble(p, gx, gy-32, f['bubble'])
            p.setFont(QFont("Microsoft YaHei", 8)); p.setPen(QColor('#8bc34a'))
            for symbol, hx, hy, _age in f['fx']:
                p.drawText(QRectF(hx-18, hy, 48, 14), Qt.AlignCenter, symbol)
        p.end()

    def _staff(self, p, x, y, emoji, label, carry):
        p.setPen(Qt.NoPen); p.setFont(QFont("Microsoft YaHei",16))
        p.drawText(QRectF(x-18,y-22,36,25),Qt.AlignCenter,emoji)
        if carry:
            p.setFont(QFont("Microsoft YaHei",11)); p.drawText(QRectF(x+7,y-20,24,20),Qt.AlignCenter,"🍺")
        p.setFont(QFont("Microsoft YaHei",7)); p.setPen(QColor('#b89b73'))
        p.drawText(QRectF(x-24,y+1,48,10),Qt.AlignCenter,label)

    def _bubble(self, p, x, y, text):
        text = text[:18]
        tw = min(150, 9*len(text)+14); th = 22
        bx = x-tw/2; by = y-th
        p.setBrush(QBrush(QColor(243,227,197,240))); p.setPen(QPen(QColor('#d99a3e'),1))
        p.drawRoundedRect(QRectF(bx, by, tw, th), 7, 7)
        p.setPen(QColor(40,27,16)); p.setFont(QFont("Microsoft YaHei", 8))
        p.drawText(QRectF(bx, by, tw, th), Qt.AlignCenter, text)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton: return
        x, y = e.x(), e.y()
        for g in GUESTS:
            if not self.gstates.get(g['id'], {}).get('present'): continue
            f = self.fig[g['id']]
            gy = 111 if f['lane']==0 else 137
            if abs(f['x']-x) < 22 and abs(gy-y) < 27:
                self.on_guest_click(g['id']); return


class CompanionWindow(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(480, 270)   # 挂机 480×270；大厅展开后总尺寸 1440×270
        self._drag = None
        self.flash = 0.0
        self.mode = 'idle'
        self.last_cups = 0

        outer = QHBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        idle = QWidget(); idle.setFixedWidth(480); outer.addWidget(idle)
        root = QVBoxLayout(idle); root.setContentsMargins(16,12,12,12); root.setSpacing(6)

        top = QHBoxLayout(); top.setSpacing(8)
        self.title = QLabel("🍺 敲酒师")
        self.title.setStyleSheet("color:#f3e3c5; font-size:14px; font-weight:600;")
        self.status = QLabel("● 采集中")
        self.status.setStyleSheet("color:#8bc34a; font-size:11px;")
        self.count_lbl = QLabel("0杯 · 0/6")
        self.count_lbl.setStyleSheet("color:#b89b73; font-size:11px;")
        top.addWidget(self.title); top.addStretch(); top.addWidget(self.count_lbl); top.addWidget(self.status)
        self.pause_btn = QPushButton("⏸"); self.pause_btn.setFixedSize(26,26)
        self.pause_btn.setStyleSheet("background:#3a2a18; color:#f3e3c5; border:1px solid #5a4128; border-radius:13px;")
        self.pause_btn.clicked.connect(self.toggle_pause)
        top.addWidget(self.pause_btn)
        self.expand_btn = QPushButton("👤大厅"); self.expand_btn.setFixedHeight(26)
        self.expand_btn.setStyleSheet("background:#3a2a18; color:#f3e3c5; border:1px solid #5a4128; border-radius:13px; padding:0 8px; font-size:11px;")
        self.expand_btn.clicked.connect(self.toggle_mode)
        top.addWidget(self.expand_btn)
        root.addLayout(top)

        mid = QHBoxLayout(); mid.setSpacing(12)
        self.vat = VatWidget()
        right = QVBoxLayout(); right.setSpacing(4)
        self.stage_lbl = QLabel("麦芽处理 · 0%")
        self.stage_lbl.setStyleSheet(LABEL)
        self.hint_lbl = QLabel("开始工作，酒液会慢慢成形……")
        self.hint_lbl.setStyleSheet(HINT); self.hint_lbl.setWordWrap(True)
        self.guest_lbl = QLabel("一位客人在角落等着……")
        self.guest_lbl.setStyleSheet(MUTED); self.guest_lbl.setWordWrap(True)
        right.addWidget(self.stage_lbl); right.addWidget(self.hint_lbl); right.addStretch(); right.addWidget(self.guest_lbl)
        mid.addWidget(self.vat); mid.addLayout(right, 1)
        root.addLayout(mid)

        self.last_lbl = QLabel("还没有酿出酒")
        self.last_lbl.setStyleSheet("color:#f3e3c5; font-size:12px; background:#15100a; border-radius:6px; padding:6px 8px;")
        self.last_lbl.setWordWrap(True)
        root.addWidget(self.last_lbl)

        strip = QHBoxLayout(); strip.setSpacing(4); strip.setContentsMargins(0,0,0,0)
        self.slots = []
        for b in BEERS:
            sl = QLabel("？"); sl.setAlignment(Qt.AlignCenter); sl.setFixedSize(70, 24)
            sl.setStyleSheet("color:#6a5238; font-size:10px; background:#15100a; border:1px solid #2e2218; border-radius:5px;")
            self.slots.append(sl); strip.addWidget(sl)
        root.addLayout(strip)

        foot = QLabel("拖动移动 · 右键退出 · 你的输入只被统计，不记录文字")
        foot.setStyleSheet(SMALL)
        root.addWidget(foot)

        # ---- 右：酒馆大厅面板 960（默认隐藏，左侧 480 挂机面板保持不变）----
        self.hall = QWidget(); self.hall.setFixedWidth(960); self.hall.setVisible(False)
        hr = QVBoxLayout(self.hall); hr.setContentsMargins(12,8,16,8); hr.setSpacing(4)
        htop = QHBoxLayout()
        htitle = QLabel("🍺 酒馆大厅"); htitle.setStyleSheet("color:#f3e3c5; font-size:14px; font-weight:600;")
        self.hall_sub = QLabel("客人正在活动 · 员工巡场 · 出酒后会完成送酒与消费反馈"); self.hall_sub.setStyleSheet(MUTED)
        collapse = QPushButton("◂ 收起回挂机"); collapse.setFixedHeight(24)
        collapse.setStyleSheet("background:#3a2a18; color:#b89b73; border:1px solid #5a4128; border-radius:11px; padding:0 10px;")
        collapse.clicked.connect(self.toggle_mode)
        htop.addWidget(htitle); htop.addSpacing(8); htop.addWidget(self.hall_sub); htop.addStretch(); htop.addWidget(collapse); hr.addLayout(htop)
        self.scene = TavernScene(self.show_profile); hr.addWidget(self.scene)
        self.feedback_lbl = QLabel("消费动态 · 大厅已经开门，客人会在桌区与吧台之间活动")
        self.feedback_lbl.setFixedHeight(30)
        self.feedback_lbl.setStyleSheet("color:#f3e3c5; font-size:11px; background:#15100a; border:1px solid #2e2218; border-radius:6px; padding:4px 8px;")
        self.feedback_lbl.setWordWrap(False); hr.addWidget(self.feedback_lbl)
        outer.addWidget(self.hall)

        # position bottom-right
        sg = QApplication.primaryScreen().availableGeometry()
        self.move(sg.right()-self.width()-18, sg.bottom()-self.height()-10)

        self.profile = GuestProfile()
        self.toast = Toast()
        self.last_t = time.perf_counter()
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(100)

    def toggle_mode(self):
        right_edge = self.x() + self.width()
        sg = QApplication.primaryScreen().availableGeometry()
        if self.mode == 'idle':
            self.mode = 'hall'; self.hall.setVisible(True); self.setFixedSize(1440,270)
            self.expand_btn.setText("◂收起"); self.move(max(sg.left(), right_edge-1440), self.y())
        else:
            self.mode = 'idle'; self.hall.setVisible(False); self.setFixedSize(480,270)
            self.expand_btn.setText("👤大厅"); self.move(right_edge-480, self.y())

    def show_profile(self, gid):
        g = next(x for x in GUESTS if x['id']==gid)
        self.profile.show_guest(g, self.state.guests.get(gid))

    # ----- drag -----
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPos() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPos() - self._drag)
    def mouseReleaseEvent(self, _): self._drag = None

    def contextMenuEvent(self, e):
        from PyQt5.QtWidgets import QMenu
        m = QMenu(self)
        a1 = m.addAction("⏸ 暂停采集" if not self.state.paused else "▶ 继续采集")
        m.addAction("✖ 退出")
        act = m.exec_(e.globalPos())
        if act is None: return
        if act.text().startswith("⏸") or act.text().startswith("▶"): self.toggle_pause()
        else: QApplication.quit()

    def toggle_pause(self):
        with self.state.lock:
            self.state.paused = not self.state.paused
            paused = self.state.paused
        self.status.setText("⏸ 已暂停" if paused else "● 采集中")
        self.status.setStyleSheet(("color:#b89b73;" if paused else "color:#8bc34a;") + " font-size:11px;")
        self.pause_btn.setText("▶" if paused else "⏸")

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(29,20,13,235))); p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 14, 14)
        bc = lerp_color('#5a4128', '#d99a3e', self.flash)
        p.setPen(QPen(bc, 1 + 2*self.flash)); p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0.5,0.5,self.width()-1,self.height()-1), 14, 14)
        if self.mode == 'hall':
            p.setPen(QPen(QColor(90,65,40,160), 1)); p.drawLine(480, 16, 480, self.height()-16)

    # ----- main loop -----
    def tick(self):
        now = time.perf_counter(); dt = min(0.25, now - self.last_t); self.last_t = now
        st = self.state
        toast_info = None
        with st.lock:
            if st.show_timer > 0:
                st.show_timer -= dt
                if st.show_timer <= 0:
                    st.show_timer = 0.0
                    if st.last_result: toast_info = st.last_result
            else:
                s = st.stats
                s.recent = [t for t in s.recent if now - t < ACTIVITY_WINDOW]
                activity = min(1.0, len(s.recent)/ACTIVITY_FULL)
                rate = (0.3 + 0.7*activity) / STAGE_SEC      # 空闲也推进（GDD 5.4）
                st.stage_prog += rate*dt
                while st.stage_prog >= 1.0 and st.show_timer <= 0:
                    st.stage_prog -= 1.0
                    st.stage += 1
                    if st.stage >= 3:
                        do_complete(st)
                        break
            # snapshot for UI (capture under lock, use after release)
            s = st.stats
            if st.history:
                allint=[x for sub in st.history for x in sub]; bms=sum(allint)/len(allint); ready=True
            else: bms=DEFAULT_BASELINE; ready=False
            bratios = (None if not st.ratio_history else
                       tuple(sum(x[i] for x in st.ratio_history)/len(st.ratio_history) for i in range(3)))
            for gs in st.guests.values():
                if gs['consume'] > 0: gs['consume'] = max(0.0, gs['consume']-dt)
            snap = dict(stage=st.stage, stage_prog=st.stage_prog, show_timer=st.show_timer,
                        paused=st.paused, kc=s.key_count,
                        cups=st.cup_count, discovered=set(st.discovered),
                        guests={k:dict(v) for k,v in st.guests.items()},
                        live=compute_flavor(s, bms, ready, bratios), last=st.last_result)
        # ---- update widgets (main thread, lock released) ----
        if toast_info: self.flash = 1.0
        else: self.flash = max(0.0, self.flash - dt*1.6)
        self.count_lbl.setText(f"{snap['cups']}杯 · {len(snap['discovered'])}/6")
        for i,b in enumerate(BEERS):
            sl = self.slots[i]
            if b['id'] in snap['discovered']:
                sl.setText(SHORT[b['id']])
                sl.setStyleSheet(f"color:#1d140d; font-size:10px; font-weight:600; background:{b['color']}; border:1px solid #5a4128; border-radius:5px;")
            else:
                sl.setText("？")
                sl.setStyleSheet("color:#6a5238; font-size:10px; background:#15100a; border:1px solid #2e2218; border-radius:5px;")
        STAGE_NAMES = ['麦芽处理','糖化/煮沸','发酵表现']
        if snap['show_timer'] > 0:
            self.stage_lbl.setText("✦ 出酒中……")
        else:
            self.stage_lbl.setText(f"{STAGE_NAMES[snap['stage']]} · {PCT(snap['stage_prog'])}%")
        if not snap['paused']:
            self.vat.set_liquid(0.18 + (snap['stage']+snap['stage_prog'])/3.0*0.7,
                                lerp_color('#f1c95b','#4a2a17', snap['live']['vec']['roast']).name())
            if snap['kc'] > 0:
                top = top_reasons(snap['live'], 1)
                beer, sim = match_beer(snap['live']['vec'], snap['live']['completion'])
                self.hint_lbl.setText(f"{top[0] if top else '—'} · 接近 {beer['name']} {PCT(sim)}%")
            else:
                self.hint_lbl.setText("开始工作，酒液会慢慢成形……")
        last = snap['last']
        if last:
            stars = '★'*last['stars'] + '☆'*(5-last['stars'])
            self.last_lbl.setText(f"最近：{last['name']} {stars} · {' '.join(last['tags'])}" + (" ✦新" if last['new'] else ""))
            g, mood = last['guest'], last['mood']
            self.guest_lbl.setText(f"{g['emoji']} {g['name']}（{g['role']}）：{g[mood]}")
        # ---- 大厅：场景客人状态 + 出酒触发上酒动画 ----
        self.scene.update_guests(snap['guests'])
        if snap['cups'] > self.last_cups:
            self.last_cups = snap['cups']
            if snap['last']:
                self.scene.trigger_serve(snap['last']['guest']['id'], snap['last']['name'],
                                         snap['last']['guest'], snap['last']['mood'])
        if last:
            gg = last['guest']
            self.feedback_lbl.setText(
                f"消费动态 · {gg['emoji']} <b>{gg['name']}</b> 买下并喝了 <b>{last['name']}</b> {'★'*last['stars']} · <i>{gg[last['mood']]}</i>"
                + (f"　<span style='color:#8bc34a'>🎁 留下 {gg['gift']} · 关系提升</span>" if last['mood']=='love' else ""))
        if toast_info and self.mode == 'idle':
            self.toast.show_result(toast_info)

class GuestSeat(QWidget):
    """大厅里的一个客座：显示客人头像/名字/关系心/心情/反应；未遇到为剪影。"""
    def __init__(self, g, on_click):
        super().__init__(); self.g = g; self.on_click = on_click
        self.gs = None; self.consuming = False
        self.setFixedSize(144, 152); self.setCursor(Qt.PointingHandCursor)
    def set_state(self, gs, consuming):
        self.gs = gs; self.consuming = consuming; self.update()
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.gs and self.gs.get('present'):
            self.on_click(self.g['id'])
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        present = bool(self.gs and self.gs.get('present'))
        border = QColor('#d99a3e') if self.consuming else (QColor('#5a4128') if present else QColor('#2e2218'))
        p.setBrush(QBrush(QColor(26,17,10,235))); p.setPen(QPen(border, 2 if self.consuming else 1))
        p.drawRoundedRect(QRectF(1,1,self.width()-2,self.height()-2), 10, 10)
        w = self.width()
        if present:
            p.setPen(Qt.NoPen)
            p.setFont(QFont("Microsoft YaHei", 26)); p.drawText(QRectF(0,6,w,40), Qt.AlignCenter, self.g['emoji'])
            p.setFont(QFont("Microsoft YaHei", 11, QFont.Bold)); p.setPen(QColor('#f3e3c5'))
            p.drawText(QRectF(0,46,w,18), Qt.AlignCenter, self.g['name'])
            hearts = min(5, (self.gs.get('rel',0) or 0)//2)
            p.setFont(QFont("Microsoft YaHei", 10)); p.setPen(QColor('#e06b6b'))
            p.drawText(QRectF(0,64,w,16), Qt.AlignCenter, '♥'*hearts + '♡'*(5-hearts))
            face = {'love':'😍','like':'🙂','neutral':'😐','dislike':'😟'}.get(self.gs.get('mood'),'')
            p.setFont(QFont("Microsoft YaHei", 9)); p.setPen(QColor('#b89b73'))
            line = self.gs.get('line') or '坐在吧台等你'
            p.drawText(QRectF(6,86,w-12,self.height()-92), Qt.AlignCenter|Qt.TextWordWrap, f"{face} {line}")
            if self.consuming:
                p.setFont(QFont("Microsoft YaHei", 9, QFont.Bold)); p.setPen(QColor('#8bc34a'))
                p.drawText(QRectF(0,self.height()-18,w,14), Qt.AlignCenter, "正在品尝…")
        else:
            p.setFont(QFont("Microsoft YaHei", 26)); p.setPen(QColor('#5a4128'))
            p.drawText(QRectF(0,34,w,40), Qt.AlignCenter, "?")
            p.setFont(QFont("Microsoft YaHei", 10))
            p.drawText(QRectF(0,76,w,16), Qt.AlignCenter, "未遇到")


class GuestProfile(QWidget):
    """点击客座弹出的人物资料卡（偏好/喝过/最爱/关系/赠礼）。"""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating); self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(300)
        self.lbl = QLabel(self); self.lbl.setWordWrap(True); self.lbl.setAlignment(Qt.AlignTop)
        self.lbl.setAttribute(Qt.WA_TransparentForMouseEvents)   # 让点击穿透到本窗，点哪都关闭
        self.lbl.setStyleSheet("color:#f3e3c5; font-size:13px; background:#1d140d; border:2px solid #d99a3e; border-radius:10px; padding:12px;")
        v = QVBoxLayout(self); v.setContentsMargins(0,0,0,0); v.addWidget(self.lbl)
        self.hide()
    def show_guest(self, g, gs):
        gs = gs or {}
        hearts = min(5, (gs.get('rel',0) or 0)//2)
        best = (f"{gs.get('best_name','—')} {'★'*gs.get('best_stars',0)}") if gs.get('best_name') else '—'
        self.lbl.setText(
            f"<b style='color:#d99a3e;font-size:16px'>{g['emoji']} {g['name']}</b> "
            f"<span style='color:#b89b73;font-size:11px'>· {g['role']}</span><br><br>"
            f"<span style='color:#b89b73'>偏好风味：</span>{' '.join(g['prefers'])}<br>"
            f"<span style='color:#b89b73'>累计喝过：</span>{gs.get('count',0)} 杯<br>"
            f"<span style='color:#b89b73'>最满意：</span>{best}<br>"
            f"<span style='color:#b89b73'>关系：</span><span style='color:#e06b6b'>{'♥'*hearts}</span>{'♡'*(5-hearts)}<br>"
            f"<span style='color:#b89b73'>会赠送：</span>{g.get('gift','—')}<br><br>"
            f"<span style='color:#6a5238;font-size:11px'>（点击关闭）</span>")
        self.adjustSize()
        sg = QApplication.primaryScreen().availableGeometry()
        self.move(sg.right()-self.width()-18, sg.bottom()-self.height()-260)
        self.show()
    def mousePressEvent(self, e): self.hide()
    def paintEvent(self, _): pass


class Toast(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating); self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(320)
        self.label = QLabel(self); self.label.setWordWrap(True)
        self.label.setStyleSheet("color:#f3e3c5; font-size:13px; background:#1d140d; border:1px solid #d99a3e; border-radius:10px; padding:12px;")
        v = QVBoxLayout(self); v.setContentsMargins(0,0,0,0); v.addWidget(self.label)
        self.hide()
    def show_result(self, r):
        stars = '★'*r['stars'] + '☆'*(5-r['stars'])
        why = "<br>".join("· "+x for x in r['reasons'])
        gift = f"<br><span style='color:#8bc34a'>🎁 {r['guest']['name']} 留下了 {r['guest']['gift']}（解锁线索）</span>" if r['mood']=='love' else ""
        newbadge = "<span style='color:#8bc34a;font-size:13px'>✦ 新发现！</span><br>" if r['new'] else ""
        self.label.setStyleSheet(
            "color:#f3e3c5; font-size:14px; background:#1d140d; border:2px solid "
            + ("#8bc34a" if r['new'] else "#d99a3e") + "; border-radius:10px; padding:12px;")
        self.label.setText(
            f"{newbadge}<b style='color:#d99a3e;font-size:16px'>🍺 {r['name']}</b> {stars} "
            f"<span style='color:#b89b73;font-size:11px'>({r['quality']}分 · 相似度 {PCT(r['sim'])}%)</span><br>"
            f"<span style='color:#b89b73;font-size:11px'>为什么是它：</span><br>{why}<br>"
            f"<span style='color:#b89b73;font-size:11px'>{r['guest']['emoji']} {r['guest']['name']}：{r['guest'][r['mood']]}</span>{gift}")
        self.adjustSize()
        sg = QApplication.primaryScreen().availableGeometry()
        self.move(sg.right()-self.width()-18, sg.bottom()-self.height()-260)
        self.show()
        QTimer.singleShot(TOAST_MS + (3000 if r['new'] else 0), self.hide)
    def paintEvent(self, _): pass

# ============================ MAIN ============================
def main():
    app = QApplication(sys.argv)
    state = State()
    listener = keyboard.Listener(on_press=make_on_press(state))
    listener.daemon = True; listener.start()
    win = CompanionWindow(state)
    win.show()
    app.aboutToQuit.connect(lambda: listener.stop())
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
