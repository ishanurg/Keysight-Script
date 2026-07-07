import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
import os, re, threading, time, queue, json
from datetime import datetime

_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_MEMORY_FILE  = os.path.join(_SCRIPT_DIR, 'T5_memory.json')

def _load_memory():
    try:
        if os.path.exists(_MEMORY_FILE):
            with open(_MEMORY_FILE, 'r') as f:
                data = json.load(f)
            return data
    except Exception:
        pass
    return {}

def _save_memory(mother_baseline):
    try:
        data = {
            'mother_baseline': float(mother_baseline),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(_MEMORY_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as ex:
        print(f'[T5] Memory save error: {ex}')
        return False

BG   = '#f4f6fb'
PNL  = '#ffffff'
PNL2 = '#eef1f8'
ACC  = '#2563eb'
FG   = '#1e293b'
DIM  = '#64748b'
BRD  = '#cbd5e1'
SEP  = '#e2e8f0'

C_AIR  = '#059669'
C_UP   = '#d97706'
C_DN   = '#dc2626'
C_REC  = '#7c3aed'
C_RAW  = '#3b82f6'
C_LEA  = '#10b981'
C_BAS  = '#ef4444'
C_CONC = '#db2777'
C_OR   = '#dc2626'
C_STB  = '#16a34a'
C_MOTHER = '#f59e0b'

BASELINE_WARMUP_SAMPLES = 25
KEEP_WINDOW             = 4000
LIVE_MAX_SAMPLES        = 120000

MIN_MV_SPAN  = 5.0
MIN_PPM_SPAN = 20.0

WARMUP_SD_THRESH = 0.3
WARMUP_PROX_MV   = 30.0

DEFAULT_PARAMS = {
    'jmp'      : 0.0,
    'alp'      : 1.0,
    'upG'      : 6.0,
    'inG'      : 0.1,
    'dnG'      : 6.0,
    'dnI'      : -0.1,
    'rec'      : 0.8,
    'drf'      : 20.0,
    'n_thresh': 0.001,
    'n_thresh_low'       : 0.002,  # n_thresh used when ppm < n_thresh_ppm_thresh
    'n_thresh_ppm_thresh': 1000.0,  # ppm — if current ppm < this, use n_thresh_low; else use n_thresh
    'o_cap'    : 30,
    'ramp_up' : [(-100, 0.0001), (40, 0.1), (200, 0.1), (400, 0.1)],
    'ramp_dn' : [(-100, -1e-5),  (40, -0.1), (200, -0.2), (400, -1.0)],
    'stab_rec': [(0, 1), (1e-5, 1), (0.001, 1), (0.01, 0.9),
                 (0.1, 0.85), (0.25, 0.67), (0.5, 0.5), (0.8, 0.25)],
    # calib tables: (emf_mV, ppm, band_mV)
    # band = +/- tolerance; if EMF within [emf-band, emf+band] -> snap to ppm
    # band=0 rows are pure interpolation breakpoints (same as old behaviour)
    'calib'   : [(0.0,     0,      0),
                 (0.15,    5,      0),
                 (0.4,     10,     0),
                 (8.40975, 100,    1.5),
                 (100.4988,1000,   12),
                 (309.699, 5000,   10),
                 (411.5075,10000,  15),
                 (493.2528,20000,  17),
                 (720.0,   100000, 0)],
    'calib_analytical': [
        (0.0,     0,      0),
        (0.9,     5,      0),
        (1.4,     10,     0),
        (44.786,  100,    10),
        (151.6863,1000,   7),
        (314.3765,5000,   7),
        (415.4543,10000,  19),
        (499.0271,20000,  14),
        (820.0,   100000, 0)
    ],
    'rec_zero_pct'        : 0.05,
    'warmup_samples'      : BASELINE_WARMUP_SAMPLES,
    'or_thresh'           : 720.0,
    'or_exit_mv'          : 20.0,
    'or_sd_stable'        : 0.000020,
    'daughter_mother_prox': 2.0,
    # Post-high-concentration limiting
    'post_high_conc_thresh'  : 8000.0,   # ppm threshold that triggers limiting
    'post_high_counter_limit': 3000,       # samples to count before resuming normal
    'post_high_upG'          : 10.0,       # upG override during limiting
    'post_high_inG'          : 0.2,        # inG override during limiting
}

def vlu(v, tbl):
    r = tbl[0][1]
    for k, val in tbl:
        if v >= k: r = val
        else: break
    return r

def vlu_sd(v, tbl):
    r = tbl[0][1]
    for k, val in tbl:
        if v >= k: r = val
    return r

def calib_interp(p_val, tbl):
    """
    Band-aware calibration interpolation.

    tbl rows are either:
      (emf, ppm)          — legacy 2-tuple, band = 0
      (emf, ppm, band)    — new 3-tuple

    Logic:
      1. If p_val <= first emf − band  → return first ppm (clamp low)
      2. If p_val >= last  emf + band  → return last  ppm (clamp high)
      3. Walk rows: if p_val falls within [emf − band, emf + band] → snap to ppm
      4. Otherwise find the gap between row i upper-edge and row i+1 lower-edge
         and interpolate linearly between (upper_edge_i, ppm_i) and
         (lower_edge_{i+1}, ppm_{i+1}).
    """
    def _unpack(row):
        if len(row) == 3:
            return float(row[0]), float(row[1]), float(row[2])
        return float(row[0]), float(row[1]), 0.0

    emf0, ppm0, band0 = _unpack(tbl[0])
    emfN, ppmN, bandN = _unpack(tbl[-1])

    # Clamp at boundaries (use band edges)
    if p_val <= emf0 - band0:
        return float(ppm0)
    if p_val >= emfN + bandN:
        return float(ppmN)

    # Check every row's band first
    for row in tbl:
        emf, ppm, band = _unpack(row)
        if (emf - band) <= p_val <= (emf + band):
            return float(ppm)

    # Not in any band — interpolate between adjacent band edges
    for i in range(len(tbl) - 1):
        emf_lo, ppm_lo, band_lo = _unpack(tbl[i])
        emf_hi, ppm_hi, band_hi = _unpack(tbl[i + 1])
        seg_lo = emf_lo + band_lo   # upper edge of lower band
        seg_hi = emf_hi - band_hi   # lower edge of upper band
        if seg_lo <= p_val <= seg_hi:
            span = seg_hi - seg_lo
            if span <= 0:
                return float(ppm_lo)
            t = (p_val - seg_lo) / span
            return round(ppm_lo + t * (ppm_hi - ppm_lo))

    return float(ppmN)

_LOG_RE = re.compile(r'^\s*[+-]?\d+(?:\.\d+)?[\s\t]+([+-]?\d+(?:\.\d+)?)')

def parse_log_emf(line):
    line = line.strip().replace('\r', '').replace('\x00', '')
    m = _LOG_RE.match(line)
    if m:
        try: return float(m.group(1))
        except: pass
    return None

def _fast_std(lst, end_idx, win):
    start = max(0, end_idx - win)
    n = end_idx - start
    if n < 2:
        return 0.0
    s = s2 = 0.0
    for i in range(start, end_idx):
        v = lst[i]
        s += v
        s2 += v * v
    mean = s / n
    var = s2 / n - mean * mean
    return var ** 0.5 if var > 0 else 0.0

def _stdrange(lst, a, b):
    """Two-pass population std of lst[a:b] — numerically equivalent to np.std (ddof=0),
    but without per-call array allocation. Used in the compute_all hot loop."""
    n = b - a
    if n < 1:
        return 0.0
    s = 0.0
    for k in range(a, b):
        s += lst[k]
    mean = s / n
    v = 0.0
    for k in range(a, b):
        d = lst[k] - mean
        v += d * d
    var = v / n
    return var ** 0.5 if var > 0.0 else 0.0


def _make_calib(tbl):
    """Pre-unpack a calibration table once and return a fast interpolation closure.
    Behaviour is identical to calib_interp(value, tbl) for every input."""
    rows = []
    for row in tbl:
        if len(row) == 3:
            rows.append((float(row[0]), float(row[1]), float(row[2])))
        else:
            rows.append((float(row[0]), float(row[1]), 0.0))
    emf0, ppm0, band0 = rows[0]
    emfN, ppmN, bandN = rows[-1]
    lo_clamp = emf0 - band0
    hi_clamp = emfN + bandN
    m = len(rows)

    def interp(p_val):
        if p_val <= lo_clamp:
            return float(ppm0)
        if p_val >= hi_clamp:
            return float(ppmN)
        for emf_, ppm_, band_ in rows:
            if (emf_ - band_) <= p_val <= (emf_ + band_):
                return float(ppm_)
        for i in range(m - 1):
            emf_lo, ppm_lo, band_lo = rows[i]
            emf_hi, ppm_hi, band_hi = rows[i + 1]
            seg_lo = emf_lo + band_lo
            seg_hi = emf_hi - band_hi
            if seg_lo <= p_val <= seg_hi:
                span = seg_hi - seg_lo
                if span <= 0:
                    return float(ppm_lo)
                t = (p_val - seg_lo) / span
                return round(ppm_lo + t * (ppm_hi - ppm_lo))
        return float(ppmN)

    return interp


def compute_all(emf, p, seed_baseline=None, prev_mb=None, ignore_prox=False):
    n = len(emf)
    warmup = int(p.get('warmup_samples', BASELINE_WARMUP_SAMPLES))
    prox_mv = float(p.get('daughter_mother_prox', 2.0))

    # Plain-Python working buffers (scalar list access is far faster than
    # per-element NumPy indexing in this sequential loop). Converted back to
    # NumPy arrays with the original dtypes just before returning.
    _z = 0.0
    C  = [_z]*n;  II = [_z]*n
    J  = [_z]*n;  K  = [_z]*n
    L  = [_z]*n;  MB = [_z]*n
    M  = [_z]*n
    D  = [0]*n;   E  = [_z]*n
    FF = [0]*n;   G  = [_z]*n
    H  = [_z]*n
    N_ = [_z]*n;  O_ = [0]*n
    Pv = [_z]*n;  Q_ = [_z]*n
    RC = [_z]*n
    R_ = [_z]*n
    S_ = [_z]*n
    OR_STATE = [None]*n
    WARMUP_PHASE = [None]*n

    jmp=p['jmp']; alp=p['alp']; upG=p['upG']; inG=p['inG']
    dnG=p['dnG']; dnI=p['dnI']; rec=p['rec']; drf=p['drf']
    nth_normal=float(p['n_thresh']); nth_low=float(p.get('n_thresh_low',0.0033))
    nth_ppm_thresh=float(p.get('n_thresh_ppm_thresh',1000.0))
    # nth is selected per-sample using previous sample's ppm (S_[i-1]),
    # same approach as post-high counter which uses last['S'].
    ocap=int(p['o_cap'])
    ru=p['ramp_up']; rd=p['ramp_dn']; sr=p['stab_rec']; cb=p['calib']
    cb_an = p.get('calib_analytical', p['calib'])
    rzp=p.get('rec_zero_pct', 0.05)
    or_thr  = float(p.get('or_thresh',   720.0))
    or_exit = float(p.get('or_exit_mv',   20.0))
    or_sd   = float(p.get('or_sd_stable', 0.000020))

    # Pre-build calibration interpolators once (instead of re-unpacking the
    # table on every sample) and read emf as plain floats for fast indexing.
    interp_cb = _make_calib(cb)
    interp_an = _make_calib(cb_an)
    emf = [float(x) for x in emf]

    if seed_baseline is not None:
        daughter_baseline = float(seed_baseline)
        mother_baseline   = float(seed_baseline)
        baseline_seeded   = True
        WARMUP_PHASE[0]   = 'running'
        auto_seeded       = False
    else:
        daughter_baseline = 0.0
        mother_baseline   = 0.0
        baseline_seeded   = False
        WARMUP_PHASE[0]   = 'waiting'
        auto_seeded       = False

    C[0]  = emf[0]; II[0] = -1.0; K[0] = 0.0; J[0] = 0.0
    if baseline_seeded:
        L[0]  = daughter_baseline
        MB[0] = mother_baseline
    else:
        L[0]  = emf[0]; MB[0] = emf[0]
    M[0]  = emf[0] - L[0]; OR_STATE[0] = 'normal'
    RC[0] = 100.0
    peak_m = 0.0; or_state = 'normal'; or_seen_overrange = False

    for i in range(1, n):
        e  = emf[i]; cp = C[i-1]
        C[i] = e if abs(e - cp) > jmp else (e - cp) * alp + cp

        if or_state == 'normal':
            if e > or_thr:
                or_state = 'overrange'; or_seen_overrange = True
        elif or_state == 'overrange':
            if e < or_exit: or_state = 'waiting_drop'
        elif or_state == 'waiting_drop':
            if e > or_thr:
                or_state = 'overrange'; or_seen_overrange = True
            elif e < or_exit:
                sd_win = _stdrange(C, max(0, i-5), i+1)
                if sd_win < or_sd and or_seen_overrange:
                    or_state = 'stable'
        elif or_state == 'stable':
            if e > or_thr:
                or_state = 'overrange'; or_seen_overrange = True
        OR_STATE[i] = or_state
        in_or = (or_state in ('overrange', 'waiting_drop', 'stable'))

        if not baseline_seeded and not in_or and i >= warmup:
            sd_now = _stdrange(C, max(0, i - warmup + 1), i + 1)
            if sd_now < WARMUP_SD_THRESH:
                _a0 = i - warmup + 1
                _ssum = 0.0
                for _kk in range(_a0, i + 1):
                    _ssum += C[_kk]
                initial_val = _ssum / warmup
                if not ignore_prox and prev_mb is not None and abs(initial_val - prev_mb) > WARMUP_PROX_MV:
                    WARMUP_PHASE[i] = 'sd_ok_proxfail'
                else:
                    daughter_baseline = initial_val
                    mother_baseline   = initial_val
                    L[i-1]  = daughter_baseline
                    MB[i-1] = mother_baseline
                    baseline_seeded   = True
                    auto_seeded       = True
                    WARMUP_PHASE[i]   = 'ready_for_tare'
            else:
                WARMUP_PHASE[i] = 'waiting'
        elif baseline_seeded:
            if auto_seeded:
                WARMUP_PHASE[i] = 'ready_for_tare'
            else:
                WARMUP_PHASE[i] = 'running'
        else:
            WARMUP_PHASE[i] = 'waiting'

        in_warmup_phase = (WARMUP_PHASE[i] != 'running')

        if in_or or i < 7 or in_warmup_phase:
            II[i] = II[i-1]; D[i]=0; E[i]=0; FF[i]=0; G[i]=0; H[i]=0
            J[i] = _stdrange(C, max(0, i-5), i+1)
            K[i]=0.0;
            L[i]  = daughter_baseline if baseline_seeded else L[i-1]
            MB[i] = mother_baseline if baseline_seeded else MB[i-1]
            M[i]  = C[i]-L[i]
            N_[i]=0.0; O_[i]=0; Pv[i]=0.0; Q_[i]=0.0; RC[i]=100.0
            R_[i]=0.0; S_[i]=0.0
            continue

        c=C[i]; c6=C[i-6]; cp1=C[i-1]
        D[i]  = D[i-1]+1  if (c-cp1) > vlu(c,ru) else 0
        E[i]  = E[i-1]+(c-c6) if D[i]>0 else 0
        FF[i] = FF[i-1]+1 if (c-c6) < vlu(c,rd) else 0
        G[i]  = G[i-1]+(c-c6) if FF[i]>0 else 0
        h = (1 if D[i]>upG and E[i]>inG else 0)+(-1 if FF[i]>dnG and G[i]<dnI else 0)
        H[i]=h; II[i] = II[i-1] if h==0 else float(h)
        J[i] = _stdrange(C, i-5, i+1)
        K[i] = 0.0 if (II[i]==1.0) else vlu_sd(J[i],sr)

        c_now=C[i]
        if c_now < mother_baseline:
            mother_baseline=c_now; l=c_now
        else:
            if K[i]>=rec and abs(c_now-mother_baseline)<drf: l=c_now
            else: l=L[i-1]
        mb=mother_baseline
        if abs(l-mother_baseline)<=prox_mv:
            mother_baseline=l; mb=mother_baseline

        daughter_baseline=l; L[i]=l; MB[i]=mb; M[i]=C[i]-L[i]

        # Select nth based on previous sample's ppm — same logic as post-high counter.
        # S_[i-1] is 0.0 at i==1 (first active sample), so nth_low is always the start.
        prev_ppm = S_[i-1] if i > 0 else 0.0
        nth = nth_low if prev_ppm < nth_ppm_thresh else nth_normal

        prev_ii=II[i-1]
        if II[i]==-1.0 and prev_ii==1.0: peak_m=abs(M[i-1])
        if II[i]==1.0 and prev_ii==-1.0: N_[i]=M[i]
        elif II[i]==1.0:
            delta=M[i]-M[i-1]
            N_[i]=M[i] if (M[i]>0 and delta>nth*M[i]) else N_[i-1]
        else: N_[i]=0.0

        if II[i]>0: O_[i]=ocap if O_[i-1]==ocap else O_[i-1]+1
        else:       O_[i]=0

        if O_[i] == 0:
            Pv[i] = 0.0
        elif O_[i] == O_[i-1]:
            Pv[i] = Pv[i-1]
        else:
            Pv[i] = N_[i]

        Q_[i] = interp_cb(Pv[i])
        R_[i] = interp_an(N_[i])
        S_[i] = max(Q_[i], R_[i])

        if II[i]==-1.0 and peak_m>0:
            abs_m=abs(M[i])
            RC[i]=100.0 if abs_m<rzp*peak_m else max(0.0,min(99.9,(1.0-abs_m/peak_m)*100.0))
        elif II[i]==1.0: RC[i]=0.0
        else:            RC[i]=RC[i-1]

    # Convert working buffers back to NumPy arrays with the original dtypes so
    # all downstream consumers behave exactly as before.
    C  = np.array(C,  dtype=float); II = np.array(II, dtype=float)
    J  = np.array(J,  dtype=float); K  = np.array(K,  dtype=float)
    L  = np.array(L,  dtype=float); MB = np.array(MB, dtype=float)
    M  = np.array(M,  dtype=float)
    D  = np.array(D,  dtype=int);   E  = np.array(E,  dtype=float)
    FF = np.array(FF, dtype=int);   G  = np.array(G,  dtype=float)
    H  = np.array(H,  dtype=float)
    N_ = np.array(N_, dtype=float); O_ = np.array(O_, dtype=int)
    Pv = np.array(Pv, dtype=float); Q_ = np.array(Q_, dtype=float)
    RC = np.array(RC, dtype=float)
    R_ = np.array(R_, dtype=float); S_ = np.array(S_, dtype=float)
    OR_STATE = np.array(OR_STATE, dtype=object)
    WARMUP_PHASE = np.array(WARMUP_PHASE, dtype=object)

    return C, D, E, FF, G, H, II, J, K, L, MB, M, N_, O_, Pv, Q_, RC, OR_STATE, WARMUP_PHASE, R_, S_


def load_csv(path):
    with open(path, 'rb') as f: raw = f.read()
    txt   = raw.decode('utf-8', errors='replace').replace('\ufeff','').replace('\r','')
    lines = txt.strip().split('\n')
    hdr   = [h.strip().lower().replace('"','').replace("'",'') for h in lines[0].split(',')]
    if 'time_sec' not in hdr or 'emf_mv' not in hdr:
        raise ValueError(f"Need time_sec & emf_mv columns.\nFound: {hdr}")
    ti=hdr.index('time_sec'); ei=hdr.index('emf_mv')
    rows=[]
    for ln in lines[1:]:
        ln=ln.strip()
        if not ln: continue
        parts=[v.strip().strip('"').strip("'") for v in ln.split(',')]
        try: rows.append((float(parts[ti]),float(parts[ei])))
        except: pass
    if not rows: raise ValueError("No valid data found.")
    return rows


class LiveState:
    MAX = LIVE_MAX_SAMPLES
    def __init__(self):
        self._lock=threading.Lock(); self._emf=[]; self._new=0; self._stop=False
    def push(self,v):
        with self._lock:
            if len(self._emf)>=self.MAX: self._emf.pop(0)
            self._emf.append(v); self._new+=1
    def consume(self):
        with self._lock: n=self._new; self._new=0; return list(self._emf),n
    def stop(self):
        with self._lock: self._stop=True
    def should_stop(self):
        with self._lock: return self._stop
    def reset(self):
        with self._lock: self._emf=[]; self._new=0; self._stop=False

    def trim_to_last(self):
        """Discard all but the final sample after a TARE.

        _live_poll uses  start = len(self._ic.emf)  as a read cursor into
        self._emf.  When _full_reset_state flushes self._ic.emf to 1 element,
        start resets to 1, so the next poll replays emf_list[1:] — the entire
        pre-TARE history including any old overrange — causing instant STABLE
        prompts in a loop.  Truncating the shared buffer here keeps cursor and
        buffer in sync: only the single post-TARE sample remains.
        """
        with self._lock:
            if self._emf:
                self._emf = [self._emf[-1]]
            self._new = 0


class IncrementalCompute:
    PRUNE_EVERY = 1000
    KEEP_FULL   = 200

    def __init__(self, p, prev_mb=None, ignore_prox=False):
        self.p=p; self.i=0; self._peak_m=0.0
        self._baseline_seeded=False
        self._daughter_baseline=0.0
        self._mother_baseline=0.0
        self.prev_mb = prev_mb
        self._ignore_prox = ignore_prox
        self.emf=[]; self.C=[]; self.II=[]
        self.D=[]; self.E=[]; self.FF=[]; self.G=[]
        self.H=[]; self.J=[]; self.K=[]
        self.L=[]; self.MB=[]
        self.M=[]; self.N=[]; self.O=[]; self.P=[]; self.Q=[]; self.REC=[]
        self.R=[]; self.S=[]
        self.OR_STATE=[]
        self.WARMUP_PHASE=[]
        self._disp_offset=0
        self._or_state='normal'
        self._or_seen_overrange = False  # ← V2.9.9k: True only after EMF genuinely > or_thresh
        self._or_armed = False           # Must NOT be armed at init; only real >or_thr arms it
        self._or_high_count = 0          # Debounce counter: consecutive samples above or_thr
        self._or_high_req   = 3          # Minimum consecutive high samples required to arm
        self._tare_count        = 0      # Incremented on every TARE
        self._tare_count_at_or  = 0      # Snapshot of _tare_count when OR was last entered
        self._or_debug_suppress = False  # True during _on_params replay to silence prints
        self._force_recovered=False
        self._warmup_phase = 'waiting'
        self._warmup_sd_ok = False
        self._warmup_prox_ok = False
        self._warmup_seed_val = None
        self._tare_blank_count = 0   # ← V2.9.9f: blanks N/P/O/Q/R/S after tare

    def _full_reset_state(self, new_base):
        self._daughter_baseline = new_base
        self._mother_baseline   = new_base
        self._baseline_seeded   = True
        self._peak_m            = 0.0
        self._force_recovered   = True
        self._warmup_phase      = 'running'
        self._warmup_sd_ok      = False
        self._warmup_prox_ok    = False
        self._warmup_seed_val   = None
        self._tare_blank_count  = 60   # ← V2.9.9k: 60-sample blank (4.5 s)

        # ── Flush C and emf buffers on TARE ───────────────────────────────────
        # The log reader pre-loads all existing file lines before TARE is pressed,
        # filling self.C with thousands of pre-TARE samples.  _tare_fence_idx was
        # meant to block these but _prune() trims C from the front, making the
        # absolute fence index invalid and allowing old samples back into the SD
        # window → spurious WAIT_DROP->STABLE.  Physical truncation is the only
        # reliable fix: keep only the single most-recent sample so _fast_std has
        # zero pre-TARE history regardless of pruning or buffer length.
        if self.C:    self.C    = [self.C[-1]]
        if self.emf:  self.emf  = [self.emf[-1]]

        def _set_last(lst, val):
            if lst: lst[-1] = val

        _set_last(self.D,   0)
        _set_last(self.E,   0.0)
        _set_last(self.FF,  0)
        _set_last(self.G,   0.0)
        _set_last(self.H,   0)
        _set_last(self.II,  -1.0)
        _set_last(self.N,   0.0)   # ← zero accumulator
        _set_last(self.O,   0)     # ← zero ROC
        _set_last(self.P,   0.0)   # ← zero clip P
        _set_last(self.Q,   0.0)   # ← zero ppm Fast
        _set_last(self.R,   0.0)   # ← zero ppm Analytical
        _set_last(self.S,   0.0)   # ← zero ppm Display
        _set_last(self.REC, 100.0)
        _set_last(self.L,   new_base)
        _set_last(self.MB,  new_base)
        _set_last(self.M,   0.0)
        _set_last(self.OR_STATE, 'normal')
        self._or_state          = 'normal'
        self._or_seen_overrange = False
        self._or_armed          = False   # Disarm; only a real >or_thr spike may re-arm
        self._or_high_count     = 0       # Reset debounce counter on TARE
        self._tare_count       += 1       # Track that a TARE occurred (used in step() guard)
        _set_last(self.WARMUP_PHASE, 'running')
        t_now = self.i * 0.200
        if not self._or_debug_suppress: print(f'[OR LIVE t={t_now:.1f}s] TARE -> OR reset  base={new_base:.3f}mV')

    def do_calibrate(self):
        if not self.C: return False
        self._full_reset_state(self.C[-1])
        return True

    def do_manual_tear(self):
        if not self.C: return False
        self._full_reset_state(self.C[-1])
        return True

    def _prune(self):
        keep=KEEP_WINDOW+self.KEEP_FULL
        if len(self.emf)>keep*2:
            trim=len(self.emf)-keep
            self.emf=self.emf[trim:]; self.C=self.C[trim:]; self.II=self.II[trim:]

    def _disp_append(self,lst,val):
        lst.append(val)
        n=len(lst)
        if n>KEEP_WINDOW+512:
            k=n-KEEP_WINDOW
            del lst[:k]; self._disp_offset+=k

    def step(self, emf_val):
        p=self.p; i=self.i; self.emf.append(emf_val)
        jmp=p['jmp']; alp=p['alp']; upG=p['upG']; inG=p['inG']
        dnG=p['dnG']; dnI=p['dnI']; rec=p['rec']; drf=p['drf']
        nth_normal=p['n_thresh']; nth_low=float(p.get('n_thresh_low',0.0033))
        nth_ppm_thresh=float(p.get('n_thresh_ppm_thresh',1000.0))
        # nth chosen using previous sample's ppm (self.S[-1]) — same as post-high counter
        ocap=int(p['o_cap'])
        rzp=p.get('rec_zero_pct',0.05)
        cb_an = p.get('calib_analytical', p['calib'])
        warmup=int(p.get('warmup_samples',BASELINE_WARMUP_SAMPLES))
        or_thr=float(p.get('or_thresh',720.0))
        or_exit=float(p.get('or_exit_mv',20.0))
        or_sd=float(p.get('or_sd_stable',0.000020))
        prox_mv=float(p.get('daughter_mother_prox',2.0))

        if i==0:
            self.C.append(emf_val); self.II.append(-1.0)
            init_l=self._daughter_baseline if self._baseline_seeded else emf_val
            self._disp_append(self.K,0.0); self._disp_append(self.L,init_l)
            self._disp_append(self.MB,init_l)
            self._disp_append(self.M,emf_val-init_l); self._disp_append(self.J,0.0)
            for lst in (self.D,self.E,self.FF,self.G,self.H,self.N,self.O):
                self._disp_append(lst,0)
            self._disp_append(self.P,0.0); self._disp_append(self.Q,0.0)
            self._disp_append(self.R,0.0); self._disp_append(self.S,0.0)
            self._disp_append(self.REC,100.0)
            self._disp_append(self.OR_STATE,self._or_state)
            self._disp_append(self.WARMUP_PHASE, self._warmup_phase)
            self.i+=1; return

        cp=self.C[-1]
        c=emf_val if abs(emf_val-cp)>jmp else (emf_val-cp)*alp+cp
        self.C.append(c)

        t_now = self.i * 0.200
        dbg = not self._or_debug_suppress

        # ── Fix 5: Force exit OR if a TARE happened while inside OR states ────
        if self._or_state in ('overrange', 'waiting_drop', 'stable'):
            if self._tare_count_at_or != self._tare_count:
                self._or_state          = 'normal'
                self._or_seen_overrange = False
                self._or_armed          = False
                self._or_high_count     = 0
                if dbg: print(f'[OR LIVE t={t_now:.1f}s] TARE-during-OR -> forced NORMAL')

        # ── Fix 2: Debounced arming — only consecutive high samples arm OR ─────
        # _or_armed stays False after TARE until or_high_req samples exceed or_thr.
        if emf_val > or_thr:
            self._or_high_count += 1
            if self._or_high_count >= self._or_high_req:
                self._or_armed = True
        else:
            self._or_high_count = 0   # reset streak; noise/single spike won't re-arm

        # ── Fix 4: In normal state, clear seen flag (prevents stale latch) ────
        if self._or_state == 'normal':
            self._or_seen_overrange = False
            if emf_val > or_thr and self._or_armed:
                self._or_state          = 'overrange'
                self._or_seen_overrange = True
                self._tare_count_at_or  = self._tare_count   # snapshot for Fix 5
                if dbg: print(f'[OR LIVE t={t_now:.1f}s] NORMAL->OVERRANGE  emf={emf_val:.3f}  or_thr={or_thr:.3f}  seen={self._or_seen_overrange}')
        elif self._or_state == 'overrange':
            if emf_val < or_exit:
                self._or_state = 'waiting_drop'
                if dbg: print(f'[OR LIVE t={t_now:.1f}s] OVERRANGE->WAIT_DROP  emf={emf_val:.3f}  or_exit={or_exit:.3f}')
        elif self._or_state == 'waiting_drop':
            # ── Fix 4: Hard block — if not armed, cannot proceed to stable ────
            if not self._or_armed:
                pass   # block all transitions
            elif emf_val > or_thr:
                self._or_state          = 'overrange'
                self._or_seen_overrange = True
                self._tare_count_at_or  = self._tare_count
                if dbg: print(f'[OR LIVE t={t_now:.1f}s] WAIT_DROP->OVERRANGE  emf={emf_val:.3f}  or_thr={or_thr:.3f}')
            elif emf_val < or_exit:
                c_len  = len(self.C)
                # C buffer is flushed to 1 sample on TARE, so _fast_std over the
                # last 6 entries can only ever use post-TARE data here.
                sd_win = _fast_std(self.C, c_len, 6)
                if dbg and self.i % 133 == 0:
                    print(f'[OR LIVE t={t_now:.1f}s] WAIT_DROP  emf={emf_val:.3f}  sd={sd_win:.6f}  or_sd={or_sd:.6f}  seen={self._or_seen_overrange}  armed={self._or_armed}')
                # ── Fix 3: Strict stable transition — must have real overrange AND be armed ──
                if sd_win < or_sd and self._or_seen_overrange and self._or_armed:
                    self._or_state = 'stable'
                    if dbg: print(f'[OR LIVE t={t_now:.1f}s] WAIT_DROP->STABLE  sd={sd_win:.6f} < or_sd={or_sd:.6f}')
        elif self._or_state == 'stable':
            if emf_val > or_thr:
                self._or_state          = 'overrange'
                self._or_seen_overrange = True
                self._tare_count_at_or  = self._tare_count
                if dbg: print(f'[OR LIVE t={t_now:.1f}s] STABLE->OVERRANGE  emf={emf_val:.3f}')

        in_or=(self._or_state in ('overrange','waiting_drop','stable'))
        self._disp_append(self.OR_STATE,self._or_state)

        if not self._baseline_seeded and not in_or:
            c_len = len(self.C)
            sd_now = _fast_std(self.C, c_len, warmup)

            if self._warmup_phase == 'waiting_for_instability':
                if sd_now >= WARMUP_SD_THRESH:
                    self._warmup_phase = 'waiting'

            elif self._warmup_phase == 'waiting':
                if i >= warmup and sd_now < WARMUP_SD_THRESH:
                    seed_val = sum(self.C[-warmup:]) / warmup
                    self._warmup_seed_val = seed_val
                    if self._ignore_prox or self.prev_mb is None or abs(seed_val - self.prev_mb) <= WARMUP_PROX_MV:
                        self._daughter_baseline = seed_val
                        self._mother_baseline   = seed_val
                        self._baseline_seeded   = True
                        self._warmup_phase      = 'ready_for_tare'
                        if self.L:  self.L[-1]  = seed_val
                        if self.MB: self.MB[-1] = seed_val
                    else:
                        self._warmup_phase  = 'sd_ok_proxfail'

        self._disp_append(self.WARMUP_PHASE, self._warmup_phase)
        in_warmup_phase = (self._warmup_phase != 'running')

        if i<7 or in_or or in_warmup_phase:
            self.II.append(self.II[-1])
            for lst in (self.D,self.E,self.FF,self.G,self.H,self.N,self.O):
                self._disp_append(lst,0)
            j = _fast_std(self.C, len(self.C), 6)
            self._disp_append(self.J,j); self._disp_append(self.K,0.0)

            curr_l = self._daughter_baseline if self._baseline_seeded else (self.L[-1] if self.L else c)
            curr_mb = self._mother_baseline if self._baseline_seeded else (self.MB[-1] if self.MB else c)

            self._disp_append(self.L,curr_l)
            self._disp_append(self.MB,curr_mb)
            self._disp_append(self.M,c-curr_l)
            self._disp_append(self.P,0.0); self._disp_append(self.Q,0.0)
            self._disp_append(self.R,0.0); self._disp_append(self.S,0.0)
            self._disp_append(self.REC,100.0); self.i+=1; return

        c_len = len(self.C)
        c6=self.C[max(0, c_len-7)]
        cp1=self.C[c_len-2]
        d=self.D[-1]+1 if (c-cp1)>vlu(c,p['ramp_up']) else 0
        e=self.E[-1]+(c-c6) if d>0 else 0
        ff=self.FF[-1]+1 if (c-c6)<vlu(c,p['ramp_dn']) else 0
        g=self.G[-1]+(c-c6) if ff>0 else 0
        h=(1 if d>upG and e>inG else 0)+(-1 if ff>dnG and g<dnI else 0)
        prev_ii=self.II[-1]; ii=float(prev_ii) if h==0 else float(h)
        self.II.append(ii)
        j = _fast_std(self.C, c_len, 6)
        k=0.0 if (ii==1.0) else vlu_sd(j,p['stab_rec'])

        c_now=c
        if c_now<self._mother_baseline:
            self._mother_baseline=c_now; l=c_now
        else:
            if k>=rec and abs(c_now-self._mother_baseline)<drf: l=c_now
            else: l=self.L[-1]
        mb=self._mother_baseline
        if abs(l-self._mother_baseline)<=prox_mv:
            self._mother_baseline=l; mb=self._mother_baseline

        self._daughter_baseline=l; m=c-l

        # Select nth using previous sample's ppm — same logic as post-high counter.
        prev_ppm = self.S[-1] if self.S else 0.0
        nth = nth_low if prev_ppm < nth_ppm_thresh else nth_normal

        if ii==1.0 and prev_ii==-1.0:
            n_val=m
        elif ii==1.0:
            delta=m-self.M[-1]
            n_val=m if (m>0 and delta>nth*m) else self.N[-1]
        else:
            n_val=0.0

        o_prev=self.O[-1]
        o_val=(ocap if o_prev==ocap else o_prev+1) if ii>0 else 0

        if o_val == 0:
            pv = 0.0
        elif o_val == o_prev:
            pv = self.P[-1]
        else:
            pv = n_val

        q_val = calib_interp(pv, p['calib'])
        r_val = calib_interp(n_val, cb_an)
        s_val = max(q_val, r_val)

        if self._tare_blank_count > 0:
            self._tare_blank_count -= 1
            n_val = 0.0
            o_val = 0
            pv    = 0.0
            q_val = 0.0
            r_val = 0.0
            s_val = 0.0

        if self._force_recovered:
            rv = 100.0
            self._force_recovered = False
            self._peak_m = 0.0
        elif ii==-1.0 and prev_ii==1.0:
            self._peak_m=abs(self.M[-1]); rv=100.0
        elif ii==-1.0 and self._peak_m>0:
            abs_m=abs(m)
            rv=100.0 if abs_m<rzp*self._peak_m else max(0.0,min(99.9,(1.0-abs_m/self._peak_m)*100.0))
        elif ii==1.0:
            rv=0.0
        else:
            rv=self.REC[-1]

        self._disp_append(self.D,d); self._disp_append(self.E,e)
        self._disp_append(self.FF,ff); self._disp_append(self.G,g)
        self._disp_append(self.H,h); self._disp_append(self.J,j)
        self._disp_append(self.K,k); self._disp_append(self.L,l)
        self._disp_append(self.MB,mb); self._disp_append(self.M,m)
        self._disp_append(self.N,n_val); self._disp_append(self.O,o_val)
        self._disp_append(self.P,pv); self._disp_append(self.Q,q_val)
        self._disp_append(self.R,r_val); self._disp_append(self.S,s_val)
        self._disp_append(self.REC,rv); self.i+=1
        if self.i%self.PRUNE_EVERY==0: self._prune()

    def last(self):
        if not self.C: return None
        return dict(
            C=self.C[-1], D=self.D[-1] if self.D else 0,
            E=self.E[-1] if self.E else 0, FF=self.FF[-1] if self.FF else 0,
            G=self.G[-1] if self.G else 0, H=self.H[-1] if self.H else 0,
            II=self.II[-1], J=self.J[-1] if self.J else 0,
            M=self.M[-1] if self.M else 0, N=self.N[-1] if self.N else 0,
            O=self.O[-1] if self.O else 0, P=self.P[-1] if self.P else 0,
            Q=self.Q[-1] if self.Q else 0,
            R=self.R[-1] if self.R else 0,
            S=self.S[-1] if self.S else 0, REC=self.REC[-1] if self.REC else 100.0,
            OR_STATE=self.OR_STATE[-1] if self.OR_STATE else 'normal',
            mother_baseline=self.MB[-1] if self.MB else 0.0,
            daughter_baseline=self.L[-1] if self.L else 0.0,
            warmup_phase=self.WARMUP_PHASE[-1] if self.WARMUP_PHASE else 'waiting',
        )

class CanvasChart:
    MAX_DRAW_PTS = 600
    PAD_L = 52
    PAD_R = 42
    PAD_T = 22
    PAD_B = 18
    LEGEND_H = 14
    NUM_GRID = 4

    def __init__(self, parent):
        self._frame = tk.Frame(parent, bg=BG)
        self._frame.pack(fill='both', expand=True)

        leg_f = tk.Frame(self._frame, bg=PNL, height=20)
        leg_f.pack(fill='x', side='top')
        tk.Frame(self._frame, bg=BRD, height=1).pack(fill='x', side='top')

        self._cv1 = tk.Canvas(self._frame, bg='#f8fafc', highlightthickness=0)
        self._cv1.pack(fill='both', expand=True)
        tk.Frame(self._frame, bg=SEP, height=2).pack(fill='x')
        self._cv2 = tk.Canvas(self._frame, bg='#f8fafc', highlightthickness=0)
        self._cv2.pack(fill='both', expand=True)

        leg_items1 = [
            ('Raw EMF', C_RAW), ('Leaky C', C_LEA),
            ('Daughter BL', C_BAS), ('Mother BL', C_MOTHER), ('OR thresh', C_OR),
        ]
        leg_items2 = [
            ('ppm Q', C_CONC), ('P clip', C_UP), ('N accum', C_RAW), ('Rec %', C_REC),
        ]
        x = 8
        for name, col in leg_items1 + leg_items2:
            tk.Label(leg_f, text='—', bg=PNL, fg=col,
                     font=('Segoe UI', 8, 'bold')).pack(side='left', padx=(x,0)); x=0
            tk.Label(leg_f, text=name, bg=PNL, fg=DIM,
                     font=('Segoe UI', 7)).pack(side='left', padx=(1,6))

        self._w1 = self._h1 = self._w2 = self._h2 = 0
        self._cv1.bind('<Configure>', self._on_resize1)
        self._cv2.bind('<Configure>', self._on_resize2)
        self._data = None

    def _on_resize1(self, e): self._w1 = e.width; self._h1 = e.height
    def _on_resize2(self, e): self._w2 = e.width; self._h2 = e.height

    def _to_canvas_coords(self, data, w, h, ymin, ymax):
        n = len(data)
        if n < 2: return None
        pl = self.PAD_L; pr = self.PAD_R; pt = self.PAD_T; pb = self.PAD_B
        cw = w - pl - pr; ch = h - pt - pb
        if cw <= 0 or ch <= 0: return None
        span = ymax - ymin if ymax != ymin else 1.0
        pts = []
        for k, v in enumerate(data):
            x = pl + cw * k / (n - 1)
            y = pt + ch * (1.0 - (v - ymin) / span)
            pts.append(x); pts.append(y)
        return pts

    def _draw_grid(self, cv, w, h, ymin, ymax, col_axis, secondary_ymin=None, secondary_ymax=None):
        pl = self.PAD_L; pr = self.PAD_R; pt = self.PAD_T; pb = self.PAD_B
        cw = w - pl - pr; ch = h - pt - pb
        if cw <= 0 or ch <= 0: return
        for k in range(self.NUM_GRID + 1):
            frac = k / self.NUM_GRID
            y = pt + ch * frac
            cv.create_line(pl, y, w - pr, y, fill=SEP, width=1)
            val = ymax - (ymax - ymin) * frac
            fmt = f'{val:.0f}' if abs(val) >= 10 else f'{val:.2f}'
            cv.create_text(pl - 4, y, text=fmt, anchor='e', font=('Segoe UI', 7), fill=DIM)
        cv.create_text(8, h // 2, text=col_axis, anchor='center', angle=90, font=('Segoe UI', 7), fill=DIM)
        if secondary_ymin is not None and secondary_ymax is not None:
            for k in range(self.NUM_GRID + 1):
                frac = k / self.NUM_GRID
                y = pt + ch * frac
                val2 = secondary_ymax - (secondary_ymax - secondary_ymin) * frac
                cv.create_text(w - pr + 4, y, text=f'{val2:.0f}', anchor='w', font=('Segoe UI', 7), fill=C_REC)
            cv.create_text(w - 10, h // 2, text='Rec%', anchor='center', angle=270, font=('Segoe UI', 7), fill=C_REC)

    def _safe_range(self, arrays, min_span):
        vals = []
        for a in arrays:
            for v in a:
                if v is not None and v == v:
                    vals.append(v)
        if not vals: return -min_span / 2, min_span / 2
        lo = min(vals); hi = max(vals)
        if hi - lo < min_span:
            mid = (lo + hi) / 2
            lo = mid - min_span / 2; hi = mid + min_span / 2
        margin = (hi - lo) * 0.06
        return lo - margin, hi + margin

    def update(self, raw, C, L, MB, N, Pv, Q, RC, or_thr=720.0, or_state_arr=None):
        n = len(raw)
        if n < 2: return
        cap = self.MAX_DRAW_PTS
        if n > cap:
            step = n / cap
            idx = [int(i * step) for i in range(cap)]
            def ds(a): return [a[k] for k in idx]
            raw=ds(raw); C=ds(C); L=ds(L); MB=ds(MB)
            N=ds(N); Pv=ds(Pv); Q=ds(Q); RC=ds(RC)
            if or_state_arr is not None:
                or_state_arr = [or_state_arr[k] for k in idx]
        self._data = (raw, C, L, MB, N, Pv, Q, RC, or_thr, or_state_arr)
        self._redraw()

    def _redraw(self):
        if self._data is None: return
        raw, C, L, MB, N, Pv, Q, RC, or_thr, or_state_arr = self._data
        w1 = self._w1; h1 = self._h1; w2 = self._w2; h2 = self._h2
        if w1 < 10 or h1 < 10 or w2 < 10 or h2 < 10: return

        self._cv1.delete('all')
        ymin1, ymax1 = self._safe_range([raw, C, L, MB], MIN_MV_SPAN)
        or_y_frac = 1.0 - (or_thr - ymin1) / (ymax1 - ymin1)
        self._draw_grid(self._cv1, w1, h1, ymin1, ymax1, 'mV')

        def draw_line(cv, data, color, width=1, dash=None):
            pts = self._to_canvas_coords(data, w1, h1, ymin1, ymax1)
            if pts and len(pts) >= 4:
                kw = dict(fill=color, width=width, smooth=False, tags='line')
                if dash: kw['dash'] = dash
                cv.create_line(*pts, **kw)

        pt_t = self.PAD_T; cw1 = w1 - self.PAD_L - self.PAD_R
        ch1 = h1 - pt_t - self.PAD_B

        # OR state shading removed — OR:0/1 shown in stats bar instead (no chart lag)

        draw_line(self._cv1, raw, C_RAW, width=1)
        draw_line(self._cv1, C,   C_LEA, width=1)
        draw_line(self._cv1, L,   C_BAS, width=2, dash=(4, 3))
        draw_line(self._cv1, MB,  C_MOTHER, width=2, dash=(2, 4))

        if 0 <= or_y_frac <= 1:
            oy = pt_t + ch1 * or_y_frac
            self._cv1.create_line(self.PAD_L, oy, w1 - self.PAD_R, oy,
                                   fill=C_OR, width=1, dash=(3, 4))

        self._cv2.delete('all')
        ymin2, ymax2 = self._safe_range([Q, Pv, N], MIN_PPM_SPAN)
        ymin2 = max(0.0, ymin2)
        rec_min, rec_max = -5.0, 105.0
        self._draw_grid(self._cv2, w2, h2, ymin2, ymax2, 'ppm',
                        secondary_ymin=rec_min, secondary_ymax=rec_max)

        def draw_line2_ppm(data, color, width=1, dash=None):
            pts = self._to_canvas_coords(data, w2, h2, ymin2, ymax2)
            if pts and len(pts) >= 4:
                kw = dict(fill=color, width=width, smooth=False, tags='line')
                if dash: kw['dash'] = dash
                self._cv2.create_line(*pts, **kw)

        def draw_line2_rec(data, color, width=1, dash=None):
            pts = self._to_canvas_coords(data, w2, h2, rec_min, rec_max)
            if pts and len(pts) >= 4:
                kw = dict(fill=color, width=width, smooth=False, tags='line')
                if dash: kw['dash'] = dash
                self._cv2.create_line(*pts, **kw)

        draw_line2_ppm(N,  C_RAW,  width=1, dash=(3, 3))
        draw_line2_ppm(Pv, C_UP,   width=1, dash=(2, 3))
        draw_line2_ppm(Q,  C_CONC, width=2)
        draw_line2_rec(RC, C_REC,  width=1, dash=(4, 2))


class EditWindow(tk.Toplevel):
    def __init__(self, parent, params, on_apply):
        super().__init__(parent)
        self.title("Parameter Editor — V2.9.9f")
        self.configure(bg=BG); self.geometry("880x700"); self.resizable(True,True)
        self.params=dict(params); self.on_apply=on_apply; self._vars={}
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

    def _build(self):
        btn=tk.Frame(self,bg=BG); btn.pack(fill='x',side='bottom',padx=6,pady=4)
        tk.Button(btn,text='Apply & Close',bg=ACC,fg='#fff',font=('Segoe UI',10,'bold'),
                  relief='flat',cursor='hand2',padx=10,pady=5,command=self._apply_close).pack(side='right',padx=3)
        tk.Button(btn,text='Apply',bg=PNL2,fg=ACC,font=('Segoe UI',10),
                  relief='flat',cursor='hand2',padx=10,pady=5,command=self._apply).pack(side='right',padx=3)
        tk.Button(btn,text='Reset Defaults',bg=PNL2,fg=C_DN,font=('Segoe UI',10),
                  relief='flat',cursor='hand2',padx=10,pady=5,command=self._reset_defaults).pack(side='left',padx=3)
        nb=ttk.Notebook(self); nb.pack(fill='both',expand=True,padx=6,pady=6)
        sty=ttk.Style(); sty.theme_use('default')
        sty.configure('TNotebook',background=BG,borderwidth=0)
        sty.configure('TNotebook.Tab',background=PNL2,foreground=DIM,padding=[10,3],font=('Segoe UI',9))
        sty.map('TNotebook.Tab',background=[('selected',PNL)],foreground=[('selected',ACC)])
        for tab_fn,title in [
            (self._core,'Core Logic'),(self._ramp,'Ramp/Drop Tables'),
            (self._calib_tab,'Calibration (P→ppm)'),(self._stab,'Stability Recovery'),
            (self._overrange,'Overrange'),
        ]:
            frm=tk.Frame(nb,bg=BG); nb.add(frm,text=title); tab_fn(frm)

    def _row(self,p,r,label,key,tip=''):
        tk.Label(p,text=label,bg=BG,fg=FG,font=('Segoe UI',9),anchor='w').grid(row=r,column=0,sticky='w',padx=8,pady=3)
        sv=tk.StringVar(value=str(self.params.get(key,''))); self._vars[key]=sv
        tk.Entry(p,textvariable=sv,bg=PNL,fg=ACC,font=('Segoe UI',10,'bold'),
                 width=14,insertbackground=ACC,relief='solid',bd=1,
                 highlightbackground=BRD,highlightthickness=1).grid(row=r,column=1,padx=8,pady=3,sticky='w')
        if tip: tk.Label(p,text=tip,bg=BG,fg=DIM,font=('Segoe UI',7),anchor='w').grid(row=r,column=2,sticky='w',padx=4)

    def _make_table(self,parent,title,key,c1,c2,scrollable=False,c3=None):
        """Build a 2- or 3-column editable table. c3: optional 3rd column header (band)."""
        hdr=tk.Frame(parent,bg=BG); hdr.pack(fill='x',padx=8,pady=(8,2))
        tk.Label(hdr,text=title,bg=BG,fg=ACC,font=('Segoe UI',9,'bold')).pack(side='left')
        add_btn=tk.Button(hdr,text='+ Row',bg=PNL2,fg=C_AIR,font=('Segoe UI',8),relief='flat',cursor='hand2',padx=6,pady=1)
        add_btn.pack(side='right',padx=2)
        colh=tk.Frame(parent,bg=BG); colh.pack(fill='x',padx=8)
        tk.Label(colh,text=c1,bg=BG,fg=DIM,font=('Segoe UI',7,'bold'),width=16).pack(side='left')
        tk.Label(colh,text=c2,bg=BG,fg=DIM,font=('Segoe UI',7,'bold'),width=16).pack(side='left')
        if c3:
            tk.Label(colh,text=c3,bg=BG,fg='#c2410c',font=('Segoe UI',7,'bold'),width=12).pack(side='left')
        if scrollable:
            outer=tk.Frame(parent,bg=BG); outer.pack(fill='both',expand=True,padx=8)
            canvas=tk.Canvas(outer,bg=BG,highlightthickness=0)
            sb=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
            rf=tk.Frame(canvas,bg=BG)
            rf.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
            canvas.create_window((0,0),window=rf,anchor='nw')
            canvas.configure(yscrollcommand=sb.set)
            canvas.pack(side='left',fill='both',expand=True); sb.pack(side='right',fill='y')
        else:
            rf=tk.Frame(parent,bg=BG); rf.pack(fill='x',padx=8)
        pairs=[]

        def add_row(kv='',vv='',bv='0'):
            rw=tk.Frame(rf,bg=BG); rw.pack(fill='x',pady=1)
            sk=tk.StringVar(value=str(kv)); sv=tk.StringVar(value=str(vv))
            tk.Entry(rw,textvariable=sk,bg=PNL,fg=FG,font=('Segoe UI',9),width=16,relief='solid',bd=1).pack(side='left',padx=2)
            tk.Entry(rw,textvariable=sv,bg=PNL,fg=ACC,font=('Segoe UI',9),width=16,relief='solid',bd=1).pack(side='left',padx=2)
            if c3:
                sb3=tk.StringVar(value=str(bv))
                tk.Entry(rw,textvariable=sb3,bg='#fff7ed',fg='#c2410c',font=('Segoe UI',9),width=10,relief='solid',bd=1).pack(side='left',padx=2)
                rem=tk.Button(rw,text='✕',bg=BG,fg=C_DN,font=('Segoe UI',7),relief='flat',cursor='hand2',padx=2,
                             command=lambda r=rw,pair=(sk,sv,sb3):_remove_row(r,pair))
                rem.pack(side='left',padx=1); pairs.append((sk,sv,rw,sb3))
            else:
                rem=tk.Button(rw,text='✕',bg=BG,fg=C_DN,font=('Segoe UI',7),relief='flat',cursor='hand2',padx=2,
                             command=lambda r=rw,pair=(sk,sv):_remove_row(r,pair))
                rem.pack(side='left',padx=1); pairs.append((sk,sv,rw))

        def _remove_row(rw,pair):
            if len(pairs)<=2: return
            idx=next((i for i,p in enumerate(pairs) if p[2]==rw),None)
            if idx is not None: pairs.pop(idx); rw.destroy()

        add_btn.config(command=lambda:add_row())
        for row in self.params.get(key,[]):
            if c3:
                bv=row[2] if len(row)>=3 else 0
                add_row(row[0],row[1],bv)
            else:
                add_row(row[0],row[1])
        self._vars[key]=pairs; return pairs

    def _core(self,p):
        p.columnconfigure(2,weight=1)
        rows=[
            ('Leaky snap jmp (mV)',            'jmp',               'snap if |EMF−Leaky| > this'),
            ('Blend alpha',                    'alp',               'smoothing per sample 0–1'),
            ('Up gate upG',                    'upG',               'D > upG to confirm H2 up'),
            ('Intensity gate inG',             'inG',               'E > inG to confirm H2 up'),
            ('Down gate dnG',                  'dnG',               'F > dnG to confirm H2 down'),
            ('Down intensity dnI',             'dnI',               'G < dnI to confirm H2 down'),
            ('Recovery thresh rec',            'rec',               'K ≥ rec to update baseline'),
            ('Baseline drift drf (mV)',        'drf',               'max |Leaky−Baseline| upward drift'),
            ('Fast-change n_thresh',           'n_thresh',          'ΔM > n_thresh×M to accumulate N  (used when ppm ≥ n_thresh ppm threshold)'),
            ('n_thresh low-signal value',      'n_thresh_low',      'n_thresh used when ppm < threshold (default 0.0033)'),
            ('n_thresh ppm threshold (ppm)',   'n_thresh_ppm_thresh','if current ppm < this → use n_thresh_low; else use n_thresh (default 1000 ppm)'),
            ('ROC cap o_cap',                  'o_cap',             '80 = 6 s at 75 ms/sample'),
            ('Recovery zero %',                'rec_zero_pct',      '|M| < this×peak → 100% recovered'),
            ('Warmup samples',                 'warmup_samples',    '# samples before SD check starts (67 = 5 s)'),
            ('Daughter→Mother proximity (mV)', 'daughter_mother_prox', 'daughter within this of mother → LOW LEAKS ready'),
            ('Post-high conc. threshold (ppm)', 'post_high_conc_thresh', 'ppm level that arms the large-leak-only counter on DOWN flag'),
            ('Post-high counter limit (samples)', 'post_high_counter_limit', 'samples to count before resuming normal sensitivity'),
            ('Post-high upG override',           'post_high_upG',           'upG used while counter is active (less sensitive)'),
            ('Post-high inG override',           'post_high_inG',           'inG used while counter is active (less sensitive)'),
        ]
        tk.Label(p,text='Core Logic Parameters',bg=BG,fg=ACC,font=('Segoe UI',11,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',padx=8,pady=(10,6))
        for r,(lbl,key,tip) in enumerate(rows,1): self._row(p,r,lbl,key,tip)

    def _overrange(self,p):
        p.columnconfigure(2,weight=1)
        tk.Label(p,text='Overrange Routine Parameters',bg=BG,fg=C_OR,font=('Segoe UI',11,'bold')).grid(row=0,column=0,columnspan=3,sticky='w',padx=8,pady=(10,6))
        desc=("Fully independent state machine — suspends ALL normal H2 logic.\n\n"
              "Flow:  EMF > or_thresh  →  OVERRANGE  (all logic frozen)\n"
              "       EMF < or_exit_mv →  WAIT DROP  (watch SD)\n"
              "       SD < or_sd_stable →  STABLE     (TEAR button appears)\n"
              "       Press TARE       →  Full state reset — resumes NORMAL")
        tk.Label(p,text=desc,bg=BG,fg=DIM,font=('Segoe UI',8),justify='left',wraplength=560).grid(row=1,column=0,columnspan=3,sticky='w',padx=8,pady=(0,10))
        rows=[
            ('Overrange entry (mV)','or_thresh','EMF > this → enter OVERRANGE (default 720 mV)'),
            ('Exit threshold (mV)','or_exit_mv','EMF must fall below this before SD is checked (default 20 mV)'),
            ('Stable SD threshold (mV)','or_sd_stable','SD < this → show TEAR button (default 0.00002)'),
        ]
        for r,(lbl,key,tip) in enumerate(rows,2): self._row(p,r,lbl,key,tip)

    def _ramp(self,p):
        cols=tk.Frame(p,bg=BG); cols.pack(fill='both',expand=True)
        lf=tk.Frame(cols,bg=BG); lf.pack(side='left',fill='both',expand=True)
        rf=tk.Frame(cols,bg=BG); rf.pack(side='left',fill='both',expand=True)
        self._make_table(lf,'Upward ramp_up (D:E)','ramp_up','EMF (mV)','Ramp rate')
        self._make_table(rf,'Downward ramp_dn (F:G)','ramp_dn','EMF (mV)','Drop rate')

    def _calib_tab(self,p):
        pw=tk.PanedWindow(p,orient='vertical',bg=BG,sashwidth=4,sashrelief='flat')
        pw.pack(fill='both',expand=True)
        top=tk.Frame(pw,bg=BG); pw.add(top,minsize=120)
        tk.Label(top,text='Fast Calibration: P clip (mV) → H2 ppm',bg=BG,fg=ACC,font=('Segoe UI',10,'bold')).pack(anchor='w',padx=8,pady=(8,2))
        tk.Label(top,text='Linear interpolation between breakpoints.',bg=BG,fg=DIM,font=('Segoe UI',8)).pack(anchor='w',padx=8)
        self._make_table(top,'','calib','Clip P (mV)','Concentration (ppm)',scrollable=True,c3='Band ±(mV)')
        bot=tk.Frame(pw,bg=BG); pw.add(bot,minsize=120)
        tk.Label(bot,text='Analytical Calibration: N Bulk Change (mV) → H2 ppm',
                 bg=BG,fg=ACC,font=('Segoe UI',10,'bold')).pack(anchor='w',padx=8,pady=(8,2))
        tk.Label(bot,text='Used for parallel real-time analytical estimate. '
                 'Display ppm = MAX(Fast ppm, Analytical ppm).',
                 bg=BG,fg=DIM,font=('Segoe UI',8)).pack(anchor='w',padx=8)
        self._make_table(bot,'','calib_analytical',
                         'Bulk N (mV)','Concentration (ppm)',scrollable=True,c3='Band ±(mV)')

    def _stab(self,p):
        self._make_table(p,'Stability/Recovery — SD → factor (used for post-TARE recovery K only)','stab_rec','SD breakpoint','Recovery factor')

    def _collect(self):
        pr={}
        scalar_keys=['jmp','alp','upG','inG','dnG','dnI','rec','drf',
                     'n_thresh','n_thresh_low','n_thresh_ppm_thresh',
                     'o_cap','rec_zero_pct','warmup_samples',
                     'or_thresh','or_exit_mv','or_sd_stable','daughter_mother_prox',
                     'post_high_conc_thresh','post_high_counter_limit',
                     'post_high_upG','post_high_inG']
        for k in scalar_keys:
            try:    pr[k]=float(self._vars[k].get())
            except: pr[k]=DEFAULT_PARAMS.get(k,0)
        pr['o_cap']=int(pr['o_cap']); pr['warmup_samples']=int(pr['warmup_samples'])
        pr['post_high_counter_limit']=int(pr['post_high_counter_limit'])
        # Safety clamp: or_thresh must be positive and large enough to mean a real overrange
        if pr['or_thresh'] < 50.0:
            messagebox.showwarning('Invalid or_thresh',
                f'Overrange entry threshold ({pr["or_thresh"]:.3f} mV) is too low!\n'
                f'Must be ≥ 50 mV. Resetting to default ({DEFAULT_PARAMS["or_thresh"]} mV).',
                parent=self)
            pr['or_thresh'] = DEFAULT_PARAMS['or_thresh']
            self._vars['or_thresh'].set(str(DEFAULT_PARAMS['or_thresh']))
        for tk_ in ('ramp_up','ramp_dn','calib','calib_analytical','stab_rec'):
            rows=[]
            for entry in self._vars[tk_]:
                sk,sv = entry[0],entry[1]
                # entry[3] is band StringVar if it exists (calib tables with c3 column)
                sb3 = entry[3] if len(entry)>=4 else None
                try:
                    emf_v=float(sk.get()); ppm_v=float(sv.get())
                    if sb3 is not None:
                        band_v=float(sb3.get())
                        rows.append((emf_v,ppm_v,band_v))
                    else:
                        rows.append((emf_v,ppm_v))
                except: pass
            rows.sort(key=lambda x:x[0]); pr[tk_]=rows
        return pr

    def _apply(self):       new=self._collect(); self.params=new; self.on_apply(new)
    def _apply_close(self): self._apply(); self.withdraw()
    def _reset_defaults(self):
        if messagebox.askyesno("Reset","Reset all to factory defaults?",parent=self):
            self.destroy(); self.__init__(self.master,DEFAULT_PARAMS,self.on_apply)


class App:
    WIN         = 1200
    INTERVAL    = 75
    CHART_EVERY = 500

    def __init__(self, root):
        self.root=root
        self.root.title("T5 Sensor Sim  [V2.9.9k]")
        self.root.configure(bg=BG)
        self.root.geometry("1280x700")
        self.root.minsize(1000,580)
        self.params=dict(DEFAULT_PARAMS)

        self.raw_data=[]; self.times=self.emf_arr=None
        self.C=self.D=self.E=self.FF=self.G=self.H=self.II=None
        self.J=self.K=self.L=self.MB_arr=self.M=self.N_=self.O_=None
        self.Pv=self.Q_=self.RC_=self.OR_STATE_arr=self.WARMUP_PHASE_arr=None
        self.R_arr=self.S_arr=None

        self._calib_offset=0; self._live_calibs=set(); self._batch_calibs=set()
        self._live_tears=set(); self._batch_tears=set()

        self.sim_idx=0; self.running=False; self._after_id=None
        self._last_flag=None; self._prog_w=0; self._last_chart_ms=0

        self._live_mode=False; self._live_state=LiveState()
        self._live_thread=None; self._live_after=None
        self._live_last_flag=None; self._ic=None; self._live_warmup_done=False

        self._flash_after=None; self._flash_state=False; self._flash_active=False
        self._or_flash_after=None; self._or_flash_state=False
        self._or_flash_active=False; self._or_which=None
        self._last_or_state='normal'; self._calib_btn_visible=False

        self._ready_flash_after=None; self._ready_flash_state=False
        self._ready_flash_active=False; self._ready_flash_low=True

        self._current_disp_flag=None

        self._poweroff_warn_after=None
        self._poweroff_warn_active=False

        self._init_overlay_active=False
        self._init_flash_after=None
        self._init_flash_state=False

        self._unstable_overlay_active=False
        self._unstable_flash_after=None
        self._unstable_flash_state=False

        self._warmup_proxfail_dialog_shown = False
        self._warmup_tare_needed = False
        self._warmup_tare_flash_active = False
        self._warmup_tare_flash_after = None
        self._warmup_tare_flash_state = False
        self._batch_ignore_prox = False
        self._batch_wait_instability = False

        # Post-high-concentration limiting state
        self._post_high_active = False    # True while counter is running
        self._post_high_counter = 0       # counts up to post_high_counter_limit
        self._post_high_peak_ppm = 0.0   # ppm that triggered the limit
        self._post_high_saw_high = False  # True once ppm >= thresh during an UP event

        self._memory=_load_memory()
        self._prev_mother_baseline=self._memory.get('mother_baseline',None)

        self._compute_q=queue.Queue()
        self._build_ui()
        self._edit_win=EditWindow(self.root,self.params,self._on_params)
        self._edit_win.withdraw()
        self._update_prev_mother_display()

    def _reset_post_high_state(self):
        """Clear post-high-concentration limiting counter."""
        self._post_high_active = False
        self._post_high_counter = 0
        self._post_high_peak_ppm = 0.0
        self._post_high_saw_high = False
        if hasattr(self, '_ph_banner_visible') and self._ph_banner_visible:
            self._hide_post_high_banner()

    def _show_post_high_banner(self):
        if getattr(self, '_ph_banner_visible', False): return
        self._ph_banner.pack(fill='x', side='top', before=self._nb)
        self._ph_banner_visible = True

    def _hide_post_high_banner(self):
        if not getattr(self, '_ph_banner_visible', False): return
        self._ph_banner.pack_forget()
        self._ph_banner_visible = False

    def _update_post_high_indicator(self):
        """Update the post-high counter banner — show progress bar and count."""
        if not hasattr(self, '_ph_banner'): return
        if self._post_high_active:
            self._show_post_high_banner()
            limit = int(self.params.get('post_high_counter_limit', 6000))
            cnt = min(self._post_high_counter, limit)
            self.lbl_ph_count.config(text=f'{cnt} / {limit}')
            # Draw progress bar inside the canvas
            w = self._ph_prog_cv.winfo_width()
            if w > 4:
                pct = cnt / limit if limit > 0 else 0
                filled = int(w * pct)
                self._ph_prog_cv.delete('all')
                self._ph_prog_cv.create_rectangle(0, 0, filled, 4, fill='#fbbf24', width=0)
        else:
            self._hide_post_high_banner()

    def _daughter_near_mother(self,daughter,mother):
        prox=float(self.params.get('daughter_mother_prox',2.0))
        return abs(daughter-mother)<=prox

    def _update_prev_mother_display(self):
        if not hasattr(self,'prev_mb_lbl'): return
        if self._prev_mother_baseline is not None:
            ts=self._memory.get('timestamp','')
            self.prev_mb_lbl.config(text=f"{self._prev_mother_baseline:.3f} mV",fg=C_MOTHER)
            if hasattr(self,'prev_mb_ts_lbl'):
                self.prev_mb_ts_lbl.config(text=ts[:16] if ts else 'stored',fg=DIM)
        else:
            self.prev_mb_lbl.config(text='-- (no record)',fg=DIM)
            if hasattr(self,'prev_mb_ts_lbl'):
                self.prev_mb_ts_lbl.config(text='',fg=DIM)

    def _check_warmup_baseline(self,new_mother_mv):
        if self._prev_mother_baseline is None:
            self._log(f'✓ Warmup done — mother BL: {new_mother_mv:.3f} mV (no prev record)','info')
            return
        diff=abs(new_mother_mv-self._prev_mother_baseline)
        if diff<=60.0:
            self._log(f'✓ BL OK — new: {new_mother_mv:.3f} mV  prev: {self._prev_mother_baseline:.3f} mV  Δ={diff:.2f} mV','air')
        else:
            self._log(f'⚠ BL SHIFT — new: {new_mother_mv:.3f} mV  prev: {self._prev_mother_baseline:.3f} mV  Δ={diff:.2f} mV  *** OUTSIDE ±60 mV ***','warn')

    def _on_params(self,new_p):
        self.params=new_p
        if self._live_mode and self._ic is not None:
            old_emf=list(self._ic.emf)
            sorted_tears = sorted(self._live_tears)
            last_tear_idx = sorted_tears[-1] if sorted_tears else -1
            self._ic=IncrementalCompute(self.params, prev_mb=self._prev_mother_baseline)
            last_overrange_idx = -1  # track the sample index when overrange was last entered
            n_total = len(old_emf)
            self._ic._or_debug_suppress = True  # silence prints during replay
            for i,v in enumerate(old_emf):
                prev_or_state = self._ic._or_state
                self._ic.step(v)
                # Track the most recent sample index that triggered overrange entry
                if prev_or_state == 'normal' and self._ic._or_state == 'overrange':
                    last_overrange_idx = i
                if i in self._live_tears:
                    self._ic.do_manual_tear()
                    self._ic._or_seen_overrange = False
                    last_overrange_idx = -1  # tare clears the overrange history
            self._ic._or_debug_suppress = False  # re-enable prints for live
            # Suppress stable/waiting_drop after replay if the last overrange event
            # was cleared by a tare (last_overrange_idx == -1 means tare happened
            # after the overrange, or no overrange happened at all).
            if last_overrange_idx == -1 and self._ic._or_state in ('stable','waiting_drop'):
                self._ic._or_state = 'normal'
                self._ic._or_seen_overrange = False
                if self._ic.OR_STATE: self._ic.OR_STATE[-1] = 'normal'
            t_replay = n_total * 0.200
            print(f'[OR REPLAY done t={t_replay:.1f}s] final_state={self._ic._or_state}  seen={self._ic._or_seen_overrange}  last_OR_idx={last_overrange_idx}  tears={sorted(self._live_tears)}')
            self._last_or_state = 'normal'
            self._update_or_box(self._ic._or_state, '--')
            self._log('params updated — live recomputed','info')
        elif not self._live_mode and self.emf_arr is not None:
            self._recompute_batch()
            self._log('params updated — batch recomputed','info')

    def _build_ui(self):
        tb=tk.Frame(self.root,bg=PNL,height=32,relief='flat')
        tb.pack(fill='x',side='top')
        tk.Frame(self.root,bg=BRD,height=1).pack(fill='x',side='top')
        tb.pack_propagate(False)
        tk.Label(tb,text='T5  SENSOR SIM',bg=PNL,fg=ACC,font=('Segoe UI',10,'bold')).pack(side='left',padx=10)
        tk.Frame(tb,bg=BRD,width=1).pack(side='left',fill='y',pady=4)
        tk.Label(tb,text='V2.9.9N',bg=PNL,fg=DIM,font=('Segoe UI',7)).pack(side='left',padx=4)
        self.lbl_info=tk.Label(tb,text='no file loaded',bg=PNL,fg=DIM,font=('Segoe UI',8))
        self.lbl_info.pack(side='left',padx=6)
        self.lbl_live=tk.Label(tb,text='',bg=PNL,fg=C_AIR,font=('Segoe UI',8,'bold'))
        self.lbl_live.pack(side='left',padx=4)
        self.lbl_stats=tk.Label(tb,text='t=--  emf=--  Δ=--  SD=--  ppm=--  rec=--%',bg=PNL,fg=DIM,font=('Segoe UI',7))
        self.lbl_stats.pack(side='right',padx=10)
        # nth-mode indicator pill: shows which n_thresh is currently active
        self.lbl_nth_mode = tk.Label(tb, text='nth: --', bg='#e2e8f0', fg='#64748b',
                                     font=('Segoe UI', 7, 'bold'), relief='flat',
                                     padx=5, pady=1)
        self.lbl_nth_mode.pack(side='right', padx=(0, 4))

        body=tk.Frame(self.root,bg=BG); body.pack(fill='both',expand=True)
        left=tk.Frame(body,bg=PNL,width=185,relief='flat')
        left.pack(side='left',fill='y'); left.pack_propagate(False)
        tk.Frame(body,bg=BRD,width=1).pack(side='left',fill='y')

        def sec(title):
            tk.Frame(left,bg=SEP,height=1).pack(fill='x')
            f=tk.Frame(left,bg=PNL); f.pack(fill='x',padx=6,pady=3)
            return f

        sf=sec('SOURCE')
        tk.Button(sf,text='📂  Browse CSV',bg=PNL2,fg=ACC,relief='flat',bd=0,font=('Segoe UI',8),cursor='hand2',command=self._browse).pack(fill='x',ipady=3,pady=1)
        tk.Button(sf,text='📡  Live Log',bg=PNL2,fg=C_AIR,relief='flat',bd=0,font=('Segoe UI',8),cursor='hand2',command=self._browse_live).pack(fill='x',ipady=3,pady=1)
        self.btn_live_stop=tk.Button(sf,text='⏹  Stop Live',bg=PNL2,fg=C_DN,relief='flat',bd=0,font=('Segoe UI',8),cursor='hand2',state='disabled',command=self._stop_live)
        self.btn_live_stop.pack(fill='x',ipady=2,pady=1)
        self.btn_tear=tk.Button(sf,text=' MANUAL TARE',bg='#fff7ed',fg='#c2410c',
                                 relief='flat',bd=0,font=('Segoe UI',8,'bold'),cursor='hand2',
                                 state='disabled',command=self._do_manual_tear)
        self.btn_tear.pack(fill='x',ipady=3,pady=(3,0))
        tk.Label(sf,text='Full state reset — matches C do_tear()',bg=PNL,fg=DIM,font=('Segoe UI',6),anchor='w').pack(fill='x')

        tk.Frame(left,bg=SEP,height=1).pack(fill='x')
        pof=tk.Frame(left,bg=PNL); pof.pack(fill='x',padx=6,pady=3)
        tk.Label(pof,text='SYSTEM',bg=PNL,fg=DIM,font=('Segoe UI',6,'bold')).pack(anchor='w',pady=(0,1))
        self.btn_poweroff=tk.Button(pof,text='⏻  POWER OFF',bg='#fef2f2',fg='#dc2626',
                                     relief='flat',bd=0,font=('Segoe UI',8,'bold'),cursor='hand2',
                                     state='disabled',command=self._do_poweroff)
        self.btn_poweroff.pack(fill='x',ipady=4,pady=(0,1))
        tk.Label(pof,text='Saves mother BL  •  Only in AIR state',bg=PNL,fg=DIM,font=('Segoe UI',6),anchor='w').pack(fill='x')

        wf=sec('WINDOW (CSV)')
        self.e_t0=self._prow(wf,'From','0'); self.e_t1=self._prow(wf,'To','9999')

        self._prog_cv=tk.Canvas(left,bg=SEP,height=3,highlightthickness=0)
        self._prog_cv.pack(fill='x',padx=0,pady=1)
        self._prog_cv.bind('<Configure>',lambda e:setattr(self,'_prog_w',e.width))

        pf=sec('PLAYBACK')
        sr=tk.Frame(pf,bg=PNL); sr.pack(fill='x',pady=(0,2))
        tk.Label(sr,text='Speed',bg=PNL,fg=DIM,font=('Segoe UI',7),width=5).pack(side='left')
        self.spd_var=tk.IntVar(value=30)
        self.lbl_spd=tk.Label(sr,text='30×',bg=PNL,fg=ACC,font=('Segoe UI',8,'bold'),width=4)
        self.lbl_spd.pack(side='right')
        tk.Scale(sr,from_=1,to=500,orient='horizontal',variable=self.spd_var,bg=PNL,fg=ACC,
                 showvalue=False,highlightthickness=0,troughcolor=SEP,bd=0,
                 command=lambda v:self.lbl_spd.config(text=f'{v}×')).pack(side='left',fill='x',expand=True)
        br=tk.Frame(pf,bg=PNL); br.pack(fill='x')
        self.btn_play=self._btn(br,'▶ Play',self._play,ACC,'#fff')
        self.btn_pause=self._btn(br,'⏸',self._pause,PNL2,ACC)
        self.btn_reset=self._btn(br,'↺',self._reset,PNL2,DIM)
        for b in (self.btn_play,self.btn_pause,self.btn_reset): b.config(state='disabled')

        ef=sec('PARAMETERS')
        tk.Button(ef,text='⚙  Edit Parameters',bg=PNL2,fg=ACC,relief='flat',bd=0,font=('Segoe UI',8),cursor='hand2',command=self._show_edit).pack(fill='x',ipady=3)

        mf=sec('LIVE VALUES')
        self.mv={}
        self.mv_emf={}   # ΔmV sub-labels for Q (ppm Fast) and R (ppm Analyt)
        grid=tk.Frame(mf,bg=PNL); grid.pack(fill='x')
        items=[('C','Leaky mV'),('M','ΔBase mV'),('J','SD'),('REC','Rec %'),
               ('N','N accum'),('O','ROC O'),('P','Clip P'),('Q','ppm Fast'),
               ('R','ppm Analyt'),('S','ppm Display')]
        for idx,(k,name) in enumerate(items):
            r,c=divmod(idx,2)
            cell=tk.Frame(grid,bg=PNL2,relief='flat'); cell.grid(row=r,column=c,padx=1,pady=1,sticky='ew')
            nc=(C_CONC if k in ('N','O','P','Q','R','S') else C_REC if k=='REC' else DIM)
            tk.Label(cell,text=name,bg=PNL2,fg=nc,font=('Segoe UI',6,'bold')).pack(anchor='w',padx=3,pady=(2,0))
            lbl=tk.Label(cell,text='--',bg=PNL2,fg=FG,font=('Segoe UI',8,'bold'))
            lbl.pack(anchor='w',padx=3,pady=(0,0)); self.mv[k]=lbl
            if k in ('Q','R'):
                emf_lbl=tk.Label(cell,text='Δ=-- mV',bg=PNL2,fg=FG,font=('Segoe UI',6))
                emf_lbl.pack(anchor='w',padx=3,pady=(0,2))
                self.mv_emf[k]=emf_lbl
            else:
                tk.Label(cell,text='',bg=PNL2,font=('Segoe UI',1)).pack(pady=(0,2))
        grid.columnconfigure(0,weight=1); grid.columnconfigure(1,weight=1)

        bf=sec('BASELINES')
        bgrid=tk.Frame(bf,bg=PNL); bgrid.pack(fill='x')
        for bi,(bname,bcol,bkey) in enumerate([
            ('Mother BL',C_MOTHER,'mb_lbl'),
            ('Daughter BL',C_BAS,'db_lbl'),
        ]):
            bcell=tk.Frame(bgrid,bg=PNL2,relief='flat')
            bcell.grid(row=0,column=bi,padx=1,pady=1,sticky='ew')
            tk.Label(bcell,text=bname,bg=PNL2,fg=bcol,font=('Segoe UI',6,'bold')).pack(anchor='w',padx=3,pady=(2,0))
            lbl=tk.Label(bcell,text='--',bg=PNL2,fg=FG,font=('Segoe UI',8,'bold'))
            lbl.pack(anchor='w',padx=3,pady=(0,2)); setattr(self,bkey,lbl)
        bgrid.columnconfigure(0,weight=1); bgrid.columnconfigure(1,weight=1)

        prev_cell=tk.Frame(bf,bg='#fffbeb',relief='flat'); prev_cell.pack(fill='x',padx=1,pady=(1,0))
        tk.Label(prev_cell,text='Prev. Mother BL (stored)',bg='#fffbeb',fg=C_MOTHER,
                 font=('Segoe UI',6,'bold')).pack(anchor='w',padx=3,pady=(2,0))
        self.prev_mb_lbl=tk.Label(prev_cell,text='-- (no record)',bg='#fffbeb',fg=DIM,
                                   font=('Segoe UI',8,'bold'))
        self.prev_mb_lbl.pack(anchor='w',padx=3)
        self.prev_mb_ts_lbl=tk.Label(prev_cell,text='',bg='#fffbeb',fg=DIM,font=('Segoe UI',6))
        self.prev_mb_ts_lbl.pack(anchor='w',padx=3,pady=(0,2))

        right=tk.Frame(body,bg=BG); right.pack(side='left',fill='both',expand=True)

        flag_strip=tk.Frame(right,bg=PNL,height=76)
        flag_strip.pack(fill='x',side='top'); flag_strip.pack_propagate(False)
        tk.Frame(right,bg=BRD,height=1).pack(fill='x',side='top')

        self.flag_boxes={}
        flag_defs=[
            (-1,'AIR / BASELINE',C_AIR,'#f0fdf4',False,False,True),
            (1,'H2 CONFIRMED ▲',C_UP,'#fffbeb',True,False,False),
            (-2,'H2 DOWN ▼',C_DN,'#fef2f2',False,False,False),
            (-3,'RECOVERING',C_REC,'#faf5ff',False,True,False),
        ]
        for val,name,col,bg2,has_conc,has_rec,has_ready in flag_defs:
            box=tk.Frame(flag_strip,bg=PNL,relief='flat',bd=0)
            box.pack(side='left',fill='both',expand=True,padx=2,pady=3)
            dot=tk.Label(box,text='●',bg=PNL,fg=BRD,font=('Segoe UI',9))
            dot.pack(side='left',padx=(6,2),pady=1)
            inner=tk.Frame(box,bg=PNL); inner.pack(side='left',fill='both',expand=True,pady=1)
            nlbl=tk.Label(inner,text=name,bg=PNL,fg=DIM,font=('Segoe UI',7,'bold'))
            nlbl.pack(anchor='w')
            clbl=tk.Label(inner,text='0 events',bg=PNL,fg=DIM,font=('Segoe UI',6))
            clbl.pack(anchor='w')
            conc_lbl=None
            if has_conc:
                conc_lbl=tk.Label(inner,text='',bg=PNL,fg=DIM,font=('Segoe UI',9,'bold'))
                conc_lbl.pack(anchor='w')
            rec_bar=rec_msg=None
            if has_rec:
                rec_bar=ttk.Progressbar(inner,orient='horizontal',length=80,mode='determinate')
                rec_bar.pack(anchor='w',pady=(1,0))
                rec_msg=tk.Label(inner,text='0%',bg=PNL,fg=C_REC,font=('Segoe UI',7,'bold'))
                rec_msg.pack(anchor='w',pady=(1,0))
            ready_msg=None
            if has_ready:
                ready_msg=tk.Label(inner,text='',bg=PNL,fg=C_AIR,font=('Segoe UI',7,'bold'))
                ready_msg.pack(anchor='w',pady=(1,0))
            self.flag_boxes[val]={
                'frame':box,'dot':dot,'name':nlbl,'count':clbl,'col':col,'bg':bg2,'events':0,
                'conc_lbl':conc_lbl,'rec_bar':rec_bar,'rec_msg':rec_msg,
                'ready_msg':ready_msg,'inner':inner,'_bg_now':PNL,
            }

        sep_or=tk.Frame(flag_strip,bg=BRD,width=2); sep_or.pack(side='left',fill='y',pady=3)
        or_box=tk.Frame(flag_strip,bg=PNL,relief='flat',bd=0,width=160)
        or_box.pack(side='left',fill='y',padx=2,pady=3); or_box.pack_propagate(False)
        or_dot=tk.Label(or_box,text='●',bg=PNL,fg=BRD,font=('Segoe UI',9))
        or_dot.pack(side='left',padx=(5,2),pady=1)
        or_inner=tk.Frame(or_box,bg=PNL); or_inner.pack(side='left',fill='both',expand=True,pady=1)
        or_nlbl=tk.Label(or_inner,text='NORMAL',bg=PNL,fg=DIM,font=('Segoe UI',7,'bold'))
        or_nlbl.pack(anchor='w')
        or_sublbl=tk.Label(or_inner,text='EMF in range',bg=PNL,fg=DIM,font=('Segoe UI',6))
        or_sublbl.pack(anchor='w')
        # OR engine flag pill: shows "OR ENGINE: FALSE" / "OR ENGINE: TRUE"
        self.lbl_or_flag = tk.Label(or_inner, text='OR ENGINE: FALSE',
                                    bg='#f1f5f9', fg='#64748b',
                                    font=('Segoe UI', 6, 'bold'), relief='flat',
                                    padx=3, pady=1)
        self.lbl_or_flag.pack(anchor='w', pady=(1,0))
        self.btn_or_tear = tk.Button(
            or_inner, text='TARE', bg='#c2410c', fg='#ffffff',
            font=('Segoe UI', 6, 'bold'), relief='flat', cursor='hand2',
            padx=3, pady=1, command=self._do_or_tear
        )
        self._or_box={'frame':or_box,'dot':or_dot,'name':or_nlbl,'sub':or_sublbl,'inner':or_inner}

        # ── Post-high-concentration counter banner (hidden until armed) ────────
        self._ph_banner = tk.Frame(right, bg='#78350f', height=22)
        # not packed yet — shown dynamically
        ph_left = tk.Frame(self._ph_banner, bg='#78350f')
        ph_left.pack(side='left', fill='y', padx=(6,0))
        self.lbl_ph_title = tk.Label(ph_left, text='⚠ LARGE LEAKS ONLY',
                                     bg='#78350f', fg='#fde68a',
                                     font=('Segoe UI', 7, 'bold'))
        self.lbl_ph_title.pack(side='left', padx=(0,6))
        ph_right = tk.Frame(self._ph_banner, bg='#78350f')
        ph_right.pack(side='right', fill='y', padx=(0,6))
        self.lbl_ph_count = tk.Label(ph_right, text='0 / 6000',
                                     bg='#78350f', fg='#fbbf24',
                                     font=('Segoe UI', 7, 'bold'))
        self.lbl_ph_count.pack(side='right')
        self._ph_prog_cv = tk.Canvas(self._ph_banner, bg='#92400e',
                                      highlightthickness=0, height=4)
        self._ph_prog_cv.pack(fill='x', side='bottom', padx=2, pady=(0,2))
        self._ph_banner_visible = False
        # ──────────────────────────────────────────────────────────────────────

        # ── Tabbed area: Charts | Events ──────────────────────────────────────
        style = ttk.Style()
        style.configure('Sim.TNotebook', background=BG, borderwidth=0)
        style.configure('Sim.TNotebook.Tab', font=('Segoe UI', 8, 'bold'),
                        padding=[10, 3], background=PNL2, foreground=DIM)
        style.map('Sim.TNotebook.Tab',
                  background=[('selected', ACC)],
                  foreground=[('selected', '#ffffff')])

        self._nb = ttk.Notebook(right, style='Sim.TNotebook')
        self._nb.pack(fill='both', expand=True)

        def _on_tab_change(event):
            try:
                if self._nb.index(self._nb.select())==1:
                    self._nb.tab(1,text='📋  Events')
            except Exception: pass
        self._nb.bind('<<NotebookTabChanged>>', _on_tab_change)

        # ── Tab 0: Charts ─────────────────────────────────────────────────────
        charts_tab = tk.Frame(self._nb, bg=BG)
        self._nb.add(charts_tab, text='📈  Charts')

        self._chart_frame = tk.Frame(charts_tab, bg=BG)
        self._chart_frame.pack(fill='both', expand=True)
        self._canvas_chart = CanvasChart(self._chart_frame)

        self.lbl_init_warn = tk.Label(
            self._chart_frame, text='⏳ INITIALIZING... PLEASE WAIT',
            bg='#3b82f6', fg='#ffffff', font=('Segoe UI', 14, 'bold'),
            padx=20, pady=10, relief='flat'
        )
        self.lbl_unstable_warn = tk.Label(
            self._chart_frame, text='⚠ UNSTABLE: BRING PROBE IN H2-FREE AIR',
            bg='#dc2626', fg='#ffffff', font=('Segoe UI', 14, 'bold'),
            padx=20, pady=10, relief='flat'
        )
        self.lbl_warmup_tare = tk.Label(
            self._chart_frame, text='✔ STABLE — PRESS TARE TO START',
            bg='#059669', fg='#ffffff', font=('Segoe UI', 14, 'bold'),
            padx=20, pady=10, relief='flat', cursor='hand2'
        )
        self.lbl_warmup_tare.bind('<Button-1>', lambda e: self._do_manual_tear())

        # ── Tab 1: Events ─────────────────────────────────────────────────────
        events_tab = tk.Frame(self._nb, bg=PNL)
        self._nb.add(events_tab, text='📋  Events')

        ev_toolbar = tk.Frame(events_tab, bg=PNL2, height=26)
        ev_toolbar.pack(fill='x', side='top'); ev_toolbar.pack_propagate(False)
        tk.Label(ev_toolbar, text='EVENT LOG', bg=PNL2, fg=DIM,
                 font=('Segoe UI', 7, 'bold')).pack(side='left', padx=8, pady=3)
        tk.Button(ev_toolbar, text='Clear', bg=PNL2, fg=C_DN, relief='flat',
                  font=('Segoe UI', 7), cursor='hand2', padx=6,
                  command=self._clear_log).pack(side='right', padx=4, pady=2)
        tk.Frame(events_tab, bg=BRD, height=1).pack(fill='x')

        ev_body = tk.Frame(events_tab, bg=PNL)
        ev_body.pack(fill='both', expand=True)
        ev_sb = ttk.Scrollbar(ev_body, orient='vertical')
        ev_sb.pack(side='right', fill='y')
        self.log = tk.Text(ev_body, bg=PNL, fg=DIM, font=('Segoe UI', 8),
                           relief='flat', state='disabled',
                           wrap='word', yscrollcommand=ev_sb.set)
        self.log.pack(fill='both', expand=True, padx=6, pady=4)
        ev_sb.config(command=self.log.yview)

        for tag, col in [
            ('air', C_AIR), ('up', C_UP), ('dn', C_DN), ('rec', C_REC),
            ('info', ACC), ('conc', C_CONC), ('warn', '#d97706'),
            ('overrange', C_OR), ('stable', C_STB),
            ('tear', '#c2410c'), ('poweroff', '#dc2626'),
        ]:
            self.log.tag_config(tag, foreground=col)
        self._log('waiting for file…', 'info')

        # \u2500\u2500 Tab 2: Calibration \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        calib_tab = tk.Frame(self._nb, bg=BG)
        self._nb.add(calib_tab, text='\U0001f527\u0020 Calibration')
        self._build_calibration_tab(calib_tab)

    def _build_calibration_tab(self, parent):
        """
        Calibration tab.
        - Selecting a known concentration auto-populates EMF fields from
          current live/batch P (fast) and N (analytical) values.
        - User can still edit the fields manually.
        - Compute Preview shows scaled tables without touching self.params.
        - Apply Calibration commits to self.params only when explicitly pressed.
        """
        self._calib_draft = None  # draft tables; None = not yet computed

        # ---- Header ----
        hdr = tk.Frame(parent, bg=PNL2, height=30)
        hdr.pack(fill='x', side='top'); hdr.pack_propagate(False)
        tk.Label(hdr, text='SENSOR CALIBRATION', bg=PNL2, fg=ACC,
                 font=('Segoe UI', 9, 'bold')).pack(side='left', padx=10, pady=4)
        tk.Label(hdr, text='Select gas concentration — EMF fields auto-fill from current readings (editable).',
                 bg=PNL2, fg=DIM, font=('Segoe UI', 7)).pack(side='left', padx=4)
        tk.Frame(parent, bg=BRD, height=1).pack(fill='x')

        body = tk.Frame(parent, bg=BG)
        body.pack(fill='both', expand=True, padx=8, pady=6)

        # ---- Input section ----
        inp_frame = tk.LabelFrame(body, text=' Calibration Inputs ', bg=BG, fg=ACC,
                                   font=('Segoe UI', 8, 'bold'), relief='groove', bd=1)
        inp_frame.pack(fill='x', pady=(0, 6))
        inp_frame.columnconfigure(2, weight=1)

        def _label(row, text):
            tk.Label(inp_frame, text=text, bg=BG, fg=FG,
                     font=('Segoe UI', 8), anchor='w').grid(
                row=row, column=0, sticky='w', padx=8, pady=3)

        def _tip(row, text):
            tk.Label(inp_frame, text=text, bg=BG, fg=DIM,
                     font=('Segoe UI', 7)).grid(row=row, column=2, sticky='w', padx=4)

        # Row 0: known concentration dropdown
        _label(0, 'Known concentration (ppm)')
        self._calib_conc_var = tk.StringVar(value='5000')

        def _on_conc_select(event=None):
            """Auto-populate EMF fields from current P and N when concentration is chosen."""
            self._calib_autofill_emf()
            # Clear any existing preview/draft since inputs changed
            self._calib_draft = None
            self._btn_apply_calib.config(state='disabled')
            self._calib_status.config(
                text='EMF fields auto-filled — edit if needed, then press Compute Preview.',
                fg=DIM)
            self._refresh_calibration_table_display(None, None)

        conc_menu = ttk.Combobox(inp_frame, textvariable=self._calib_conc_var,
                                  values=['5000', '10000', '20000', '100000'],
                                  state='readonly', width=12, font=('Segoe UI', 10))
        conc_menu.grid(row=0, column=1, padx=8, pady=3, sticky='w')
        conc_menu.bind('<<ComboboxSelected>>', _on_conc_select)
        _tip(0, 'Ref gas used for calibration — only 5k/10k/20k/100k ppm allowed')

        # Row 3: SF step editor
        _label(3, 'SF cross-conc. step (Δ)')
        self._calib_sf_step_var = tk.StringVar(value='0.05')
        tk.Entry(inp_frame, textvariable=self._calib_sf_step_var,
                 bg=PNL, fg='#c2410c', font=('Segoe UI', 10, 'bold'),
                 width=10, relief='solid', bd=1).grid(row=3, column=1, padx=8, pady=3, sticky='w')
        _tip(3, 'Step applied per concentration tier away from ref gas (default 0.05). '
                'Table: ref→5k=SF×1, →10k=SF÷1.05, →20k=SF÷1.10, →100k=SF÷1.15 etc.')

        # Row 1: Fast EMF entry + source label
        _label(1, 'Measured ΔEMF — Fast (mV)')
        self._calib_fast_emf_var = tk.StringVar()
        tk.Entry(inp_frame, textvariable=self._calib_fast_emf_var,
                 bg=PNL, fg=ACC, font=('Segoe UI', 10, 'bold'),
                 width=14, relief='solid', bd=1).grid(row=1, column=1, padx=8, pady=3, sticky='w')
        self._calib_fast_src = tk.Label(inp_frame, text='', bg=BG, fg=DIM, font=('Segoe UI', 7))
        self._calib_fast_src.grid(row=1, column=2, sticky='w', padx=4)

        # Row 2: Analytical EMF entry + source label
        _label(2, 'Measured ΔEMF — Analytical (mV)')
        self._calib_anal_emf_var = tk.StringVar()
        tk.Entry(inp_frame, textvariable=self._calib_anal_emf_var,
                 bg=PNL, fg=ACC, font=('Segoe UI', 10, 'bold'),
                 width=14, relief='solid', bd=1).grid(row=2, column=1, padx=8, pady=3, sticky='w')
        self._calib_anal_src = tk.Label(inp_frame, text='', bg=BG, fg=DIM, font=('Segoe UI', 7))
        self._calib_anal_src.grid(row=2, column=2, sticky='w', padx=4)

        # Trace manual edits to update source label (suppressed during auto-fill)
        self._calib_autofill_in_progress = False
        def _mark_manual(src_lbl, *_):
            if not self._calib_autofill_in_progress:
                src_lbl.config(text='(manually edited)', fg='#d97706')
        self._calib_fast_emf_var.trace_add('write', lambda *a: _mark_manual(self._calib_fast_src))
        self._calib_anal_emf_var.trace_add('write', lambda *a: _mark_manual(self._calib_anal_src))

        # ---- Status / control row ----
        ctl_row = tk.Frame(body, bg=BG); ctl_row.pack(fill='x', pady=(0, 6))
        self._calib_status = tk.Label(
            ctl_row,
            text='Select a concentration above — EMF fields will auto-fill from current P and N values.',
            bg=BG, fg=DIM, font=('Segoe UI', 8), anchor='w')
        self._calib_status.pack(side='left', padx=4)
        tk.Button(ctl_row, text='Compute Preview', bg=PNL2, fg=ACC,
                  font=('Segoe UI', 9, 'bold'), relief='flat', cursor='hand2',
                  padx=10, pady=4, command=self._compute_calibration_preview).pack(side='right', padx=4)

        # ---- Tables side by side ----
        tables_frame = tk.Frame(body, bg=BG); tables_frame.pack(fill='both', expand=True)
        tables_frame.columnconfigure(0, weight=1); tables_frame.columnconfigure(1, weight=1)

        def _make_calib_table_frame(parent, col, title, col_header1, col_header2):
            lf = tk.LabelFrame(parent, text=f' {title} ', bg=BG, fg=ACC,
                                font=('Segoe UI', 8, 'bold'), relief='groove', bd=1)
            lf.grid(row=0, column=col, sticky='nsew',
                    padx=(0 if col == 0 else 4, 0), pady=2)
            hf = tk.Frame(lf, bg=PNL2); hf.pack(fill='x', padx=4, pady=(4, 0))
            tk.Label(hf, text=col_header1, bg=PNL2, fg=DIM,
                     font=('Segoe UI', 7, 'bold'), width=16, anchor='w').pack(side='left', padx=4)
            tk.Label(hf, text=col_header2, bg=PNL2, fg=DIM,
                     font=('Segoe UI', 7, 'bold'), width=16, anchor='w').pack(side='left', padx=4)
            tk.Label(hf, text='Preview', bg=PNL2, fg=DIM,
                     font=('Segoe UI', 7, 'bold'), width=12, anchor='w').pack(side='left', padx=4)
            outer = tk.Frame(lf, bg=BG); outer.pack(fill='both', expand=True, padx=4, pady=2)
            cv = tk.Canvas(outer, bg=BG, highlightthickness=0)
            sb = ttk.Scrollbar(outer, orient='vertical', command=cv.yview)
            rf = tk.Frame(cv, bg=BG)
            rf.bind('<Configure>', lambda e: cv.configure(scrollregion=cv.bbox('all')))
            cv.create_window((0, 0), window=rf, anchor='nw')
            cv.configure(yscrollcommand=sb.set)
            cv.pack(side='left', fill='both', expand=True)
            sb.pack(side='right', fill='y')
            return rf

        self._calib_fast_frame = _make_calib_table_frame(
            tables_frame, 0, 'Fast Calibration (P clip → ppm)', 'Clip P (mV)', 'Concentration (ppm)')
        self._calib_anal_frame = _make_calib_table_frame(
            tables_frame, 1, 'Analytical Calibration (N bulk → ppm)', 'Bulk N (mV)', 'Concentration (ppm)')

        # ---- Apply / Reset buttons ----
        btn_row = tk.Frame(body, bg=BG); btn_row.pack(fill='x', pady=(6, 0))
        self._btn_apply_calib = tk.Button(
            btn_row, text='✔  Apply Calibration', bg=ACC, fg='#fff',
            font=('Segoe UI', 10, 'bold'), relief='flat', cursor='hand2',
            padx=14, pady=6, state='disabled', command=self._apply_calibration)
        self._btn_apply_calib.pack(side='right', padx=4)
        tk.Button(btn_row, text='↺  Reset to Defaults', bg=PNL2, fg=C_DN,
                  font=('Segoe UI', 9), relief='flat', cursor='hand2',
                  padx=10, pady=6, command=self._reset_calibration_defaults).pack(side='right', padx=4)
        tk.Label(btn_row,
                 text='⚠  Apply only stores the calibration when you press Apply Calibration.',
                 bg=BG, fg='#d97706', font=('Segoe UI', 7)).pack(side='left', padx=4)

        # Initial table population
        self._refresh_calibration_table_display(None, None)

    def _calib_autofill_emf(self):
        """Read current P (fast) and N (analytical) from live/batch state and fill EMF entry fields."""
        self._calib_autofill_in_progress = True
        p_val = None
        n_val = None

        if self._live_mode and self._ic is not None:
            last = self._ic.last()
            if last is not None:
                p_val = float(last.get('P', 0.0))
                n_val = float(last.get('N', 0.0))
        elif not self._live_mode and self.Pv is not None and self.sim_idx > 0:
            idx = self.sim_idx - 1
            p_val = float(self.Pv[idx])
            n_val = float(self.N_[idx])

        if p_val is not None and n_val is not None:
            self._calib_fast_emf_var.set(f'{p_val:.4f}')
            self._calib_anal_emf_var.set(f'{n_val:.4f}')
            self._calib_fast_src.config(text=f'auto from P={p_val:.4f} mV', fg=C_AIR)
            self._calib_anal_src.config(text=f'auto from N={n_val:.4f} mV', fg=C_AIR)
        else:
            self._calib_fast_emf_var.set('')
            self._calib_anal_emf_var.set('')
            self._calib_fast_src.config(text='no live/batch data — enter manually', fg=C_DN)
            self._calib_anal_src.config(text='no live/batch data — enter manually', fg=C_DN)

        self._calib_autofill_in_progress = False

    def _get_table_emf_at_ppm(self, table, target_ppm):
        """Return the EMF value from a calibration table at the exact target_ppm breakpoint."""
        for row in table:
            emf, ppm = row[0], row[1]   # band (row[2]) ignored here
            if abs(ppm - target_ppm) < 0.01:
                return float(emf)
        return None

    def _compute_calibration_preview(self):
        """Compute scaling with cross-concentration SF adjustment. Does NOT write to self.params.

        Cross-concentration SF table (step = user-editable, default 0.05):
        ref gas →  5000   10000    20000    100000
        5000       SF×1   SF÷1.05  SF÷1.10  SF÷1.15
        10000      SF×1.05 SF×1    SF÷1.05  SF÷1.10
        20000      SF×1.10 SF×1.05  SF×1    SF÷1.05
        100000     SF×1.15 SF×1.10  SF×1.05  SF×1

        Rule: for a target ppm tier that is N steps above ref → divide SF by (1 + N*step)
              for a target ppm tier that is N steps below ref → multiply SF by (1 + N*step)
        """
        try:
            known_ppm   = float(self._calib_conc_var.get())
            fast_emf_in = float(self._calib_fast_emf_var.get())
            anal_emf_in = float(self._calib_anal_emf_var.get())
        except ValueError:
            self._calib_status.config(
                text='⚠  Invalid input — enter numeric mV values.', fg=C_DN)
            return

        try:
            sf_step = float(self._calib_sf_step_var.get())
            if sf_step <= 0:
                raise ValueError
        except ValueError:
            self._calib_status.config(
                text='⚠  Invalid SF step — must be a positive number (e.g. 0.05).', fg=C_DN)
            return

        # The four allowed calibration tiers in ascending order
        CALIB_TIERS = [5000, 10000, 20000, 100000]
        HIGH_PPM = 5000.0  # only scale rows >= this ppm

        if known_ppm not in CALIB_TIERS:
            self._calib_status.config(
                text=f'⚠  Reference gas must be one of: {CALIB_TIERS}', fg=C_DN)
            return

        ref_idx = CALIB_TIERS.index(known_ppm)  # position of ref gas in tier list

        def sf_for_target(sf_base, target_ppm):
            """Return adjusted SF for a given target ppm based on distance from ref tier."""
            if target_ppm not in CALIB_TIERS:
                return sf_base  # non-tier row: use base SF unchanged
            tgt_idx = CALIB_TIERS.index(target_ppm)
            steps = tgt_idx - ref_idx  # positive = target is higher than ref
            divisor = 1.0 + abs(steps) * sf_step
            if steps > 0:
                # target is higher concentration than ref → divide
                return sf_base / divisor
            elif steps < 0:
                # target is lower concentration than ref → multiply
                return sf_base * divisor
            else:
                # same tier → use SF as-is
                return sf_base

        # ---- Fast table ----
        fast_tbl = list(self.params.get('calib', DEFAULT_PARAMS['calib']))
        fast_ref = self._get_table_emf_at_ppm(fast_tbl, known_ppm)
        if fast_ref is None or fast_ref == 0:
            self._calib_status.config(
                text=f'⚠  {known_ppm:.0f} ppm not found in fast table or has 0 EMF.', fg=C_DN)
            return
        sf_fast_base = fast_emf_in / fast_ref

        new_fast = []
        for row in fast_tbl:
            emf, ppm, band = row[0], row[1], (row[2] if len(row) >= 3 else 0)
            if ppm >= HIGH_PPM:
                sf_adj = sf_for_target(sf_fast_base, ppm)
                new_fast.append((round(emf * sf_adj, 4), ppm, band))
            else:
                new_fast.append((emf, ppm, band))

        # ---- Analytical table ----
        anal_tbl = list(self.params.get('calib_analytical', DEFAULT_PARAMS['calib_analytical']))
        anal_ref = self._get_table_emf_at_ppm(anal_tbl, known_ppm)
        if anal_ref is None or anal_ref == 0:
            self._calib_status.config(
                text=f'⚠  {known_ppm:.0f} ppm not found in analytical table or has 0 EMF.', fg=C_DN)
            return
        sf_anal_base = anal_emf_in / anal_ref

        new_anal = []
        for row in anal_tbl:
            emf, ppm, band = row[0], row[1], (row[2] if len(row) >= 3 else 0)
            if ppm >= HIGH_PPM:
                sf_adj = sf_for_target(sf_anal_base, ppm)
                new_anal.append((round(emf * sf_adj, 4), ppm, band))
            else:
                new_anal.append((emf, ppm, band))

        # Build a human-readable SF summary for each tier
        tier_summary_parts = []
        for tp in CALIB_TIERS:
            sf_t = sf_for_target(sf_fast_base, tp)
            steps = CALIB_TIERS.index(tp) - ref_idx
            if steps == 0:
                op = '×1 (ref)'
            elif steps > 0:
                op = f'÷{1+abs(steps)*sf_step:.2f}'
            else:
                op = f'×{1+abs(steps)*sf_step:.2f}'
            tier_summary_parts.append(f'{int(tp)}ppm {op}→SF={sf_t:.4f}')

        # Store draft (not yet applied)
        self._calib_draft = {'calib': new_fast, 'calib_analytical': new_anal}

        self._calib_status.config(
            text=(
                f'✓  Ref={known_ppm:.0f}ppm  BaseF SF={sf_fast_base:.4f}  Step={sf_step}  |  '
                + '  '.join(tier_summary_parts)
                + '  — Press Apply to commit.'
            ),
            fg=C_AIR)
        self._btn_apply_calib.config(state='normal')
        self._refresh_calibration_table_display(new_fast, new_anal)

    def _apply_calibration(self):
        """Commit the draft calibration tables to self.params (and push to EditWindow)."""
        if self._calib_draft is None:
            return
        # Deep-copy so the draft cannot mutate what we store
        import copy
        new_fast = copy.deepcopy(self._calib_draft['calib'])
        new_anal = copy.deepcopy(self._calib_draft['calib_analytical'])
        # Write to params
        self.params['calib'] = new_fast
        self.params['calib_analytical'] = new_anal
        # Push to EditWindow so it stays in sync
        if hasattr(self, '_edit_win') and self._edit_win.winfo_exists():
            self._edit_win.params['calib'] = copy.deepcopy(new_fast)
            self._edit_win.params['calib_analytical'] = copy.deepcopy(new_anal)
            # Rebuild EditWindow so the table widgets reflect the new values
            try:
                self._edit_win.destroy()
            except Exception:
                pass
            self._edit_win = EditWindow(self.root, self.params, self._on_params)
            self._edit_win.withdraw()
        # Trigger recompute so live/batch data uses new calibration
        self._on_params(self.params)
        self._calib_status.config(
            text='\u2714  Calibration applied and stored in active parameters.', fg=C_AIR)
        self._btn_apply_calib.config(state='disabled')
        self._calib_draft = None
        # Refresh display to show applied values (no preview column)
        self._refresh_calibration_table_display(None, None)
        self._log('\U0001f527 Calibration applied \u2014 tables updated and recomputed', 'info')

    def _reset_calibration_defaults(self):
        """Reset calibration tables to DEFAULT_PARAMS and clear any draft."""
        import copy
        if not messagebox.askyesno('Reset Calibration',
                                    'Reset BOTH calibration tables to factory defaults?',
                                    parent=self.root):
            return
        self.params['calib'] = copy.deepcopy(DEFAULT_PARAMS['calib'])
        self.params['calib_analytical'] = copy.deepcopy(DEFAULT_PARAMS['calib_analytical'])
        self._calib_draft = None
        self._btn_apply_calib.config(state='disabled')
        self._calib_status.config(text='Tables reset to factory defaults.', fg=DIM)
        self._on_params(self.params)
        self._refresh_calibration_table_display(None, None)
        self._log('\U0001f527 Calibration reset to factory defaults', 'warn')

    def _refresh_calibration_table_display(self, preview_fast, preview_anal):
        """Re-draw both calibration tables in the Calibration tab.
        preview_fast / preview_anal: if not None, show preview values in 3rd column.
        """
        # High-ppm threshold (rows >= this get a preview/scaling highlight)
        HIGH_PPM = 5000.0

        def _clear_and_fill(frame, table, preview_table):
            for w in frame.winfo_children():
                w.destroy()
            preview_map = {}
            if preview_table is not None:
                for r in preview_table:
                    preview_map[r[1]] = r[0]  # r=(emf,ppm) or (emf,ppm,band)

            for trow in table:
                emf, ppm, band = trow[0], trow[1], (trow[2] if len(trow) >= 3 else 0)
                row_bg = BG
                row_frame = tk.Frame(frame, bg=row_bg)
                row_frame.pack(fill='x', pady=1)

                highlight = (ppm >= HIGH_PPM)
                emf_col = FG
                ppm_col = ACC if highlight else DIM

                # EMF column
                tk.Label(row_frame, text=f'{emf:.4f}', bg=row_bg, fg=emf_col,
                         font=('Segoe UI', 8, 'bold' if highlight else 'normal'),
                         width=16, anchor='w').pack(side='left', padx=4)
                # PPM column
                tk.Label(row_frame, text=f'{ppm:.0f}', bg=row_bg, fg=ppm_col,
                         font=('Segoe UI', 8, 'bold' if highlight else 'normal'),
                         width=16, anchor='w').pack(side='left', padx=4)
                # Band column (orange if non-zero)
                band_col = '#c2410c' if band > 0 else DIM
                tk.Label(row_frame, text=f'±{band:.3f}' if band > 0 else '—',
                         bg=row_bg, fg=band_col,
                         font=('Segoe UI', 8), width=8, anchor='w').pack(side='left', padx=4)
                # Preview column
                if ppm in preview_map:
                    prev_emf = preview_map[ppm]
                    changed = abs(prev_emf - emf) > 1e-6
                    prev_col = C_AIR if changed else DIM
                    prev_text = f'{prev_emf:.4f}' if changed else '(no change)'
                    tk.Label(row_frame, text=prev_text, bg=row_bg, fg=prev_col,
                             font=('Segoe UI', 8, 'bold' if changed else 'normal'),
                             width=12, anchor='w').pack(side='left', padx=4)
                elif preview_table is not None:
                    tk.Label(row_frame, text='\u2014', bg=row_bg, fg=DIM,
                             font=('Segoe UI', 8), width=12, anchor='w').pack(side='left', padx=4)

        fast_tbl = self.params.get('calib', DEFAULT_PARAMS['calib'])
        anal_tbl = self.params.get('calib_analytical', DEFAULT_PARAMS['calib_analytical'])
        _clear_and_fill(self._calib_fast_frame, fast_tbl, preview_fast)
        _clear_and_fill(self._calib_anal_frame, anal_tbl, preview_anal)

    def _prow(self,parent,label,default):
        row=tk.Frame(parent,bg=PNL); row.pack(fill='x',pady=1)
        tk.Label(row,text=label,bg=PNL,fg=DIM,font=('Segoe UI',7),anchor='w').pack(side='left',fill='x',expand=True)
        sv=tk.StringVar(value=default)
        tk.Entry(row,textvariable=sv,width=6,bg=PNL2,fg=FG,insertbackground=FG,relief='solid',bd=1,font=('Segoe UI',7),justify='right').pack(side='right')
        return sv

    def _btn(self,parent,text,cmd,bg,fg):
        b=tk.Button(parent,text=text,command=cmd,bg=bg,fg=fg,activebackground=ACC,
                    activeforeground='#fff',relief='flat',bd=0,font=('Segoe UI',8,'bold'),
                    padx=5,pady=3,cursor='hand2')
        b.pack(side='left',fill='x',expand=True,padx=1); return b

    def _log(self,msg,tag='info',t='--'):
        self.log.config(state='normal')
        self.log.insert('end',f'{str(t):>7}s  {msg}\n',tag)
        self.log.see('end'); self.log.config(state='disabled')
        # Show a dot on the Events tab when the user is on the Charts tab
        try:
            if hasattr(self,'_nb') and self._nb.index(self._nb.select())!=1:
                cur=self._nb.tab(1,'text')
                if '•' not in cur: self._nb.tab(1,text='📋  Events  •')
        except Exception: pass

    def _clear_log(self):
        self.log.config(state='normal'); self.log.delete('1.0','end')
        self.log.config(state='disabled')

    def _show_edit(self):
        if self._edit_win.winfo_exists():
            self._edit_win.deiconify(); self._edit_win.lift()
        else:
            self._edit_win=EditWindow(self.root,self.params,self._on_params)

    def _show_warmup_tare_banner(self):
        self._hide_init_overlay()
        self._hide_unstable_overlay()
        if getattr(self, '_warmup_tare_flash_active', False): return  # already showing
        self.lbl_warmup_tare.place(relx=0.5, rely=0.1, anchor='center')
        self._warmup_tare_needed = True
        self._warmup_tare_flash_active = True
        self._warmup_tare_flash_state = False
        self._do_warmup_tare_flash()

    def _do_warmup_tare_flash(self):
        if not getattr(self, '_warmup_tare_flash_active', False): return
        self._warmup_tare_flash_state = not self._warmup_tare_flash_state
        col = '#059669' if self._warmup_tare_flash_state else '#065f46'
        try:
            self.lbl_warmup_tare.config(bg=col)
        except tk.TclError:
            self._warmup_tare_flash_active = False; return
        self._warmup_tare_flash_after = self.root.after(350, self._do_warmup_tare_flash)

    def _hide_warmup_tare_banner(self):
        self._warmup_tare_flash_active = False
        if getattr(self, '_warmup_tare_flash_after', None) is not None:
            self.root.after_cancel(self._warmup_tare_flash_after)
            self._warmup_tare_flash_after = None
        self.lbl_warmup_tare.place_forget()
        self._warmup_tare_needed = False

    def _show_init_overlay(self):
        if getattr(self, '_init_overlay_active', False): return
        self._hide_unstable_overlay()
        self._hide_warmup_tare_banner()
        self._init_overlay_active = True
        self.lbl_init_warn.place(relx=0.5, rely=0.1, anchor='center')
        self._init_flash_state = False
        self._do_init_flash()

    def _do_init_flash(self):
        if not getattr(self, '_init_overlay_active', False): return
        self._init_flash_state = not self._init_flash_state
        col = '#3b82f6' if self._init_flash_state else '#1d4ed8'
        try:
            self.lbl_init_warn.config(bg=col)
        except tk.TclError:
            self._init_overlay_active = False; return
        self._init_flash_after = self.root.after(350, self._do_init_flash)

    def _hide_init_overlay(self):
        if not getattr(self, '_init_overlay_active', False): return
        self._init_overlay_active = False
        if getattr(self, '_init_flash_after', None) is not None:
            self.root.after_cancel(self._init_flash_after)
            self._init_flash_after = None
        self.lbl_init_warn.place_forget()

    def _show_unstable_overlay(self):
        if getattr(self, '_unstable_overlay_active', False): return
        self._hide_init_overlay()
        self._hide_warmup_tare_banner()
        self._unstable_overlay_active = True
        self.lbl_unstable_warn.place(relx=0.5, rely=0.1, anchor='center')
        self._unstable_flash_state = False
        self._do_unstable_flash()

    def _do_unstable_flash(self):
        if not getattr(self, '_unstable_overlay_active', False): return
        self._unstable_flash_state = not self._unstable_flash_state
        col = '#dc2626' if self._unstable_flash_state else '#991b1b'
        try:
            self.lbl_unstable_warn.config(bg=col)
        except tk.TclError:
            self._unstable_overlay_active = False; return
        self._unstable_flash_after = self.root.after(350, self._do_unstable_flash)

    def _hide_unstable_overlay(self):
        if not getattr(self, '_unstable_overlay_active', False): return
        self._unstable_overlay_active = False
        if getattr(self, '_unstable_flash_after', None) is not None:
            self.root.after_cancel(self._unstable_flash_after)
            self._unstable_flash_after = None
        self.lbl_unstable_warn.place_forget()

    def _show_proxfail_dialog(self, seed_val):
        prev_str = f'{self._prev_mother_baseline:.3f} mV' if self._prev_mother_baseline is not None else 'N/A'
        diff_str = f'{abs(seed_val - self._prev_mother_baseline):.2f} mV' if self._prev_mother_baseline is not None else 'N/A'
        msg = (
            f"Leaky EMF ({seed_val:.3f} mV) is outside ±{WARMUP_PROX_MV:.0f} mV\n"
            f"of the stored mother baseline ({prev_str}).\n"
            f"Difference: {diff_str}\n\n"
            "ARE YOU SURE THE PROBE IS NOT EXPOSED TO H2?"
        )
        return messagebox.askyesno("Baseline Proximity Check", msg, icon='warning', parent=self.root)

    _FLASH_A={'bg':'#d97706','dot':'#ffffff','name':'#ffffff','count':'#fef3c7','conc':'#ffffff','inner':'#d97706'}
    _FLASH_B={'bg':'#7c2d12','dot':'#fbbf24','name':'#fde68a','count':'#fde68a','conc':'#fbbf24','inner':'#7c2d12'}

    def _start_flash(self):
        if self._flash_active: return
        self._flash_active=True; self._flash_state=False; self._do_flash()

    def _do_flash(self):
        if not self._flash_active: return
        self._flash_state=not self._flash_state
        pal=self._FLASH_A if self._flash_state else self._FLASH_B
        d=self.flag_boxes.get(1)
        if d:
            d['frame'].config(bg=pal['bg']); d['dot'].config(bg=pal['bg'],fg=pal['dot'])
            d['name'].config(bg=pal['bg'],fg=pal['name']); d['count'].config(bg=pal['bg'],fg=pal['count'])
            d['inner'].config(bg=pal['bg'])
            if d['conc_lbl']: d['conc_lbl'].config(bg=pal['bg'],fg=pal['conc'])
        self._flash_after=self.root.after(240,self._do_flash)

    def _stop_flash(self):
        self._flash_active=False
        if self._flash_after: self.root.after_cancel(self._flash_after); self._flash_after=None

    _OR_FLASH_OVER_A={'bg':'#dc2626','dot':'#ffffff','name':'#ffffff','sub':'#fecaca'}
    _OR_FLASH_OVER_B={'bg':'#7f1d1d','dot':'#fca5a5','name':'#fecaca','sub':'#fca5a5'}
    _OR_FLASH_STAB_A={'bg':'#c2410c','dot':'#ffffff','name':'#ffffff','sub':'#fed7aa'}
    _OR_FLASH_STAB_B={'bg':'#7c2d12','dot':'#fdba74','name':'#ffedd5','sub':'#fdba74'}

    def _start_or_flash(self,which):
        self._stop_or_flash(); self._or_which=which; self._or_flash_active=True
        self._or_flash_state=False; self._do_or_flash()

    def _do_or_flash(self):
        if not self._or_flash_active: return
        self._or_flash_state=not self._or_flash_state
        pal=(self._OR_FLASH_OVER_A if self._or_flash_state else self._OR_FLASH_OVER_B) if self._or_which=='overrange' else (self._OR_FLASH_STAB_A if self._or_flash_state else self._OR_FLASH_STAB_B)
        d=self._or_box
        d['frame'].config(bg=pal['bg']); d['dot'].config(bg=pal['bg'],fg=pal['dot'])
        d['name'].config(bg=pal['bg'],fg=pal['name']); d['sub'].config(bg=pal['bg'],fg=pal['sub'])
        d['inner'].config(bg=pal['bg'])
        self.btn_or_tear.config(bg=pal['bg'])
        self._or_flash_after=self.root.after(240,self._do_or_flash)

    def _stop_or_flash(self):
        self._or_flash_active=False; self._or_which=None
        if self._or_flash_after: self.root.after_cancel(self._or_flash_after); self._or_flash_after=None
        d=self._or_box
        for w in (d['frame'],d['dot'],d['name'],d['sub'],d['inner']): w.config(bg=PNL)
        d['dot'].config(fg=BRD); d['name'].config(fg=DIM); d['sub'].config(fg=DIM)
        self.btn_or_tear.config(bg='#c2410c')

    def _start_ready_flash(self,low_leaks:bool):
        self._stop_ready_flash()
        self._ready_flash_low=low_leaks; self._ready_flash_active=True
        self._ready_flash_state=False; self._do_ready_flash()

    def _do_ready_flash(self):
        if not self._ready_flash_active: return
        self._ready_flash_state=not self._ready_flash_state
        d=self.flag_boxes.get(-1)
        if d and d.get('ready_msg'):
            bg2=d.get('_bg_now','#f0fdf4')
            if self._ready_flash_low:
                txt='◉ READY: LOW LEAKS' if self._ready_flash_state else '○ READY: LOW LEAKS'
                col=C_AIR if self._ready_flash_state else '#6ee7b7'
            else:
                txt='◉ READY: LARGE LEAKS ONLY' if self._ready_flash_state else '○ READY: LARGE LEAKS ONLY'
                col=C_UP if self._ready_flash_state else '#fcd34d'
            d['ready_msg'].config(text=txt,fg=col,bg=bg2)
        self._ready_flash_after=self.root.after(400,self._do_ready_flash)

    def _stop_ready_flash(self):
        self._ready_flash_active=False
        if self._ready_flash_after: self.root.after_cancel(self._ready_flash_after); self._ready_flash_after=None
        d=self.flag_boxes.get(-1)
        if d and d.get('ready_msg'):
            d['ready_msg'].config(text='',bg=d.get('_bg_now',PNL))

    def _update_nth_indicator(self, cur_ppm, nth_ppm_thresh, nth_normal, nth_low):
        """Update the nth-mode pill to show which n_thresh is currently active."""
        if not hasattr(self, 'lbl_nth_mode'): return
        low_active = (cur_ppm < nth_ppm_thresh)
        if low_active:
            self.lbl_nth_mode.config(
                text=f'nth: {nth_low:.4f} LOW  {cur_ppm:.0f}<{nth_ppm_thresh:.0f}ppm',
                bg='#fef9c3', fg='#854d0e')
        else:
            self.lbl_nth_mode.config(
                text=f'nth: {nth_normal:.4f} NORMAL  {cur_ppm:.0f}≥{nth_ppm_thresh:.0f}ppm',
                bg='#dcfce7', fg='#166534')

    def _update_or_box(self,or_state,t='--'):
        prev=self._last_or_state; self._last_or_state=or_state
        d=self._or_box
        # Update OR engine flag pill
        in_or = or_state in ('overrange','waiting_drop','stable')
        if hasattr(self,'lbl_or_flag'):
            if in_or:
                self.lbl_or_flag.config(text='OR ENGINE: TRUE', bg='#fef2f2', fg='#dc2626')
            else:
                self.lbl_or_flag.config(text='OR ENGINE: FALSE', bg='#f1f5f9', fg='#64748b')
        if or_state=='normal':
            self.btn_or_tear.pack_forget()
            self._calib_btn_visible=False
            if prev!='normal':
                self._stop_or_flash()
                d['name'].config(text='NORMAL',fg=DIM)
            # Always refresh sub-label with current threshold so user can see it
            d['sub'].config(text=f'Entry > {self.params.get("or_thresh",720):.0f} mV',fg=DIM)
        elif or_state=='overrange':
            self.btn_or_tear.pack_forget()
            self._calib_btn_visible=False
            if prev!='overrange':
                self._stop_flash(); self._reset_flag_boxes_for_overrange()
                self._start_or_flash('overrange')
                d['name'].config(text='⚠ OVERRANGE',fg='#ffffff')
                d['sub'].config(text='EMF > threshold',fg='#fecaca')
                if prev=='normal': self._log('⚠ OVERRANGE — all H2 logic suspended','overrange',t)
        elif or_state=='waiting_drop':
            self.btn_or_tear.pack_forget()
            self._calib_btn_visible=False
            if prev!='waiting_drop':
                self._start_or_flash('overrange')
                d['name'].config(text='⬇ WAIT DROP',fg='#ffffff')
                d['sub'].config(text=f'Wait EMF < {self.params.get("or_exit_mv",20):.0f} mV',fg='#fecaca')
                self._log('↓ Overrange exit — waiting for EMF to drop','overrange',t)
        elif or_state=='stable':
            if prev!='stable':
                self._start_or_flash('stable')
                d['name'].config(text='✔ STABLE',fg='#ffffff')
                d['sub'].config(text='SD stable — press TARE',fg='#fed7aa')
                self._log('✔ STABLE — press TEAR to set baseline and resume','stable',t)
            if not self._calib_btn_visible:
                self.btn_or_tear.config(bg='#c2410c')
                self.btn_or_tear.pack(anchor='w',pady=(1,0))
                self._calib_btn_visible=True

    def _reset_flag_boxes_for_overrange(self):
        self._reset_flag_boxes()
        d=self.flag_boxes.get(1)
        if d and d['conc_lbl']: d['conc_lbl'].config(text='',fg=DIM,bg=PNL)

    def _recompute_batch(self):
        if self.emf_arr is None: return
        params_sn=dict(self.params)
        ignore_prox = getattr(self, '_batch_ignore_prox', False)
        res=list(compute_all(self.emf_arr, params_sn, prev_mb=self._prev_mother_baseline, ignore_prox=ignore_prox))
        for c_idx in sorted(list(self._batch_calibs|self._batch_tears)):
            if c_idx>=len(self.emf_arr): continue
            new_base=float(res[0][c_idx])
            rem_emf=self.emf_arr[c_idx:]
            res_rem=list(compute_all(rem_emf, params_sn, seed_baseline=new_base, prev_mb=self._prev_mother_baseline, ignore_prox=ignore_prox))
            for i in range(len(res)): res[i][c_idx:]=res_rem[i]
        (self.C,self.D,self.E,self.FF,self.G,self.H,self.II,
         self.J,self.K,self.L,self.MB_arr,self.M,self.N_,self.O_,self.Pv,
         self.Q_,self.RC_,self.OR_STATE_arr,self.WARMUP_PHASE_arr,
         self.R_arr,self.S_arr)=res

    def _do_or_tear(self):
        t_str = '--'
        if self._live_mode and self._ic is not None:
            c_val = self._ic.C[-1] if self._ic.C else 0.0
            tear_idx = len(self._ic.emf) - 1
            if self._ic.do_manual_tear():
                self._live_state.trim_to_last()   # flush shared buffer to prevent replay of old overrange
                self._live_tears.add(tear_idx)
                t_now = len(self._ic.emf) * 0.200
                t_str = f'{t_now:.1f}'
                self._log(f' TARE (overrange stable) @ {c_val:.3f} mV — full state reset','tear',t_str)
        elif not self._live_mode and self.C is not None and self.sim_idx > 0:
            tear_idx = self.sim_idx - 1
            c_val = float(self.C[tear_idx])
            self._batch_tears.add(tear_idx)
            self._recompute_batch()
            t_now = self.times[tear_idx] if self.times is not None else tear_idx * 0.200
            t_str = f'{t_now:.1f}'
            self._log(f'TARE (overrange stable) @ {c_val:.3f} mV — full state reset','tear',t_str)
            idx = self.sim_idx; s = max(0, idx - self.WIN)
            self._update_charts(self.emf_arr[s:idx], self.C[s:idx], self.L[s:idx],
                                self.MB_arr[s:idx], self.N_[s:idx], self.Pv[s:idx],
                                self.Q_[s:idx], self.RC_[s:idx],
                                or_thr=float(self.params.get('or_thresh', 720.0)), force=True,
                                or_state_arr=self.OR_STATE_arr[s:idx] if self.OR_STATE_arr is not None else None)
        else:
            self._log(' TARE (overrange stable) — no data','warn')
            return
        self._stop_or_flash(); self._stop_flash()
        d = self._or_box
        d['name'].config(text='NORMAL', fg=DIM, bg=PNL)
        d['sub'].config(text='Torn ✓ — resumed', fg=C_AIR, bg=PNL)
        d['frame'].config(bg=PNL); d['dot'].config(bg=PNL, fg=BRD); d['inner'].config(bg=PNL)
        self.btn_or_tear.pack_forget()
        self._calib_btn_visible = False
        self._hide_init_overlay()
        self._hide_unstable_overlay()
        self._hide_warmup_tare_banner()
        self.root.update_idletasks()
        self._last_or_state = 'normal'
        # Immediately reset all flag boxes to neutral + zero ppm display
        self._reset_flag_boxes()
        d_h2 = self.flag_boxes.get(1)
        if d_h2 and d_h2.get('conc_lbl'):
            d_h2['conc_lbl'].config(text='0 ppm', fg=DIM)
        if self._live_mode:
            self._live_last_flag = None
        else:
            self._last_flag = -1
            self._current_disp_flag = -1
            self._highlight_flag(-1)
        if not self._live_mode:
            pass  # batch mode already handled above
        else:
            self._current_disp_flag = None

    def _do_manual_tear(self):
        if self._live_mode and self._ic is not None:
            c_val=self._ic.C[-1] if self._ic.C else 0.0
            tear_idx=len(self._ic.emf)-1
            if self._ic.do_manual_tear():
                self._live_state.trim_to_last()   # flush shared buffer to prevent replay of old overrange
                self._live_tears.add(tear_idx)
                t=len(self._ic.emf)*0.200
                self._hide_init_overlay()
                self._hide_unstable_overlay()
                self._hide_warmup_tare_banner()
                self._warmup_proxfail_dialog_shown = False
                self._log(f' MANUAL TARE @ {c_val:.3f} mV — full state reset (C do_tear equiv)','tear',f'{t:.1f}')
                self._check_warmup_baseline(self._ic._mother_baseline)
                # Immediately exit any overrange/stable UI state
                self._stop_or_flash(); self._stop_flash()
                self._calib_btn_visible = False
                self.btn_or_tear.pack_forget()
                d_or = self._or_box
                d_or['name'].config(text='NORMAL', fg=DIM, bg=PNL)
                d_or['sub'].config(text='Torn \u2713 \u2014 resumed', fg=C_AIR, bg=PNL)
                d_or['frame'].config(bg=PNL); d_or['dot'].config(bg=PNL, fg=BRD); d_or['inner'].config(bg=PNL)
                self._last_or_state = 'normal'
                # Immediately zero the ppm display and reset all flag boxes to neutral
                # so the UI doesn't appear frozen/stuck during the blank window.
                self._reset_flag_boxes()
                d_h2 = self.flag_boxes.get(1)
                if d_h2 and d_h2.get('conc_lbl'):
                    d_h2['conc_lbl'].config(text='0 ppm', fg=DIM)
                # Use None so next real transition fires fresh (no spurious AIR log)
                self._live_last_flag = None
                self._current_disp_flag = None
        elif not self._live_mode and self.C is not None and self.sim_idx>0:
            tear_idx=self.sim_idx-1; c_val=float(self.C[tear_idx])
            self._batch_tears.add(tear_idx); self._recompute_batch()
            t=self.times[tear_idx] if self.times is not None else tear_idx*0.200
            self._hide_init_overlay()
            self._hide_unstable_overlay()
            self._hide_warmup_tare_banner()
            self._log(f' MANUAL TARE @ {c_val:.3f} mV — full state reset, recomputed','tear',f'{t:.1f}')
            self._last_flag = -1
            self._current_disp_flag = -1
            self._highlight_flag(-1)
            idx=self.sim_idx; s=max(0,idx-self.WIN)
            self._update_charts(self.emf_arr[s:idx], self.C[s:idx], self.L[s:idx],
                                self.MB_arr[s:idx], self.N_[s:idx], self.Pv[s:idx],
                                self.Q_[s:idx], self.RC_[s:idx],
                                or_thr=float(self.params.get('or_thresh',720.0)), force=True,
                                or_state_arr=self.OR_STATE_arr[s:idx] if self.OR_STATE_arr is not None else None)
        else:
            messagebox.showinfo('Tear','No data available to tear against.')

    def _do_poweroff(self):
        can_poweroff=False; current_mother=None
        if self._live_mode and self._ic is not None:
            last=self._ic.last()
            if last is not None:
                can_poweroff=(self._live_last_flag==-1)
                current_mother=last.get('mother_baseline',None)
        elif not self._live_mode and self.C is not None and self.sim_idx>0:
            can_poweroff=(self._last_flag==-1)
            if self.MB_arr is not None: current_mother=float(self.MB_arr[self.sim_idx-1])
        else:
            can_poweroff=True
        if not can_poweroff:
            self._show_poweroff_warning(); return
        saved=False
        if current_mother is not None:
            saved=_save_memory(current_mother)
            if saved:
                self._prev_mother_baseline=current_mother
                self._memory=_load_memory()
                self._update_prev_mother_display()
                self._log(f'⏻ POWER OFF — mother BL saved: {current_mother:.3f} mV','poweroff')
            else:
                self._log('⏻ POWER OFF — WARNING: could not save BL to memory','warn')
        self._show_poweroff_overlay(current_mother,saved)

    def _show_poweroff_warning(self):
        if self._poweroff_warn_active: return
        self._poweroff_warn_active=True
        warn_lbl=tk.Label(self.root,
            text='⚠  BRING SENSOR TO AMBIENT CONDITION FIRST\n(Wait for AIR / BASELINE state)',
            bg='#dc2626',fg='#ffffff',font=('Segoe UI',12,'bold'),relief='flat',padx=18,pady=10)
        warn_lbl.place(relx=0.5,rely=0.5,anchor='center')
        self._log('⚠ Power-off blocked — sensor not in AIR/BASELINE state','warn')
        _flash_count=[0]
        def _flash():
            if not warn_lbl.winfo_exists(): return
            _flash_count[0]+=1
            col='#dc2626' if _flash_count[0]%2==0 else '#7f1d1d'
            warn_lbl.config(bg=col)
            if _flash_count[0]<6: self.root.after(300,_flash)
            else: self.root.after(800,lambda: (warn_lbl.destroy(), setattr(self,'_poweroff_warn_active',False)))
        _flash()

    def _show_poweroff_overlay(self,mother_val,saved):
        overlay=tk.Frame(self.root,bg='#1e293b')
        overlay.place(x=0,y=0,relwidth=1,relheight=1)
        tk.Label(overlay,text='⏻',bg='#1e293b',fg='#dc2626',font=('Segoe UI',40)).pack(pady=(60,8))
        tk.Label(overlay,text='SYSTEM POWERED OFF',bg='#1e293b',fg='#f1f5f9',font=('Segoe UI',18,'bold')).pack()
        if mother_val is not None and saved:
            tk.Label(overlay,text=f'Mother Baseline saved: {mother_val:.3f} mV',
                     bg='#1e293b',fg=C_MOTHER,font=('Segoe UI',12)).pack(pady=(12,3))
            ts=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            tk.Label(overlay,text=f'Saved at: {ts}',bg='#1e293b',fg='#64748b',font=('Segoe UI',9)).pack()
        else:
            tk.Label(overlay,text='(No baseline data saved)',bg='#1e293b',fg='#64748b',font=('Segoe UI',10)).pack(pady=12)
        tk.Label(overlay,text='Close the application window to exit,\nor press Resume to continue.',
                 bg='#1e293b',fg='#94a3b8',font=('Segoe UI',9)).pack(pady=(24,12))
        tk.Button(overlay,text='▶  RESUME SESSION',bg=C_AIR,fg='#ffffff',font=('Segoe UI',10,'bold'),
                  relief='flat',cursor='hand2',padx=20,pady=8,command=overlay.destroy).pack()
        tk.Button(overlay,text='✕  EXIT APPLICATION',bg='#dc2626',fg='#ffffff',font=('Segoe UI',9),
                  relief='flat',cursor='hand2',padx=14,pady=6,command=self.root.destroy).pack(pady=(6,0))

    def _update_charts(self, raw, C, L, MB, N, Pv, Q, RC, or_thr=720.0, force=False, or_state_arr=None):
        now_ms = time.monotonic() * 1000
        if not force and now_ms - self._last_chart_ms < self.CHART_EVERY: return
        if len(raw) < 2: return
        self._last_chart_ms = now_ms
        self._canvas_chart.update(
            list(raw), list(C), list(L), list(MB),
            list(N), list(Pv), list(Q), list(RC), or_thr=or_thr,
            or_state_arr=list(or_state_arr) if or_state_arr is not None else None
        )

    def _draw_prog(self,pct):
        if not self._prog_w: return
        self._prog_cv.delete('all')
        self._prog_cv.create_rectangle(0,0,int(self._prog_w*pct/100),3,fill=ACC,width=0)

    def _reset_flag_boxes(self):
        self._stop_flash(); self._stop_ready_flash()
        for d in self.flag_boxes.values():
            for w in (d['frame'],d['dot'],d['name'],d['count'],d['inner']): w.config(bg=PNL)
            if d['conc_lbl']: d['conc_lbl'].config(bg=PNL)
            d['dot'].config(fg=BRD); d['name'].config(fg=DIM)
            d['count'].config(fg=DIM,text=f"{d['events']} events")
            if d['conc_lbl']: d['conc_lbl'].config(fg=DIM,text='')
            if d['rec_bar']:  d['rec_bar']['value']=0
            if d.get('rec_msg'): d['rec_msg'].config(text='0%',fg=C_REC,bg=PNL)
            if d.get('ready_msg'): d['ready_msg'].config(text='',bg=PNL)
            d['_bg_now']=PNL

    def _highlight_flag(self,fval):
        self._stop_flash(); self._stop_ready_flash()
        self._reset_flag_boxes()
        d=self.flag_boxes.get(fval)
        if not d: return
        col=d['col']; bg2=d['bg']
        for w in (d['frame'],d['dot'],d['name'],d['count'],d['inner']): w.config(bg=bg2)
        if d['conc_lbl']: d['conc_lbl'].config(bg=bg2)
        if d.get('rec_msg'): d['rec_msg'].config(bg=bg2)
        if d.get('ready_msg'): d['ready_msg'].config(bg=bg2)
        d['_bg_now']=bg2
        d['dot'].config(fg=col); d['name'].config(fg=col)
        d['count'].config(fg=col,text=f"{d['events']} events")
        if d['conc_lbl']: d['conc_lbl'].config(fg=C_CONC)
        if fval==1: self._start_flash()

    def _update_rec_box(self, rec):
        d=self.flag_boxes.get(-3)
        if not d: return
        if d['rec_bar']: d['rec_bar']['value']=min(100,rec)
        if d.get('rec_msg'):
            bg2 = d.get('_bg_now', PNL)
            d['rec_msg'].config(text=f'{rec:.1f}%',fg=C_REC,bg=bg2)

    def _update_ready_box(self, daughter_mv, mother_mv, post_high_active=False):
        d=self.flag_boxes.get(-1)
        if not d or not d.get('ready_msg'): return
        if post_high_active:
            # Only show LARGE LEAKS ONLY when truly back in AIR (flag -1), rec=100
            # Never show LOW LEAKS during post-high counter — block that path entirely
            if self._current_disp_flag != -1:
                self._stop_ready_flash()
                d['ready_msg'].config(text='')
                return
            # In AIR: always large-leaks-only, never low-leaks
            if not self._ready_flash_active or self._ready_flash_low:
                self._start_ready_flash(low_leaks=False)
            return
        # Normal path: only show ready text when in AIR state
        if self._current_disp_flag != -1:
            self._stop_ready_flash()
            d['ready_msg'].config(text='')
            return
        low_leaks = self._daughter_near_mother(daughter_mv, mother_mv)
        if not self._ready_flash_active or self._ready_flash_low != low_leaks:
            self._start_ready_flash(low_leaks)

    def _update_metrics(self,v):
        fmts={'C':'.2f','M':'.3f','J':'.5f','REC':'.1f','N':'.4f','O':'d','P':'.4f','Q':'.0f','R':'.0f','S':'.0f'}
        cols={'C':FG,'M':FG,'J':DIM,'REC':C_REC,'N':C_CONC,'O':C_CONC,'P':C_CONC,'Q':C_CONC,'R':C_CONC,'S':C_CONC}
        for k,fmt in fmts.items():
            if k in self.mv and k in v:
                try:
                    val=v[k]; txt=(f'{int(val)}' if fmt=='d' else f'{val:{fmt}}')
                    self.mv[k].config(text=txt,fg=cols.get(k,FG))
                except: pass
        # ΔmV sub-labels: ppm Fast clips at Pv (=P), ppm Analyt clips at N_
        if hasattr(self,'mv_emf'):
            try:
                p_val=float(v.get('P',0.0))
                if 'Q' in self.mv_emf: self.mv_emf['Q'].config(text=f'Δ={p_val:.3f} mV')
            except: pass
            try:
                n_val=float(v.get('N',0.0))
                if 'R' in self.mv_emf: self.mv_emf['R'].config(text=f'Δ={n_val:.4f} mV')
            except: pass
        if 'mother_baseline' in v:
            try:
                val=float(v['mother_baseline'])
                if hasattr(self,'mb_lbl'): self.mb_lbl.config(text=f"{val:.3f} mV",fg=C_MOTHER)
            except: pass
        if 'daughter_baseline' in v:
            try:
                val=float(v['daughter_baseline'])
                if hasattr(self,'db_lbl'): self.db_lbl.config(text=f"{val:.3f} mV",fg=C_BAS)
            except: pass

    def _get_disp_flag(self, raw_flag, rec):
        if raw_flag == -1:
            return -1 if rec >= 99.5 else -3
        elif raw_flag == 1:
            return 1
        return -1

    def _browse(self):
        path=filedialog.askopenfilename(filetypes=[('CSV','*.csv'),('All','*.*')])
        if not path: return
        try:
            rows=load_csv(path); self.raw_data=rows
            name=os.path.basename(path); maxt=rows[-1][0]
            self.lbl_info.config(text=f'{name}  ({len(rows):,} pts, {maxt:.0f} s)')
            self.e_t1.set(str(int(np.ceil(maxt))))
            self._reset(); self.btn_play.config(state='normal')
            self.btn_reset.config(state='normal')
            self._clear_log(); self._log('ready','info')
            self._live_mode=False; self.lbl_live.config(text='')
            self.btn_tear.config(state='normal')
            self.btn_poweroff.config(state='normal')
        except Exception as ex:
            messagebox.showerror('Load Error',str(ex))

    def _play(self):
        if self.running: return

        if self.times is not None and 0 < self.sim_idx < len(self.times):
            self.running = True
            self.btn_play.config(state='disabled')
            self.btn_pause.config(state='normal')
            self._tick()
            self._log('resumed playback', 'info')
            return

        self._batch_calibs.clear(); self._batch_tears.clear()
        self._batch_ignore_prox = False
        self._batch_proxfail_shown = False
        self._batch_wait_instability = False
        t0=float(self.e_t0.get()); t1=float(self.e_t1.get())
        filtered=[(t,e) for t,e in self.raw_data if t0<=t<=t1]
        if not filtered: messagebox.showwarning('No Data','No data in window.'); return
        self._clear_log()
        warmup=int(self.params.get('warmup_samples',BASELINE_WARMUP_SAMPLES))
        self._log(f'computing {len(filtered):,} samples  (warmup min {warmup*0.200:.0f} s, SD < {WARMUP_SD_THRESH} gate)','info')
        times_arr=np.array([d[0] for d in filtered]); emf_arr=np.array([d[1] for d in filtered])
        params_sn=dict(self.params)
        def _do_compute():
            res=compute_all(emf_arr, params_sn, prev_mb=self._prev_mother_baseline); self._compute_q.put((times_arr,emf_arr,res))
        threading.Thread(target=_do_compute,daemon=True).start()
        self._poll_compute()

    def _poll_compute(self):
        try: times_arr,emf_arr,res=self._compute_q.get_nowait()
        except queue.Empty: self.root.after(50,self._poll_compute); return
        self.times=times_arr; self.emf_arr=emf_arr
        (self.C,self.D,self.E,self.FF,self.G,self.H,self.II,
         self.J,self.K,self.L,self.MB_arr,self.M,self.N_,self.O_,self.Pv,
         self.Q_,self.RC_,self.OR_STATE_arr,self.WARMUP_PHASE_arr,
         self.R_arr,self.S_arr)=res
        self._log(f'playing {len(self.times):,} samples','info')
        self.sim_idx=0; self.running=True
        self._last_flag=None; self._last_chart_ms=0; self._last_or_state='normal'
        self._calib_offset=0; self._current_disp_flag=None
        self._reset_post_high_state()
        for v in self.flag_boxes: self.flag_boxes[v]['events']=0
        self._reset_flag_boxes(); self._stop_or_flash()
        self._hide_init_overlay(); self._hide_unstable_overlay(); self._hide_warmup_tare_banner()
        d=self._or_box
        d['name'].config(text='NORMAL',fg=DIM,bg=PNL); d['sub'].config(text='EMF in range',fg=DIM,bg=PNL)
        d['frame'].config(bg=PNL); d['dot'].config(bg=PNL,fg=BRD); d['inner'].config(bg=PNL)
        self.btn_or_tear.pack_forget(); self._calib_btn_visible=False
        self.btn_play.config(state='disabled'); self.btn_pause.config(state='normal')
        self._tick()

    def _pause(self):
        self.running=False
        if self._after_id: self.root.after_cancel(self._after_id); self._after_id=None
        self._stop_flash(); self._stop_or_flash(); self._stop_ready_flash()
        self._hide_init_overlay(); self._hide_unstable_overlay(); self._hide_warmup_tare_banner()
        self.btn_play.config(state='normal'); self.btn_pause.config(state='disabled')
        self._log('paused','info')

    def _reset(self):
        self.running=False
        self._batch_proxfail_shown = False
        self._batch_ignore_prox = False
        self._batch_wait_instability = False
        if self._after_id: self.root.after_cancel(self._after_id); self._after_id=None
        self._stop_flash(); self._stop_or_flash(); self._stop_ready_flash()
        self._hide_init_overlay(); self._hide_unstable_overlay(); self._hide_warmup_tare_banner()
        self.sim_idx=0; self._last_flag=None; self._draw_prog(0)
        self._last_or_state='normal'; self._calib_offset=0; self._current_disp_flag=None
        self.WARMUP_PHASE_arr=None
        self.R_arr=None; self.S_arr=None
        self._reset_post_high_state()
        self.btn_play.config(state='normal' if self.raw_data else 'disabled')
        self.btn_pause.config(state='disabled')
        self.lbl_stats.config(text='t=--  emf=--  Δ=--  SD=--  ppm=--  rec=--%')
        for lbl in self.mv.values(): lbl.config(text='--',fg=DIM)
        for v in self.flag_boxes: self.flag_boxes[v]['events']=0
        self._reset_flag_boxes()
        d=self._or_box
        d['name'].config(text='NORMAL',fg=DIM,bg=PNL); d['sub'].config(text='EMF in range',fg=DIM,bg=PNL)
        d['frame'].config(bg=PNL); d['dot'].config(bg=PNL,fg=BRD); d['inner'].config(bg=PNL)
        self.btn_or_tear.pack_forget(); self._calib_btn_visible=False
        if hasattr(self,'lbl_or_flag'): self.lbl_or_flag.config(text='OR ENGINE: FALSE',bg='#f1f5f9',fg='#64748b')
        if hasattr(self,'mb_lbl'): self.mb_lbl.config(text='--',fg=DIM)
        if hasattr(self,'db_lbl'): self.db_lbl.config(text='--',fg=DIM)
        if hasattr(self, '_canvas_chart'):
            self._canvas_chart._cv1.delete('all')
            self._canvas_chart._cv2.delete('all')

    def _tick(self):
        if not self.running: return
        spd=self.spd_var.get(); step=max(1,min(int(spd*1.5),2000))
        end=min(self.sim_idx+step,len(self.times)); self.sim_idx=end; idx=end
        if idx<2: self._after_id=self.root.after(self.INTERVAL,self._tick); return

        t=self.times[idx-1]; e=self.emf_arr[idx-1]
        dlt=self.M[idx-1]; sd=self.J[idx-1]
        ppm=self.S_arr[idx-1] if self.S_arr is not None else self.Q_[idx-1]
        rec=self.RC_[idx-1]
        or_state=str(self.OR_STATE_arr[idx-1]) if self.OR_STATE_arr is not None else 'normal'
        daughter_mv=float(self.L[idx-1]); mother_mv=float(self.MB_arr[idx-1])

        phase = str(self.WARMUP_PHASE_arr[idx-1]) if self.WARMUP_PHASE_arr is not None else 'running'
        warmup = int(self.params.get('warmup_samples', BASELINE_WARMUP_SAMPLES))

        if getattr(self, '_batch_wait_instability', False):
            start_w = max(0, idx - warmup)
            sd_67 = float(np.std(self.C[start_w:idx])) if idx > start_w + 1 else 0.0
            if sd_67 >= WARMUP_SD_THRESH:
                self._batch_wait_instability = False
                self._batch_proxfail_shown = False
            phase = 'waiting'

        if phase == 'waiting':
            if idx <= warmup:
                self._hide_unstable_overlay()
                self._hide_warmup_tare_banner()
                self._show_init_overlay()
            else:
                self._hide_init_overlay()
                self._show_unstable_overlay()
                self._hide_warmup_tare_banner()

        elif phase == 'sd_ok_proxfail':
            self._hide_init_overlay()
            if not getattr(self, '_batch_proxfail_shown', False):
                self._pause()
                self._batch_proxfail_shown = True
                start_i = max(0, idx - warmup)
                seed_val = sum(self.C[start_i:idx]) / (idx - start_i) if idx > start_i else (self.C[idx-1] if self.C else 0.0)

                user_yes = self._show_proxfail_dialog(seed_val)
                if user_yes:
                    self._batch_ignore_prox = True
                    self._recompute_batch()
                    phase = str(self.WARMUP_PHASE_arr[idx-1])
                    self._hide_unstable_overlay()
                    self._show_warmup_tare_banner()
                    self._log(f'✓ User confirmed — baseline seeded at {seed_val:.3f} mV — press TARE','info')
                else:
                    self._batch_wait_instability = True
                    self._show_unstable_overlay()
                    self._log('↺ User aborted — waiting for probe to be moved (SD spike)','warn')

                self.running = True
                self.btn_play.config(state='disabled')
                self.btn_pause.config(state='normal')
            else:
                self._show_unstable_overlay()

        elif phase == 'ready_for_tare':
            self._hide_init_overlay()
            self._hide_unstable_overlay()
            self._show_warmup_tare_banner()

        elif phase == 'running':
            self._hide_init_overlay()
            self._hide_unstable_overlay()
            self._hide_warmup_tare_banner()

        or_flag_int = 1 if or_state in ('overrange','waiting_drop','stable') else 0
        ph_str = f'  ⚠LGE:{self._post_high_counter}/{int(self.params.get("post_high_counter_limit",6000))}' if self._post_high_active else ''
        self.lbl_stats.config(text=f't={t:.1f}s  emf={e:.2f}mV  Δ={dlt:.3f}  SD={sd:.5f}  ppm={ppm:.0f}  rec={rec:.0f}%  OR:{or_flag_int}{ph_str}')
        # Update nth-mode indicator using current ppm
        _nth_lo  = float(self.params.get('n_thresh_low', 0.0033))
        _nth_n   = float(self.params.get('n_thresh', 0.001))
        _nth_thr = float(self.params.get('n_thresh_ppm_thresh', 1000.0))
        _cur_ppm_batch = float(self.S_arr[idx-1]) if self.S_arr is not None else 0.0
        self._update_nth_indicator(_cur_ppm_batch, _nth_thr, _nth_n, _nth_lo)
        self._draw_prog(idx/len(self.times)*100)
        self._update_or_box(or_state,f'{t:.1f}')
        in_or=(or_state in ('overrange','waiting_drop','stable'))

        if not in_or and phase == 'running':
            raw_flag=float(self.II[idx-1])
            if idx>=2 and self.II[idx-2]==1 and raw_flag==-1: disp_flag=-2
            else: disp_flag=self._get_disp_flag(raw_flag,rec)

            # ── Post-high-concentration limiting counter (batch mode) ──────────
            conc_thresh   = float(self.params.get('post_high_conc_thresh',  10000.0))
            counter_limit = int(self.params.get('post_high_counter_limit',  6000))
            if self._post_high_active:
                self._post_high_counter += step
                if self._post_high_counter >= counter_limit:
                    self._post_high_active = False
                    self._post_high_counter = 0
                    self._post_high_saw_high = False
                    self._log(f'▶ Post-high counter done — resuming normal sensitivity','info',f'{t:.1f}')
            else:
                # Stage 1: track whether ppm crossed threshold during UP phase
                if disp_flag == 1 or raw_flag == 1.0:
                    if ppm >= conc_thresh:
                        self._post_high_saw_high = True
                # Stage 2: arm counter when DOWN/recovering/air appears after high reading
                if self._post_high_saw_high and disp_flag in (-2, -3, -1):
                    self._post_high_active = True
                    self._post_high_counter = 0
                    self._post_high_peak_ppm = ppm
                    self._post_high_saw_high = False
                    self._log(f'⚠ Post-high limiting armed ({conc_thresh:.0f} ppm threshold crossed) → LARGE LEAKS ONLY for {counter_limit} samples','warn',f'{t:.1f}')
            # ─────────────────────────────────────────────────────────────────

            if disp_flag!=self._last_flag:
                if disp_flag in self.flag_boxes: self.flag_boxes[disp_flag]['events']+=1
                self._last_flag=disp_flag; self._current_disp_flag=disp_flag
                self._highlight_flag(disp_flag)
                lbl_map={-1:'→ AIR / BASELINE (recovered)',1:'→ H2 CONFIRMED ▲',-2:'→ H2 DOWN ▼',-3:'→ RECOVERING'}
                tag_map={-1:'air',1:'up',-2:'dn',-3:'rec'}
                self._log(lbl_map.get(disp_flag,f'→{disp_flag}'),tag_map.get(disp_flag,'info'),f'{t:.1f}')
                if disp_flag==-1: self.btn_poweroff.config(state='normal')

            ocap=int(self.params['o_cap'])
            if idx>1 and self.O_[idx-1]==ocap and self.O_[idx-2]<ocap:
                self._log(f'★ 6 s snapshot → {ppm:.0f} ppm  (P={self.Pv[idx-1]:.4f} mV)','conc',f'{t:.1f}')

            if raw_flag==1:
                d=self.flag_boxes.get(1)
                if d and d['conc_lbl']:
                    d['conc_lbl'].config(text=f'{ppm:.0f} ppm',
                                          fg=C_CONC if not self._flash_active else '#ffffff')

            self._update_rec_box(rec)

        # Always update ready box (post-high limiting must show even outside AIR flag)
        self._update_ready_box(daughter_mv,mother_mv,post_high_active=self._post_high_active)
        # Also update counter indicator every tick
        self._update_post_high_indicator()

        self._update_metrics(dict(
            C=self.C[idx-1],M=self.M[idx-1],J=self.J[idx-1],
            N=self.N_[idx-1],O=self.O_[idx-1],P=self.Pv[idx-1],
            Q=self.Q_[idx-1],REC=rec,
            R=self.R_arr[idx-1] if self.R_arr is not None else self.Q_[idx-1],
            S=self.S_arr[idx-1] if self.S_arr is not None else self.Q_[idx-1],
            mother_baseline=mother_mv,daughter_baseline=daughter_mv))
        s=max(0,idx-self.WIN)
        self._update_charts(self.emf_arr[s:idx], self.C[s:idx], self.L[s:idx],
                            self.MB_arr[s:idx], self.N_[s:idx], self.Pv[s:idx],
                            self.Q_[s:idx], self.RC_[s:idx],
                            or_thr=float(self.params.get('or_thresh',720.0)),
                            or_state_arr=self.OR_STATE_arr[s:idx] if self.OR_STATE_arr is not None else None)

        if idx>=len(self.times):
            self.running=False; self.btn_play.config(state='normal')
            self.btn_pause.config(state='disabled'); self._draw_prog(100); self._stop_flash()
            self._hide_init_overlay(); self._hide_unstable_overlay(); self._hide_warmup_tare_banner()
            self._log(f'complete — {len(self.times):,} samples','info'); return
        self._after_id=self.root.after(self.INTERVAL,self._tick)

    def _browse_live(self):
        path=filedialog.askopenfilename(title='Select Live Log File',
                                         filetypes=[('Log','*.log'),('Text','*.txt'),('All','*.*')])
        if not path: return
        self._start_live(path)

    def _start_live(self,path):
        self._stop_live(silent=True)
        if self.running: self._pause()
        self._live_mode=True; self._live_state.reset()
        self._live_calibs.clear(); self._live_tears.clear()
        self._ic=IncrementalCompute(self.params, prev_mb=self._prev_mother_baseline)
        self._live_last_flag=None; self._last_chart_ms=0
        self._live_warmup_done=False; self._last_or_state='normal'
        self._calib_btn_visible=False; self._current_disp_flag=None
        self._warmup_proxfail_dialog_shown = False
        self._reset_post_high_state()
        for v in self.flag_boxes: self.flag_boxes[v]['events']=0
        self._reset_flag_boxes(); self._stop_or_flash()
        self._hide_init_overlay(); self._hide_unstable_overlay(); self._hide_warmup_tare_banner()
        d=self._or_box
        d['name'].config(text='NORMAL',fg=DIM,bg=PNL); d['sub'].config(text='EMF in range',fg=DIM,bg=PNL)
        d['frame'].config(bg=PNL); d['dot'].config(bg=PNL,fg=BRD); d['inner'].config(bg=PNL)
        self.btn_or_tear.pack_forget()
        name=os.path.basename(path); self.lbl_info.config(text=f'LIVE: {name}')
        self.lbl_live.config(text='● LIVE',fg=C_AIR)
        self.btn_live_stop.config(state='normal')
        self.btn_tear.config(state='normal')
        self.btn_poweroff.config(state='normal')
        self.btn_play.config(state='disabled')
        self._clear_log()
        warmup=int(self.params.get('warmup_samples',BASELINE_WARMUP_SAMPLES))
        self._log(f'Live — warmup: {warmup} samples ({warmup*0.200:.0f} s min), SD < {WARMUP_SD_THRESH} gate','warn')
        self._log(f'Keep probe in H2-free air. Flashing overlay = NOT STABLE.','warn')
        if self._prev_mother_baseline is not None:
            ts=self._memory.get('timestamp','')
            self._log(f'Stored mother BL: {self._prev_mother_baseline:.3f} mV  [{ts[:16]}]','info')
        self._update_prev_mother_display()
        self._show_init_overlay()
        self._live_thread=threading.Thread(target=self._log_reader_thread,args=(path,self._live_state),daemon=True)
        self._live_thread.start()
        self._live_poll()

    def _stop_live(self,silent=False):
        if self._live_after: self.root.after_cancel(self._live_after); self._live_after=None
        self._live_state.stop(); self._live_mode=False; self.lbl_live.config(text='')
        self.btn_live_stop.config(state='disabled')
        self._stop_flash(); self._stop_or_flash(); self._stop_ready_flash()
        self._hide_init_overlay(); self._hide_unstable_overlay(); self._hide_warmup_tare_banner()
        if hasattr(self,'lbl_or_flag'): self.lbl_or_flag.config(text='OR ENGINE: FALSE',bg='#f1f5f9',fg='#64748b')
        self.btn_play.config(state='normal' if self.raw_data else 'disabled')
        if not silent: self._log('live stopped','info')
    def _log_reader_thread(self,path,state):
        try:
            with open(path,'r',errors='replace') as f:
                for raw_line in f:
                    if state.should_stop(): return
                    v=parse_log_emf(raw_line)
                    if v is not None: state.push(v)
                buf=''
                while not state.should_stop():
                    chunk=f.read(512)
                    if not chunk: time.sleep(0.02); continue
                    buf+=chunk; lines=buf.split('\n'); buf=lines[-1]
                    for raw_line in lines[:-1]:
                        v=parse_log_emf(raw_line)
                        if v is not None: state.push(v)
        except Exception: pass

    def _live_poll(self):
        if not self._live_mode: return
        emf_list,new_count=self._live_state.consume()
        warmup=int(self.params.get('warmup_samples',BASELINE_WARMUP_SAMPLES))

        if new_count>0 and self._ic is not None:
            start=len(self._ic.emf)
            for v in emf_list[start:]: self._ic.step(v)

            if not self._live_warmup_done:
                phase = self._ic._warmup_phase

                if phase == 'waiting_for_instability':
                    self._hide_init_overlay()
                    self._show_unstable_overlay()

                elif phase == 'waiting':
                    if self._ic.i <= warmup:
                        self._hide_unstable_overlay()
                        self._show_init_overlay()
                    else:
                        self._hide_init_overlay()
                        self._show_unstable_overlay()

                elif phase == 'sd_ok_proxfail' and not self._warmup_proxfail_dialog_shown:
                    self._hide_init_overlay()
                    self._warmup_proxfail_dialog_shown = True
                    seed_val = self._ic._warmup_seed_val or (self._ic.C[-1] if self._ic.C else 0.0)
                    self._log(f'⚠ SD ok but EMF ({seed_val:.3f} mV) outside ±{WARMUP_PROX_MV:.0f} mV of prev BL — prompting user','warn')
                    user_yes = self._show_proxfail_dialog(seed_val)
                    if user_yes:
                        self._ic._ignore_prox = True
                        self._ic._daughter_baseline = seed_val
                        self._ic._mother_baseline   = seed_val
                        self._ic._baseline_seeded   = True
                        self._ic._warmup_phase      = 'ready_for_tare'
                        if self._ic.L:  self._ic.L[-1]  = seed_val
                        if self._ic.MB: self._ic.MB[-1] = seed_val
                        self._log(f'✓ User confirmed — baseline seeded at {seed_val:.3f} mV — press TARE','info')
                        self._show_warmup_tare_banner()
                    else:
                        self._ic._warmup_phase = 'waiting_for_instability'
                        self._warmup_proxfail_dialog_shown = False
                        self._log('↺ User aborted — waiting for probe to be moved (SD spike)','warn')
                        self._show_unstable_overlay()

                elif phase == 'ready_for_tare':
                    self._hide_init_overlay()
                    self._hide_unstable_overlay()
                    self._show_warmup_tare_banner()

                elif phase == 'running':
                    self._hide_init_overlay()
                    self._hide_unstable_overlay()
                    self._hide_warmup_tare_banner()

            if self._ic._baseline_seeded and self._warmup_tare_needed == False and self._live_warmup_done == False:
                pass

            if not self._warmup_tare_needed and self._ic._baseline_seeded and not self._live_warmup_done:
                if self._ic.i > warmup + 2:
                    self._live_warmup_done = True

            last=self._ic.last()
            if last is None:
                self._live_after=self.root.after(self.INTERVAL,self._live_poll); return

            idx=len(self._ic.emf); t=idx*0.200; rec=last['REC']
            # Always read OR state from the live engine state, not the stale last() dict.
            # This ensures that immediately after a tare (which resets _or_state='normal'),
            # the UI exits overrange/stable without waiting for the next step() call.
            or_state=self._ic._or_state
            daughter_mv=last.get('daughter_baseline',0.0)
            mother_mv=last.get('mother_baseline',0.0)

            ws = (last.get('warmup_phase', 'waiting') in ('waiting', 'waiting_for_instability'))
            if ws and not self._warmup_tare_needed:
                if self._ic.i <= warmup:
                    self._hide_unstable_overlay()
                    self._show_init_overlay()
                else:
                    self._hide_init_overlay()
                    self._show_unstable_overlay()
            elif not ws and not self._warmup_tare_needed and self._ic._baseline_seeded:
                self._hide_init_overlay()
                self._hide_unstable_overlay()

            or_flag_int = 1 if or_state in ('overrange','waiting_drop','stable') else 0
            ph_str = f'  ⚠LGE:{self._post_high_counter}/{int(self.params.get("post_high_counter_limit",6000))}' if self._post_high_active else ''
            self.lbl_stats.config(text=f't={t:.1f}s  emf={self._ic.emf[-1]:.2f}mV  Δ={last["M"]:.3f}  SD={last["J"]:.5f}  ppm={last["S"]:.0f}  rec={rec:.0f}%  OR:{or_flag_int}{ph_str}')
            # Update nth-mode indicator
            _nth_lo  = float(self.params.get('n_thresh_low', 0.0033))
            _nth_n   = float(self.params.get('n_thresh', 0.001))
            _nth_thr = float(self.params.get('n_thresh_ppm_thresh', 1000.0))
            _cur_ppm = float(last.get('S', 0.0))
            self._update_nth_indicator(_cur_ppm, _nth_thr, _nth_n, _nth_lo)
            self._update_or_box(or_state,f'{t:.1f}')
            in_or=(or_state in ('overrange','waiting_drop','stable'))

            if not in_or and self._live_warmup_done:
                raw_flag=float(last['II'])
                if idx>=2 and self._ic.II[-2]==1 and raw_flag==-1: disp_flag=-2
                else: disp_flag=self._get_disp_flag(raw_flag,rec)

                # ── Post-high-concentration limiting counter (live mode) ───────
                conc_thresh   = float(self.params.get('post_high_conc_thresh',  10000.0))
                counter_limit = int(self.params.get('post_high_counter_limit',  6000))
                limited_upG   = float(self.params.get('post_high_upG',  10.0))
                limited_inG   = float(self.params.get('post_high_inG',  0.2))
                cur_ppm = float(last.get('S', 0.0))

                if self._post_high_active:
                    # Counter running — keep overriding gates and tick
                    self._ic.p['upG'] = limited_upG
                    self._ic.p['inG'] = limited_inG
                    # ── Re-trigger check: if threshold crossed AGAIN while counter
                    #    is running, track it so we can reset on the next DOWN flag ──
                    if disp_flag == 1 or raw_flag == 1.0:
                        if cur_ppm >= conc_thresh:
                            self._post_high_saw_high = True
                    # If a new high event just ended (DOWN/recovering/air), reset counter
                    if self._post_high_saw_high and disp_flag in (-2, -3, -1):
                        self._post_high_counter = 0
                        self._post_high_saw_high = False
                        self._log(f'⚠ Post-high counter RESET — gas ≥{conc_thresh:.0f} ppm seen again → restarting {counter_limit}-sample window','warn',f'{t:.1f}')
                    # ────────────────────────────────────────────────────────────────
                    self._post_high_counter += new_count
                    if self._post_high_counter >= counter_limit:
                        self._post_high_active = False
                        self._post_high_counter = 0
                        self._post_high_saw_high = False
                        self._ic.p['upG'] = self.params['upG']
                        self._ic.p['inG'] = self.params['inG']
                        self._log(f'▶ Post-high counter done — resuming normal sensitivity','info',f'{t:.1f}')
                else:
                    # Restore normal gates
                    self._ic.p['upG'] = self.params['upG']
                    self._ic.p['inG'] = self.params['inG']
                    # Stage 1: track whether ppm crossed threshold during UP phase
                    if disp_flag == 1 or raw_flag == 1.0:
                        if cur_ppm >= conc_thresh:
                            self._post_high_saw_high = True
                    # Stage 2: arm counter when DOWN flag appears after a high reading
                    if self._post_high_saw_high and disp_flag in (-2, -3, -1):
                        # Down/recovering/air after a high-ppm event → arm
                        self._post_high_active = True
                        self._post_high_counter = 0
                        self._post_high_peak_ppm = cur_ppm
                        self._post_high_saw_high = False
                        self._log(f'⚠ Post-high limiting armed ({conc_thresh:.0f} ppm threshold crossed) → LARGE LEAKS ONLY for {counter_limit} samples','warn',f'{t:.1f}')
                # ──────────────────────────────────────────────────────────────

                # During the tare blank window: still update the visual flag highlight
                # so the UI doesn't look frozen/stuck, but suppress event count logging
                # and ppm display until blank expires so N re-accumulates from scratch.
                in_blank = (self._ic._tare_blank_count > 0)

                if disp_flag != self._live_last_flag:
                    if not in_blank:
                        # Full transition: log event, increment counter, update ppm
                        if disp_flag in self.flag_boxes: self.flag_boxes[disp_flag]['events']+=1
                        lbl_map={-1:'→ AIR / BASELINE (recovered)',1:'→ H2 CONFIRMED ▲',-2:'→ H2 DOWN ▼',-3:'→ RECOVERING'}
                        tag_map={-1:'air',1:'up',-2:'dn',-3:'rec'}
                        self._log(lbl_map.get(disp_flag,f'→{disp_flag}'),tag_map.get(disp_flag,'info'),f'{t:.1f}')
                        if disp_flag==-1: self.btn_poweroff.config(state='normal')
                    # Always update visual highlight and tracking (even during blank)
                    # so the flag boxes show correct state and UI doesn't appear stuck
                    self._live_last_flag=disp_flag; self._current_disp_flag=disp_flag
                    self._highlight_flag(disp_flag)

                ocap=int(self.params['o_cap'])
                if idx>1 and self._ic.O[-1]==ocap and self._ic.O[-2]<ocap:
                    self._log(f'★ 6 s snapshot → {last["S"]:.0f} ppm  (P={last["P"]:.4f} mV)','conc',f'{t:.1f}')

                if raw_flag==1 and not in_blank:
                    d=self.flag_boxes.get(1)
                    if d and d['conc_lbl']:
                        d['conc_lbl'].config(text=f'{last["S"]:.0f} ppm',
                                              fg=C_CONC if not self._flash_active else '#ffffff')

            self._update_rec_box(rec)

            # Always update ready box (post-high must show outside AIR flag too)
            self._update_ready_box(daughter_mv,mother_mv,post_high_active=self._post_high_active)
            self._update_post_high_indicator()

            self._update_metrics({**last,'F':last['FF'],
                                   'R':last['R'],'S':last['S'],
                                   'mother_baseline':mother_mv,'daughter_baseline':daughter_mv})

            s=max(0,len(self._ic.Q)-self.WIN)
            c_len=len(self._ic.C); q_len=len(self._ic.Q)
            c_s=max(0,c_len-(q_len-s)); mb_s=max(0,len(self._ic.MB)-(q_len-s))
            or_s=max(0,len(self._ic.OR_STATE)-(q_len-s))
            self._update_charts(
                self._ic.emf[-(q_len-s):], self._ic.C[c_s:],
                self._ic.L[s:], self._ic.MB[mb_s:],
                self._ic.N[s:], self._ic.P[s:], self._ic.Q[s:], self._ic.REC[s:],
                or_thr=float(self.params.get('or_thresh',720.0)),
                or_state_arr=self._ic.OR_STATE[or_s:]
            )
            cur=self.lbl_live.cget('text')
            self.lbl_live.config(text='● LIVE' if '●' not in cur else '○ LIVE',fg=C_AIR)

        self._live_after=self.root.after(self.INTERVAL,self._live_poll)


if __name__=='__main__':
    root=tk.Tk()
    App(root)
    root.mainloop()