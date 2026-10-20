#!/usr/bin/env python3
"""synthesize.py - BolgeForge: canonical Malbolge classic quine synthesizer and verifier.

Usage: python3 synthesize.py <m>
  m = 2 (mod 3), in [161, 314]. Known-good: 281 (record, 53,562 B), 284, 287, 293, 308.
  Writes artifacts/candidate_m<m>_<bytes>b.mal and, if the oracle `mb_ref` is built
  (run `make`), verifies it byte-for-byte under Olmstead Classic semantics.

Port v3.1 (2026-10-17) of synthesize_v2.py v3 (sha256 56088d2c...), the version that
built the m=281 record (53,562 B; -572 B vs the previous m=284 record, -6,290 B vs
Lutter's 59,852 B reference quine). Only paths and CLI were made portable; the
synthesis core is byte-equivalent (regression: m=281 -> 96b670b8, m=284 -> 1808fd4d).
"""
import sys
import os
import subprocess
import time
from pathlib import Path
from collections import deque
import heapq
import itertools

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = REPO_ROOT / 'artifacts'
OUT_DIR.mkdir(exist_ok=True)

from relational.synthesizer import rot_op, crazy_op, XLAT1, XLAT2, run_on_engine

if len(sys.argv) < 2:
    print("usage: python3 synthesize_record_quine.py <m>   # m = 2 (mod 3) in [161, 314]; known-good: 281 (record), 284, 287, 293, 308")
    sys.exit(1)
m_target = int(sys.argv[1])
print(f"=== SYNTHESIZING MALBOLGE QUINE FOR m = {m_target} ===", flush=True)

Delta = 94 * (314 - m_target)
C = 94 * m_target
clean_total_len = 2 * C
capacity = C - 467

p = SCRIPT_DIR / 'baseline_quine.mal'
clean_lutter = [b for b in p.read_bytes() if 33 <= b <= 126]
assert len(clean_lutter) == 59032

# 1. Compute canonical diff targets from Lutter at step 27190
mem_lutter = list(clean_lutter) + [0] * (59049 - len(clean_lutter))
for i in range(len(clean_lutter), 59049):
    mem_lutter[i] = crazy_op(mem_lutter[i-1], mem_lutter[i-2])

a = c = d = step = 0
while step < 27190:
    instr = mem_lutter[c]
    idx = (instr - 33 + c) % 94 if 33 <= instr <= 126 else 0
    ch = XLAT1[idx]
    if ch == 'j': d = mem_lutter[d]
    elif ch == 'i': c = mem_lutter[d]
    elif ch == '*': mem_lutter[d] = rot_op(mem_lutter[d]); a = mem_lutter[d]
    elif ch == 'p': mem_lutter[d] = crazy_op(a, mem_lutter[d]); a = mem_lutter[d]
    if 33 <= mem_lutter[c] <= 126: mem_lutter[c] = ord(XLAT2[mem_lutter[c] - 33])
    c = 0 if c == 59048 else c + 1
    d = 0 if d == 59048 else d + 1
    step += 1

diffs = [i for i in range(29000, 30000) if clean_lutter[i] != mem_lutter[i]]
print(f"Found {len(diffs)} variables to synthesize.", flush=True)

def calc_reset_val(C_len):
    target_reset = C_len - 4
    for a_reset in range(59049):
        if crazy_op(a_reset, 29524) == target_reset:
            for X in range(59049):
                if crazy_op(59048, X) == a_reset:
                    return X
    raise ValueError(f"No solution for reset val C={C_len}")

targets = {}
for addr in diffs:
    val = mem_lutter[addr]
    new_addr = addr - Delta
    if addr == 29352:
        new_val = calc_reset_val(C)
    elif 29048 <= val <= 29515:
        new_val = val - Delta
    else:
        new_val = val
    targets[new_addr] = new_val


# 2. Initialize memory for m_target
loop_slice = clean_lutter[29049:29516]
assert len(loop_slice) == 467

mem = list(clean_lutter[:clean_total_len]) + [0] * (59049 - clean_total_len)
for i in range(467):
    mem[capacity + i] = loop_slice[i]
    mem[C + capacity + i] = loop_slice[i]

for i in range(clean_total_len, 59049):
    mem[i] = crazy_op(mem[i-1], mem[i-2])

# 3. Run prefix (0..1357)
a = c = d = 0
for step in range(1358):
    instr = mem[c]
    ch = XLAT1[(instr - 33 + c) % 94] if 33 <= instr <= 126 else 'o'
    if ch == 'j': d = mem[d]
    elif ch == 'i': c = mem[d]
    elif ch == '*': mem[d] = rot_op(mem[d]); a = mem[d]
    elif ch == 'p': mem[d] = crazy_op(a, mem[d]); a = mem[d]
    if 33 <= mem[c] <= 126: mem[c] = ord(XLAT2[mem[c]-33])
    c = (c + 1) % 59049; d = (d + 1) % 59049

print(f"Prefix finished: c={c}, d={d}, a={a}", flush=True)
assert c == 1473 and d == 149 and mem[148] == 29524

