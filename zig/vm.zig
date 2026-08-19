// vm.zig - Maquina Malbolge (semantica EXACTA del debugger del paquete
// `malbolge` con SparseMemory), compartida por bolge.zig (CLI batch) y
// frontier_scan.zig (escaneos exhaustivos).
//
// Quirks replicados del SparseMemory:
//   - overlay (dict) para source + writes; las lecturas van primero al overlay
//   - el crazy-fill se materializa por bloques de 243 celdas, PEROZOSAMENTE:
//     las semillas del bloque cola se leen del overlay (no del source) en el
//     momento del primer acceso lejano, asi que writes previos (encrypts,
//     crz, rotr) pueden cambiar los valores del fill
//   - las semillas del primer bloque tras el cola se derivan de las dos
//     ultimas celdas del bloque cola via overlay-or-chain (self[242],
//     self[241] con __getitem__); los bloques siguientes siguen la cadena
//     pura (equivalente al jump map del paquete)

const std = @import("std");

pub const MEM_SIZE: usize = 59049;
pub const LAST: u32 = MEM_SIZE - 1;
pub const POW9: u32 = 19683;
pub const HALF: u32 = 243;
pub const BLOCK_SIZE: usize = 243;
pub const MAX_OVERLAY: usize = 200000;

pub const ENCRYPT =
    "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVac`uY*MK'X~xDl}REokN:#?G\"i@";

const CRAZY_TBL = [3][3]u8{ .{ 1, 0, 0 }, .{ 1, 0, 2 }, .{ 2, 2, 1 } };

var crazy5: [HALF][HALF]u32 = undefined;
var chain: [MEM_SIZE]u32 = undefined;
var ovl_idx: [MAX_OVERLAY]u32 = undefined;
var ovl_val: [MAX_OVERLAY]u32 = undefined;
var ovl_len: usize = 0;
var chain_until: usize = 0;
var fill_start: usize = 0;

pub const OUT_CAP: usize = 65536;
pub var out_buf: [OUT_CAP]u8 = undefined;

pub const RunOutcome = struct {
    steps: u64,
    terminated: bool,
    output_len: usize,
    final_c: u32,
    final_a: u32,
    final_d: u32,
};

pub fn buildCrazy5() void {
    var a5: usize = 0;
    while (a5 < HALF) : (a5 += 1) {
        var b5: usize = 0;
        while (b5 < HALF) : (b5 += 1) {
            var r: u32 = 0;
            var p: u32 = 1;
            var aa: usize = a5;
            var bb: usize = b5;
            var k: usize = 0;
            while (k < 5) : (k += 1) {
                r += @as(u32, CRAZY_TBL[bb % 3][aa % 3]) * p;
                aa /= 3;
                bb /= 3;
                p *= 3;
            }
            crazy5[a5][b5] = r;
        }
    }
}

pub fn crazy(a: u32, b: u32) u32 {
    return crazy5[a % HALF][b % HALF] + HALF * crazy5[a / HALF][b / HALF];
}

fn rotate(n: u32) u32 {
    return POW9 * (n % 3) + n / 3;
}

fn ovlGet(x: usize) ?u32 {
    var i: usize = 0;
    while (i < ovl_len) : (i += 1) {
        if (ovl_idx[i] == x) return ovl_val[i];
    }
    return null;
}

fn ovlSet(x: usize, v: u32) void {
    var i: usize = 0;
    while (i < ovl_len) : (i += 1) {
        if (ovl_idx[i] == x) {
            ovl_val[i] = v;
            return;
        }
    }
    if (ovl_len < MAX_OVERLAY) {
        ovl_idx[ovl_len] = @intCast(x);
        ovl_val[ovl_len] = v;
        ovl_len += 1;
    }
}

fn ensureFilled(x: usize) void {
    const block_end = (x / BLOCK_SIZE + 1) * BLOCK_SIZE;
    const tail_end = (fill_start / BLOCK_SIZE + 1) * BLOCK_SIZE;
    var p1: u32 = undefined;
    var p2: u32 = undefined;
    var i: usize = undefined;
    if (chain_until == fill_start) {
        p1 = ovlGet(fill_start - 1) orelse 0;
        p2 = ovlGet(fill_start - 2) orelse 0;
        i = fill_start;
    } else {
        i = chain_until;
        p1 = chain[i - 1];
        p2 = chain[i - 2];
    }
    while (i < block_end) : (i += 1) {
        var nxt: u32 = undefined;
        if (i == tail_end) {
            nxt = crazy(memGet(i - 1), memGet(i - 2));
        } else if (i == tail_end + 1) {
            nxt = crazy(p1, memGet(i - 2));
        } else {
            nxt = crazy(p1, p2);
        }
        chain[i] = nxt;
        p2 = p1;
        p1 = nxt;
    }
    chain_until = block_end;
}

fn memGet(x: usize) u32 {
    if (ovlGet(x)) |v| return v;
    if (x < fill_start) return 0;
    if (x >= chain_until) ensureFilled(x);
    return chain[x];
}

fn memSet(x: usize, v: u32) void {
    ovlSet(x, v);
}

pub fn runProgram(cells: []const u32, input: []const u8, max_steps: u32) RunOutcome {
    fill_start = @max(cells.len, 2);
    chain_until = fill_start;
    ovl_len = 0;
    for (cells, 0..) |cell, i| {
        ovlSet(i, cell);
    }

    var a: u32 = 0;
    var c: u32 = 0;
    var d: u32 = 0;
    var executed: u64 = 0;
    var terminated = false;
    var input_pos: usize = 0;
    var output_len: usize = 0;

    while (executed < max_steps) {
        executed += 1;
        const ins = memGet(c);
        if (ins < 33 or ins > 126) {
            terminated = true;
            break;
        }
        const v = (ins + c) % 94;
        switch (v) {
            4 => c = memGet(d),
            5 => {
                if (output_len < OUT_CAP) {
                    out_buf[output_len] = @intCast(a % 256);
                    output_len += 1;
                }
            },
            23 => {
                if (input_pos < input.len) {
                    a = input[input_pos];
                    input_pos += 1;
                } else {
                    terminated = true;
                    break;
                }
            },
            39 => {
                const r = rotate(memGet(d));
                memSet(d, r);
                a = r;
            },
            40 => d = memGet(d),
            62 => {
                const r = crazy(a, memGet(d));
                memSet(d, r);
                a = r;
            },
            81 => {
                terminated = true;
                break;
            },
            else => {},
        }
        if (terminated) break;
        const enc = memGet(c);
        if (enc >= 33 and enc <= 126) memSet(c, ENCRYPT[enc - 33]);
        c = if (c == LAST) 0 else c + 1;
        d = if (d == LAST) 0 else d + 1;
    }

    return .{
        .steps = executed,
        .terminated = terminated,
        .output_len = output_len,
        .final_c = c,
        .final_a = a,
        .final_d = d,
    };
}