// vm.zig - Motor Malbolge CLASSIC denso, port de Malbolge-Translator
// zig/src/engine.zig. Compartido por bolge.zig (CLI batch) y
// frontier_scan.zig (escaneos exhaustivos).
//
// Semantica replicada de engine.zig:
//   - cinta DENSE [MEM_SIZE]u16, cero-inicializada y rellenada al completo
//     por la recurrencia crazy (para programas cortos las semillas de la
//     cola usan wrap a mem[MEM_SIZE-1], que vale 0 por la inicializacion:
//     la autoridad Python es una cinta pre-rellenada a cero)
//   - decode con widening: op = (cell + c) % 94
//   - instrucciones invalidas -> NOP (la ejecucion NO termina por celda no
//     imprimible)
//   - opcodes: 4=chase 5=out 23=in 39=rotr 40=mov_d 62=crz 68=nop 81=halt
//   - post-exec: si hubo jump, c = c_target; encrypt de mem[c] si
//     33 <= mem[c] <= 126; c++ y d++ con wrap en MEM_SIZE
//   - steps cuenta TODA instruccion ejecutada, incluida la que termina
//
// Divergencia deliberada con engine.zig: OP_IN consume input REAL (engine
// usa a=0xFFFF); el bajoflujo de input TERMINA la ejecucion (contrato
// Autobolge: los echoes dependen de ello).
//
// La tabla crazy (CRAZY_TBL indexado [bb%3][aa%3]) y ENCRYPT son las
// canonicas de la toolkit malbolge (malbolge_toolkit) verificadas valor a
// valor.

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

// La cinta densa completa (59049 celdas) vive aqui; no hay overlay ni
// pereza: se rellena entera al comienzo de cada runProgram.
var mem: [MEM_SIZE]u16 = undefined;

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

fn decodeOpcode(cell: u16, c: u32) u32 {
    return (@as(u32, cell) + c) % 94;
}

/// Carga `cells` en la cinta y la rellena por la recurrencia crazy.
/// Semillas del wrap (programas de <2 celdas) = mem[MEM_SIZE-1] == 0 porque
/// la cinta se cero-inicializa antes (autoridad Python: array pre-rellenado).
fn loadMemory(cells: []const u32) void {
    @memset(&mem, 0);
    var i: usize = 0;
    while (i < cells.len and i < MEM_SIZE) : (i += 1) {
        mem[i] = @intCast(cells[i]);
    }
    i = @min(cells.len, MEM_SIZE);
    while (i < MEM_SIZE) : (i += 1) {
        const prev1 = if (i >= 1) mem[i - 1] else mem[MEM_SIZE - 1];
        const prev2 = if (i >= 2) mem[i - 2] else mem[MEM_SIZE - 1];
        mem[i] = @intCast(crazy(prev1, prev2));
    }
}

pub fn runProgram(cells: []const u32, input: []const u8, max_steps: u32) RunOutcome {
    loadMemory(cells);

    var a: u32 = 0;
    var c: u32 = 0;
    var d: u32 = 0;
    var executed: u64 = 0;
    var terminated = false;
    var input_pos: usize = 0;
    var output_len: usize = 0;

    while (executed < max_steps) {
        executed += 1;
        const op = decodeOpcode(mem[@intCast(c)], c);
        var jumped = false;
        var c_target: u32 = 0;
        switch (op) {
            4 => {
                c_target = mem[@intCast(d)];
                jumped = true;
            },
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
                const r = rotate(mem[@intCast(d)]);
                mem[@intCast(d)] = @intCast(r);
                a = r;
            },
            40 => d = mem[@intCast(d)],
            62 => {
                const r = crazy(a, mem[@intCast(d)]);
                mem[@intCast(d)] = @intCast(r);
                a = r;
            },
            81 => {
                terminated = true;
                break;
            },
            else => {},
        }
        if (jumped) c = c_target;
        const enc = mem[@intCast(c)];
        if (enc >= 33 and enc <= 126) mem[@intCast(c)] = ENCRYPT[enc - 33];
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