# 4. Return routes for loop variables
routes = {}
for start_d in range(34, 140):
    q = deque([(start_d, '')])
    vis = {start_d}
    found = None
    while q:
        curr, path = q.popleft()
        if curr == 140:
            found = path; break
        if len(path) >= 12: continue
        no = (curr + 1) % 59049
        if no not in vis:
            vis.add(no); q.append((no, path + 'o'))
        nj = (mem[curr] + 1) % 59049
        if nj not in vis:
            vis.add(nj); q.append((nj, path + 'j'))
    routes[start_d] = found

def get_return_code(from_addr, written_set):
    best = None
    best_cost = 999999
    cand = from_addr
    limit = from_addr + 40
    while cand < C and cand <= limit:
        if cand not in written_set:
            target_d = (mem[cand] + 1) % 59049
            if target_d in routes and routes[target_d] is not None:
                cost = (cand - from_addr) + 1 + len(routes[target_d])
                if cost < best_cost:
                    best_cost = cost
                    best = 'o' * (cand - from_addr) + 'j' + routes[target_d]
        cand += 1
    if best is not None:
        return best
    cand = from_addr
    while cand < C:
        if cand not in written_set:
            target_d = (mem[cand] + 1) % 59049
            if target_d in routes and routes[target_d] is not None:
                return 'o' * (cand - from_addr) + 'j' + routes[target_d]
        cand += 1
    raise RuntimeError(f"Could not return to 140 from {from_addr}")

# 5. Dijkstra Solver
C2 = 59048; C20 = 59046; C21 = 59047; C0 = 0; C29524 = 29524
trans_rot = [rot_op(i) for i in range(59049)]
trans_c2 = [crazy_op(C2, i) for i in range(59049)]
trans_c20 = [crazy_op(C20, i) for i in range(59049)]
trans_c21 = [crazy_op(C21, i) for i in range(59049)]
trans_c0 = [crazy_op(C0, i) for i in range(59049)]
trans_c29 = [crazy_op(C29524, i) for i in range(59049)]
trans_rxx = [crazy_op(rot_op(i), rot_op(i)) for i in range(59049)]

# extended pure edges discovered via exhaustive macro enumeration (len<=14)
rot2_tab = [trans_rot[i] for i in trans_rot]
rot3_tab = [trans_rot[i] for i in rot2_tab]
def _cf_rot(K, a):
    base = trans_rot if a == 1 else (rot2_tab if a == 2 else rot3_tab)
    return [crazy_op(K, base[i]) for i in range(59049)]
trans_cr_2_1 = _cf_rot(C2, 1)
trans_cr_2_2 = _cf_rot(C2, 2)
trans_cr_2_3 = _cf_rot(C2, 3)
trans_cr_29_1 = _cf_rot(C29524, 1)
trans_cr_29_2 = _cf_rot(C29524, 2)
trans_cr_0_1 = _cf_rot(0, 1)
trans_cr_0_2 = _cf_rot(0, 2)
trans_cr_20_1 = _cf_rot(C20, 1)
trans_cr_20_2 = _cf_rot(C20, 2)
trans_cr_21_1 = _cf_rot(C21, 1)
trans_cr_21_2 = _cf_rot(C21, 2)
trans_cr_19682_1 = _cf_rot(19682, 1)
trans_cr_19682_2 = _cf_rot(19682, 2)
trans_cr_39365_1 = _cf_rot(39365, 1)
trans_cr_39365_2 = _cf_rot(39365, 2)
trans_xx22 = [crazy_op(rot2_tab[i], rot2_tab[i]) for i in range(59049)]
trans_xx33 = [crazy_op(rot3_tab[i], rot3_tab[i]) for i in range(59049)]
trans_const_29 = [C29524] * 59049
trans_const_0 = [0] * 59049

macro_code = {
    0: '*jo',
    1: 'oj*pjo',
    2: 'oojo*popjo',
    3: 'ooj*opopjo',
    4: 'ooojooo*ooopjo',
    5: 'ooojoooo*oopjo',
    6: '*jopjo',
    7: '*j*pjo',
    8: '*jo*j*pjo',
    9: '*jo*jo*j*pjo',
    10: '*ojo*oopjo',
    11: '*ojo*oopjo*jo',
    12: '*oj*ooopjo',
    13: '*oj*ooopjo*jo',
    14: '*ojo*popjo',
    15: '*jo*ojo*popjo',
    16: '*oj*opopjo',
    17: '*jo*oj*opopjo',
    18: 'oojo*popjo*jo',
    19: 'ooj*opopjo*jo',
    20: '*oj*opopjo*jo',
    21: '*ojo*popjo*jo',
    22: '*jopjo*jo',
    23: '*jopjo*jo*jo',
    24: 'pjopjppjopjo',
    25: 'pjopojo*oopjo',
}

EDGES = [
    (trans_rot, 3),      # 0
    (trans_c2, 6),       # 1
    (trans_c20, 10),     # 2
    (trans_c21, 10),     # 3
    (trans_c0, 14),      # 4
    (trans_c29, 14),     # 5
    (trans_rxx, 6),      # 6
    (trans_cr_2_1, 6),   # 7
    (trans_cr_2_2, 9),   # 8
    (trans_cr_2_3, 12),  # 9
    (trans_cr_29_1, 10), # 10
    (trans_cr_29_2, 13), # 11
    (trans_cr_0_1, 10),  # 12
    (trans_cr_0_2, 13),  # 13
    (trans_cr_20_1, 10), # 14
    (trans_cr_20_2, 13), # 15
    (trans_cr_21_1, 10), # 16
    (trans_cr_21_2, 13), # 17
    (trans_cr_19682_1, 13), # 18
    (trans_cr_39365_1, 13), # 19
    (trans_cr_39365_2, 13), # 20
    (trans_cr_19682_2, 13), # 21
    (trans_xx22, 9),     # 22
    (trans_xx33, 12),    # 23
    (trans_const_29, 12),# 24
    (trans_const_0, 13), # 25
]

def fast_dijkstra_path(src, dst):
    if src == dst: return 0, []
    dist = [-1] * 59049
    dist[src] = 0
    parent = [-1] * 59049
    parent_op = [-1] * 59049
    pq = [(0, src)]
    while pq:
        cost, u = heapq.heappop(pq)
        if u == dst:
            path = []
            curr = dst
            while curr != src:
                p = parent[curr]
                op = parent_op[curr]
                path.append(op)
                curr = p
            return cost, path[::-1]
        if cost > dist[u]: continue
        for op, (tab, w) in enumerate(EDGES):
            v = tab[u]; nd = cost + w
            if dist[v] == -1 or nd < dist[v]:
                dist[v] = nd; parent[v] = u; parent_op[v] = op; heapq.heappush(pq, (nd, v))
    return 0, []

def dijkstra_dist_only(src, dst):
    if src == dst: return 0
    dist = [-1] * 59049
    dist[src] = 0
    pq = [(0, src)]
    while pq:
        cost, u = heapq.heappop(pq)
        if u == dst: return cost
        if cost > dist[u]: continue
        for tab, w in EDGES:
            v = tab[u]; nd = cost + w
            if dist[v] == -1 or nd < dist[v]:
                dist[v] = nd; heapq.heappush(pq, (nd, v))
    return 999999

synthesized_ops = []
phase = 'init'
PHASE = {}
LENS = {'g_ret': [], 'g_synth': [], 'land_ret': [], 'land_synth': [], 'misc_synth': []}

def exec_ops(ops):
    global a, c, d
    for ch in ops:
        synthesized_ops.append(ch)
        PHASE[phase] = PHASE.get(phase, 0) + 1
        ascii_val = ((XLAT1.index(ch) - (c % 94)) % 94) + 33
        if ch == 'j': d = mem[d]
        elif ch == 'i': c = mem[d]
        elif ch == '*': mem[d] = rot_op(mem[d]); a = mem[d]
        elif ch == 'p': mem[d] = crazy_op(a, mem[d]); a = mem[d]
        mem[c] = ord(XLAT2[ascii_val - 33])
        c = (c + 1) % 59049; d = (d + 1) % 59049

# 6. Seed synthesis
seed_val = 29265 - Delta
TRIT_SOLS = {
    (0, 0): [1, 2], (0, 1): [0], (0, 2): [],
    (1, 0): [1], (1, 1): [0], (1, 2): [2],
    (2, 0): [], (2, 1): [2], (2, 2): [0, 1]
}
def solve_crazy_first(b, target):
    """Find x such that crazy_op(x, b) = target.  p instruction is crazy(a, mem[d])."""
    trit_map = {
        0: {1: [0], 0: [1, 2], 2: []},
        1: {1: [0], 0: [1], 2: [2]},
        2: {2: [0, 1], 1: [2], 0: []},
    }
    allowed = []
    bb = b; tt = target; p = 1
    for _ in range(10):
        bi = bb % 3; ti = tt % 3
        s = trit_map[bi].get(ti, [])
        if not s:
            return []
        allowed.append([x * p for x in s])
        bb //= 3; tt //= 3; p *= 3
    res = [0]
    for trits in allowed:
        res = [base + t for base in res for t in trits]
    return res

seed_x = solve_crazy_first(29524, seed_val)[0]
phase = 'seed'
exec_ops('ooooo')
assert d == 154
_, path = fast_dijkstra_path(mem[154], seed_x)
exec_ops(''.join(macro_code[op] for op in path))
assert mem[154] == seed_x and a == seed_x
exec_ops('ooojopj')
assert mem[148] == seed_val and d == 140
print(f"Seed {seed_val} written to cell 148.", flush=True)

# 7. Write all 28 groups
inc_macros = {
    0: '*opoooo*pjoopooopopjoopooopooj*joj',
    1: '*opoooo*pjoopoopoopjoopoopooojojoj',
    2: '*opoooo*pjoopopooopjoopopooooj*joj',
    3: '*opoooo*pjooppoooopjooppoooooj'
}

def sim_step(sm, sd, sa, ch):
    if ch == 'j': sd = sm[sd]
    elif ch == '*': sm[sd] = rot_op(sm[sd]); sa = sm[sd]
    elif ch == 'p': sm[sd] = crazy_op(sa, sm[sd]); sa = sm[sd]
    elif ch == 'o': pass
    sd = (sd + 1) % 59049
    return sm, sd, sa

def do_composite_inc(T):
    """V=mem[148] -> T=(V+9)%59049 via two guaranteed writes V->W->T."""
    import random as _rnd
    global a, d, phase
    V = mem[148]
    T = T % 59049
    assert T == (V + 9) % 59049, f"composite target mismatch {V} -> {T}"
    def _trits(x):
        out = []
        for _ in range(10):
            out.append(x % 3); x //= 3
        return out
    vt = _trits(V); tt = _trits(T)
    wt = list(vt)
    for i in range(10):
        if i >= 2 and vt[i] == 2 and tt[i] == 0:
            wt[i] = 1
    W0 = sum(x * (3 ** i) for i, x in enumerate(wt))
    # candidate W variants: free digits where V==1 (any W allowed both writes)
    variants = [wt]
    free_idx = [i for i in range(10) if vt[i] == 1]
    for _ in range(23):
        wv = list(wt)
        r = _rnd.Random(V ^ len(variants) * 2654435761)
        for i in free_idx:
            wv[i] = r.randrange(3)
        variants.append(wv)
    best = None
    for wv in variants:
        W = sum(x * (3 ** i) for i, x in enumerate(wv))
        s1 = solve_crazy_first(V, W)
        if not s1:
            continue
        s2 = solve_crazy_first(W, T)
        if not s2:
            continue
        for x1 in s1[:5]:
            if mem[154] == x1:
                c1 = 0 if a == x1 else 30
            else:
                c1 = dijkstra_dist_only(mem[154], x1)
            for x2 in s2[:5]:
                c2 = 0 if x1 == x2 else dijkstra_dist_only(x1, x2)
                c = c1 + c2
                if best is None or c < best[0]:
                    best = (c, W, x1, x2)
    assert best is not None, f"composite construction failed V={V} T={T}"
    _, W, X1, X2 = best
    print(f"  COMPOSITE INC V={V} W={W} T={T} X1={X1} X2={X2} est_extra={best[0]}", flush=True)
    phase = 'comp_inc'
    # write 1: V -> W
    exec_ops('ojoooooo')
    assert d == 154
    if mem[154] == X1 and a == X1: ops1 = ''
    elif mem[154] == X1 and a != X1: ops1 = '*jo' * 10
    else:
        _, p1 = fast_dijkstra_path(mem[154], X1)
        ops1 = ''.join(macro_code[op] for op in p1)
    exec_ops(ops1)
    assert mem[154] == X1 and a == X1
    exec_ops('ooojopj')
    assert mem[148] == W and d == 140
    # write 2: W -> T
    exec_ops('ojoooooo')
    assert d == 154
    if mem[154] == X2 and a == X2: ops2 = ''
    elif mem[154] == X2 and a != X2: ops2 = '*jo' * 10
    else:
        _, p2 = fast_dijkstra_path(mem[154], X2)
        ops2 = ''.join(macro_code[op] for op in p2)
    exec_ops(ops2)
    assert mem[154] == X2 and a == X2
    exec_ops('ooojopj')
    assert mem[148] == T and d == 140
    print(f"  COMPOSITE INC OK mem[148]={mem[148]} d={d} c={c}", flush=True)

def find_inc_macro_bfs(curr_val, mem_snapshot, a_start, max_depth=24):
    start_mem = list(mem_snapshot)
    start_mem[148] = curr_val
    q = deque()
    q.append((140, a_start, curr_val, start_mem, ''))
    visited = set()
    visited.add((140, a_start, curr_val))
    target = (curr_val + 9) % 59049
    nodes = 0
    while q:
        d, a_, m148, smem, path = q.popleft()
        if m148 == target and d == 140 and len(path) > 0:
            return path
        if len(path) >= max_depth:
            continue
        nodes += 1
        if nodes > 150000:
            return None
        for ch in ['o', 'j', '*', 'p']:
            m2, d2, a2 = sim_step(smem, d, a_, ch)
            m148_2 = m2[148]
            key = (d2, a2, m148_2)
            if key in visited:
                continue
            visited.add(key)
            q.append((d2, a2, m148_2, m2, path + ch))
    return None

def run_macro_check(macro, curr_val):
    sim_mem = list(mem)
    sim_mem[148] = curr_val
    sim_a = a; sim_d = 140
    for ch in macro:
        if ch == 'j': sim_d = sim_mem[sim_d]
        elif ch == '*': sim_mem[sim_d] = rot_op(sim_mem[sim_d]); sim_a = sim_mem[sim_d]
        elif ch == 'p': sim_mem[sim_d] = crazy_op(sim_a, sim_mem[sim_d]); sim_a = sim_mem[sim_d]
        sim_d = (sim_d + 1) % 59049
    return sim_mem[148] == (curr_val + 9) % 59049 and sim_d == 140

find_inc_at_runtime = True
bfs_count = 0
print(f"Generated 27 group increment macro sequence for m={m_target} (BFS fallbacks: {bfs_count}).", flush=True)

target_strategies = {}
import json as _json
_strat_dump = open(OUT_DIR / f"strat_m{m_target}.jsonl", "w")
for addr, target in targets.items():
    init_val = mem[addr]
    sols1 = solve_crazy_first(init_val, target)
    _strat_dump.write(_json.dumps({'addr': addr, 'init': init_val, 'target': target, 'sols1': (sols1 or [])[:8]}) + "\n")
    if sols1:
        target_strategies[addr] = ('1write', sols1)
        continue
    m0 = crazy_op(0, init_val)
    sols0 = solve_crazy_first(m0, target)
    if sols0:
        target_strategies[addr] = ('2write_0', sols0)
        continue
    target_strategies[addr] = ('3write', solve_crazy_first(29524, target))
_strat_dump.close()

written_set = set()

for g in range(28):
    DEST = seed_val + g * 9
    addrs = [DEST + k for k in range(1, 10) if (DEST + k) in targets]
    
    rep_X = {}
    for cand in addrs:
        strat, sols = target_strategies[cand]
        best_x = sols[0]
        best_d = dijkstra_dist_only(mem[154], best_x)
        for cand_x in sols[1:8]:
            d_x = dijkstra_dist_only(mem[154], cand_x)
            if d_x < best_d:
                best_d = d_x; best_x = cand_x
        rep_X[cand] = best_x
        
    nodes = [mem[154]] + [rep_X[a] for a in addrs]
    N = len(nodes)
    dist_mat = [[0] * N for _ in range(N)]
    for i in range(N):
        for j in range(N):
            if i != j:
                dist_mat[i][j] = dijkstra_dist_only(nodes[i], nodes[j])
                
    best_perm = None
    best_cost = 999999
    if N <= 9:
        for perm in itertools.permutations(range(1, N)):
            cost = dist_mat[0][perm[0]]
            for k in range(len(perm)-1):
                cost += dist_mat[perm[k]][perm[k+1]]
            if cost < best_cost:
                best_cost = cost
                best_perm = perm
    else:
        rem = list(range(1, N))
        curr = 0
        p = []
        while rem:
            nxt = min(rem, key=lambda x: dist_mat[curr][x])
            p.append(nxt)
            rem.remove(nxt)
            curr = nxt
        best_perm = p
        
    ordered_addrs = [addrs[idx - 1] for idx in best_perm]
    
    for addr in ordered_addrs:
        strat, sols = target_strategies[addr]
        target = targets[addr]
        k = addr - DEST
        walk = 'o' * (k - 1)
        ret = get_return_code(addr + 1, written_set)
        LENS['g_ret'].append(len(ret))
        
        best_X = rep_X[addr]
        if len(sols) > 1:
            best_d = dijkstra_dist_only(mem[154], best_X)
            for cand_x in sols:
                d_x = dijkstra_dist_only(mem[154], cand_x)
                if d_x < best_d:
                    best_d = d_x; best_X = cand_x
        X = best_X
        
        if strat == '1write':
            phase = 'g_setup'
            exec_ops('ojoooooo')
            assert d == 154
            if mem[154] == X and a == X: synth_ops = ''
            elif mem[154] == X and a != X: synth_ops = '*jo' * 10
            else:
                _, best_path = fast_dijkstra_path(mem[154], X)
                synth_ops = ''.join(macro_code[op] for op in best_path)
            LENS['g_synth'].append(len(synth_ops))
            phase = 'g_synth'
            _from = (d, a, mem[154], [mem[k] for k in range(140,159)])
            exec_ops(synth_ops)
            if not (mem[154] == X and a == X):
                print(f"SYNTHFAIL strat={strat} addr={addr} X={X} mem154={mem[154]} a={a} ops={synth_ops!r} from_d={_from[0]} from_a={_from[1]} from_154={_from[2]} from_module={_from[3]} to_module={[mem[k] for k in range(140,159)]}", flush=True)
            assert mem[154] == X and a == X
            write_code = 'ooojoj' + walk + 'p' + ret
            phase = 'g_write'
            exec_ops(write_code)
            if not (d == 140 and mem[addr] == target):
                print(f"WRITEFAIL g={g} addr={addr} k={k} strat={strat} d={d} mem[addr]={mem[addr]} target={target} c={c} mem[148]={mem[148]} DEST={DEST} mem[154]={mem[154]} a={a} X={X}", flush=True)
            assert d == 140 and mem[addr] == target
            
        elif strat == '2write_0':
            phase = 'g_clear'
            exec_ops('ojoo*' + 'oooooo' + 'joj' + walk + 'p' + ret)
            assert d == 140
            phase = 'g_setup'
            exec_ops('ojoooooo')
            assert d == 154
            if mem[154] == X and a == X: synth_ops = ''
            elif mem[154] == X and a != X: synth_ops = '*jo' * 10
            else:
                _, best_path = fast_dijkstra_path(mem[154], X)
                synth_ops = ''.join(macro_code[op] for op in best_path)
            LENS['g_synth'].append(len(synth_ops))
            phase = 'g_synth'
            _from = (d, a, mem[154], [mem[k] for k in range(140,159)])
            exec_ops(synth_ops)
            if not (mem[154] == X and a == X):
                print(f"SYNTHFAIL strat={strat} addr={addr} X={X} mem154={mem[154]} a={a} ops={synth_ops!r} from_d={_from[0]} from_a={_from[1]} from_154={_from[2]} from_module={_from[3]} to_module={[mem[k] for k in range(140,159)]}", flush=True)
            assert mem[154] == X and a == X
            write_code = 'ooojoj' + walk + 'p' + ret
            phase = 'g_write'
            exec_ops(write_code)
            if not (d == 140 and mem[addr] == target):
                print(f"WRITEFAIL g={g} addr={addr} k={k} strat={strat} d={d} mem[addr]={mem[addr]} target={target} c={c} mem[148]={mem[148]} DEST={DEST} mem[154]={mem[154]} a={a} X={X}", flush=True)
            assert d == 140 and mem[addr] == target
            
        else: # 3write fallback
            clear_code = '*jj' + walk + 'p' + ret + 'ojj' + walk + 'p' + ret
            phase = 'g_clear'
            exec_ops(clear_code)
            assert d == 140 and mem[addr] == 29524
            phase = 'g_setup'
            exec_ops('ojoooooo')
            assert d == 154
            if mem[154] == X and a == X: synth_ops = ''
            elif mem[154] == X and a != X: synth_ops = '*jo' * 10
            else:
                _, best_path = fast_dijkstra_path(mem[154], X)
                synth_ops = ''.join(macro_code[op] for op in best_path)
            LENS['g_synth'].append(len(synth_ops))
            phase = 'g_synth'
            _from = (d, a, mem[154], [mem[k] for k in range(140,159)])
            exec_ops(synth_ops)
            if not (mem[154] == X and a == X):
                print(f"SYNTHFAIL strat={strat} addr={addr} X={X} mem154={mem[154]} a={a} ops={synth_ops!r} from_d={_from[0]} from_a={_from[1]} from_154={_from[2]} from_module={_from[3]} to_module={[mem[k] for k in range(140,159)]}", flush=True)
            assert mem[154] == X and a == X
            write_code = 'ooojoj' + walk + 'p' + ret
            phase = 'g_write'
            exec_ops(write_code)
            if not (d == 140 and mem[addr] == target):
                print(f"WRITEFAIL g={g} addr={addr} k={k} strat={strat} d={d} mem[addr]={mem[addr]} target={target} c={c} mem[148]={mem[148]} DEST={DEST} mem[154]={mem[154]} a={a} X={X}", flush=True)
            assert d == 140 and mem[addr] == target
            
        written_set.add(addr)
        
    if g < 27:
        phase = 'g_inc'
        found_idx = None
        for idx in range(4):
            if run_macro_check(inc_macros[idx], mem[148]):
                found_idx = idx
                break
        if found_idx is None:
            macro = find_inc_macro_bfs(mem[148], mem, a)
            if macro is None:
                print(f"  BFS failed @ {mem[148]} -> COMPOSITE INC", flush=True)
                do_composite_inc((mem[148] + 9) % 59049)
                found_idx = -1
            else:
                inc_macros[len(inc_macros)] = macro
                found_idx = len(inc_macros) - 1
                print(f"  BFS inc @ {mem[148]}: '{macro}' ({len(macro)} ops)", flush=True)
        if found_idx >= 0:
            exec_ops(inc_macros[found_idx])
        assert mem[148] == DEST + 9 and d == 140
        
    print(f"Group {g:02d} written! Current c = {c}", flush=True)

print(f"All 215 variables written! Current c = {c}", flush=True)

# 7.5 Write end-of-program boundary cell (clean_total_len) = 127
if clean_total_len != 59032:
    print(f"Writing end-of-program boundary cell {clean_total_len} = 127...", flush=True)
    phase = 'boundary'
    exec_ops('*jpjojpj')
    assert mem[148] == 29524 and d == 140
    exec_ops('ojoooooo')
    assert d == 154
    v_dest = solve_crazy_first(29524, clean_total_len - 1)[0]
    _, path_dest = fast_dijkstra_path(mem[154], v_dest)
    exec_ops(''.join(macro_code[op] for op in path_dest))
    assert mem[154] == v_dest and a == v_dest
    exec_ops('ooojopj')
    assert mem[148] == clean_total_len - 1 and d == 140

    exec_ops('ojoooooo')
    assert d == 154
    x_127 = solve_crazy_first(mem[clean_total_len], 127)[0]
    _, path_127 = fast_dijkstra_path(mem[154], x_127)
    exec_ops(''.join(macro_code[op] for op in path_127))
    assert mem[154] == x_127 and a == x_127
    exec_ops('ooojojpj' + 'jjjoj')
    assert mem[clean_total_len] == 127 and d == 140
    print(f"End-of-program boundary cell {clean_total_len} written to 127! Current c = {c}", flush=True)

# 8. Reset mem[148] = 44
phase = 'reset'
exec_ops('*jpjojpj')
assert mem[148] == 29524 and d == 140
exec_ops('ojoooooo')
assert d == 154
_, path_44 = fast_dijkstra_path(mem[154], 29492)
exec_ops(''.join(macro_code[op] for op in path_44))
assert mem[154] == 29492 and a == 29492
exec_ops('ooojopj')
assert mem[148] == 44 and d == 140
print(f"Cell 148 reset to 44. Current c = {c}", flush=True)

# 9. Landing table (cells 45..138)
target_landing = 29420 - Delta
x_landing = solve_crazy_first(29524, target_landing)[0]

def can_reach_140(start, min_allowed):
    if start == 140: return ''
    q = deque([(start, '')])
    vis = {start}
    while q:
        u, path = q.popleft()
        if u == 140: return path
        if len(path) >= 8: continue
        no = u + 1
        if (no >= min_allowed and no <= 140) and no not in vis:
            vis.add(no); q.append((no, path + 'o'))
        nj = mem[u] + 1
        if (nj >= min_allowed and nj <= 140) and nj not in vis:
            vis.add(nj); q.append((nj, path + 'j'))
    return None

safe_returns = {}
for addr in range(45, 127):
    found = None
    for cand in range(addr + 1, 140):
        target_d = mem[cand] + 1
        if target_d > addr and target_d <= 140:
            path = can_reach_140(target_d, addr + 1)
            if path is not None:
                walk = 'o' * (cand - (addr + 1))
                found = walk + 'j' + path
                break
    assert found is not None, f"Failed internal return for addr {addr}!"
    safe_returns[addr] = found

for addr in range(127, 139):
    walk = 'o' * (140 - (addr + 1))
    safe_returns[addr] = walk

# Synthesize x_landing in mem[154]
phase = 'land_prep'
exec_ops('ojoooooo')
assert d == 154
_, path_landing = fast_dijkstra_path(mem[154], x_landing)
LENS['land_synth'].append(len(path_landing))
exec_ops(''.join(macro_code[op] for op in path_landing))
assert mem[154] == x_landing and a == x_landing
exec_ops('ooojooj')
assert d == 140 and mem[148] == 44

for g in range(11):
    DEST = 44 + g * 9
    assert mem[148] == DEST
    k_max = 4 if g == 10 else 9
    for k in range(1, k_max + 1):
        addr = DEST + k
        assert addr <= 138
        walk = 'o' * (k - 1)
        ret = safe_returns[addr]
        LENS['land_ret'].append(len(ret))
        
        # Clear
        if crazy_op(0, mem[addr]) == 29524:
            clear_code = 'ojoo*' + 'oooooo' + 'joj' + walk + 'p' + ret
        else:
            clear_code = '*jj' + walk + 'p' + ret + 'ojj' + walk + 'p' + ret
        phase = 'land_clear'
        exec_ops(clear_code)
        assert d == 140 and mem[addr] == 29524
        
        # Reload A = x_landing via *pj*p at 153..155
        phase = 'land_reload'
        exec_ops('ojooooo' + '*pj*p')
        assert mem[154] == x_landing and a == x_landing and d == 155
        
        # Write target_landing
        write_code = 'oojoj' + walk + 'p' + ret
        phase = 'land_write'
        exec_ops(write_code)
        assert d == 140 and mem[addr] == target_landing
    
    if g < 10:
        phase = 'land_inc'
        found_idx = None
        for idx in range(4):
            if run_macro_check(inc_macros[idx], mem[148]):
                found_idx = idx
                break
        if found_idx is None:
            macro = find_inc_macro_bfs(mem[148], mem, a)
            if macro is None:
                print(f"  BFS landing failed @ {mem[148]} -> COMPOSITE INC", flush=True)
                do_composite_inc((mem[148] + 9) % 59049)
                found_idx = -1
            else:
                inc_macros[len(inc_macros)] = macro
                found_idx = len(inc_macros) - 1
                print(f"  BFS landing inc @ {mem[148]}: '{macro}' ({len(macro)} ops)", flush=True)
        if found_idx >= 0:
            exec_ops(inc_macros[found_idx])
        assert mem[148] == DEST + 9 and d == 140

print(f"All 94 landing table cells written to {target_landing}! Current c = {c}", flush=True)

# 10. Write cell 139
phase = 'cell139'
target_139 = 29474 - Delta
x_139 = solve_crazy_first(29524, target_139)[0]

exec_ops('*jj' + 'oooo' + 'p' + 'ojj' + 'oooo' + 'p')
assert d == 140 and mem[139] == 29524

exec_ops('ojoooooo')
assert d == 154
_, path_139 = fast_dijkstra_path(mem[154], x_139)
exec_ops(''.join(macro_code[op] for op in path_139))
assert mem[154] == x_139 and a == x_139

exec_ops('ooojoj' + 'oooo' + 'p')
assert d == 140 and mem[139] == target_139
print(f"Cell 139 written with {target_139}! Current c = {c}", flush=True)

# 11. Handoff jump
phase = 'handoff'
target_handoff_a = 29509 - Delta
target_handoff_c = 29078 - Delta
target_handoff_d = 29511 - Delta
target_handoff_mem_d = 29077 - Delta

exec_ops('ojoooooo')
assert d == 154
_, path_handoff = fast_dijkstra_path(mem[154], target_handoff_a)
exec_ops(''.join(macro_code[op] for op in path_handoff))
assert mem[154] == target_handoff_a and a == target_handoff_a

pre_jump_c = c
print(f"Position c before handoff jump: {pre_jump_c}", flush=True)
print(f"Maximum allowed c (capacity - 3): {capacity - 3}", flush=True)
if pre_jump_c > capacity - 3:
    print(f"OVERFLOW by {pre_jump_c - (capacity - 3)}", flush=True)
    print("LENS:", {k: (len(v) if isinstance(v, list) else v) for k, v in LENS.items()}, flush=True)
    print("PHASE_TOTALS:", {k: v for k, v in PHASE.items()}, flush=True)

assert pre_jump_c <= capacity - 3, f"Preamble overflow: c={pre_jump_c} exceeds {capacity - 3}!"

# Jump instruction
exec_ops('j')
assert d == target_handoff_d - 1 and a == target_handoff_a and mem[target_handoff_d - 1] == target_handoff_mem_d
exec_ops('i')
assert c == target_handoff_c and d == target_handoff_d and a == target_handoff_a

print("=" * 60, flush=True)
print(f"PREAMBLE SYNTHESIS 100% COMPLETE AND VERIFIED FOR m = {m_target}!", flush=True)
print(f"Final handoff: c = {c}, d = {d}, a = {a}", flush=True)
print(f"Total synthesized opcodes: {len(synthesized_ops)}", flush=True)
print("PHASE BREAKDOWN:", flush=True)
for k in sorted(PHASE, key=lambda x: -PHASE[x]):
    print(f"  {k:14s} {PHASE[k]:7d}", flush=True)
for k in LENS:
    if LENS[k]:
        print(f"  {k:14s} n={len(LENS[k]):4d} total={sum(LENS[k]):7d} mean={sum(LENS[k])/len(LENS[k]):6.1f}", flush=True)
print(f"Positive margin before loop slice ({capacity}): {capacity - (pre_jump_c + 2)} opcodes!", flush=True)
print("=" * 60, flush=True)

# 12. Build the exact standalone source file
region_a = list(clean_lutter[:1473])

for i, cmd in enumerate(synthesized_ops):
    cell_idx = 1473 + i
    idx = XLAT1.index(cmd)
    ascii_val = ((idx - (cell_idx % 94)) % 94) + 33
    region_a.append(ascii_val)

assert len(region_a) == pre_jump_c + 2

idx_nop = XLAT1.index('o')
for cell_idx in range(len(region_a), capacity):
    ascii_val = ((idx_nop - (cell_idx % 94)) % 94) + 33
    region_a.append(ascii_val)

assert len(region_a) == capacity

# Append loop slice
region_a.extend(loop_slice)
assert len(region_a) == C

# Region B is an identical copy of Region A
clean_source = region_a + region_a
assert len(clean_source) == clean_total_len

# Format with line breaks at 72 chars/line
lines = [clean_source[i:i+72] for i in range(0, len(clean_source), 72)]
formatted_source = b'\n'.join(bytes(l) for l in lines) + b'\n'

file_bytes_count = len(formatted_source)
print(f"TOTAL FILE BYTES (wrapped at 72 chars/line): {file_bytes_count} bytes!", flush=True)

out_file = OUT_DIR / f'candidate_m{m_target}_{file_bytes_count}b.mal'
out_file.write_bytes(formatted_source)
print(f"WROTE EXACT QUINE FILE TO: {out_file}", flush=True)

# 13. Canonical Olmstead verification with Autobolge native Zig motor (bolge.exe)
print(f"RUNNING CANONICAL OLMSTEAD VERIFICATION WITH bolge.exe...", flush=True)
t0 = time.time()
out_b, steps, term, reason = run_on_engine(clean_source, input_data="", max_steps=100_000_000)
elapsed = time.time() - t0
print(f"Engine finished in {elapsed:.3f}s ({steps:,} steps, term={term}, reason={reason})", flush=True)

if out_b == formatted_source:
    print("*" * 60, flush=True)
    print(f"VERIFICATION PASS: EXACT 0-BYTE DIFFERENCE BIT-FOR-BIT!", flush=True)
    print(f"CANONICAL MALBOLGE QUINE FOR m = {m_target} CONFIRMED!", flush=True)
    print(f"FILE SIZE: {file_bytes_count} BYTES (vs Lutter's 59,852 bytes, saved {59852 - file_bytes_count} bytes!)", flush=True)
    print("*" * 60, flush=True)
else:
    print(f"Diff mismatch: output {len(out_b)} bytes vs source {len(formatted_source)} bytes", flush=True)

