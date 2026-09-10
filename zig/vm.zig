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

fn buildCrazy5Table() [HALF][HALF]u32 {
    @setEvalBranchQuota(1_000_000);
    var table: [HALF][HALF]u32 = undefined;
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
            table[a5][b5] = r;
        }
    }
    return table;
}

const crazy5 = buildCrazy5Table();

pub const OUT_CAP: usize = 65536;

// BOLG2 serializa este enum como u8. Los valores 0/1 preservan el contrato
// anterior; 2+ separan causas que antes quedaban colapsadas en "terminated".
pub const StopReason = enum(u8) {
    step_limit = 0,
    halt = 1,
    input_underflow = 2,
    output_limit = 3,
    invalid_protocol_cell = 4,
    running = 5,
};

pub const RunOutcome = struct {
    steps: u64,
    terminated: bool,
    reason: StopReason,
    output_len: usize,
    final_c: u32,
    final_a: u32,
    final_d: u32,
};

pub const TraceEvent = struct {
    step: u64,
    pre_c: u32,
    pre_a: u32,
    pre_d: u32,
    opcode: u32,
    effects: u8, // 1 jump, 2 output, 4 input, 8 memory write, 16 encrypt
    post_c: u32,
    post_a: u32,
    post_d: u32,
    reason: StopReason,
};

pub const TraceSink = struct {
    events: []TraceEvent,
    len: usize = 0,
    dropped: usize = 0,

    pub fn append(self: *TraceSink, event: TraceEvent) void {
        if (self.len < self.events.len) {
            self.events[self.len] = event;
            self.len += 1;
        } else {
            self.dropped += 1;
        }
    }
};

fn recordTrace(trace: ?*TraceSink, step: u64, pre_c: u32, pre_a: u32, pre_d: u32, opcode: u32, effects: u8, post_c: u32, post_a: u32, post_d: u32, reason: StopReason) void {
    if (trace) |sink| sink.append(.{
        .step = step,
        .pre_c = pre_c,
        .pre_a = pre_a,
        .pre_d = pre_d,
        .opcode = opcode,
        .effects = effects,
        .post_c = post_c,
        .post_a = post_a,
        .post_d = post_d,
        .reason = reason,
    });
}

// El estado mutable pertenece a la instancia. Esto permite que batches y
// ramas futuras ejecuten VMs intercaladas sin pisarse la cinta ni el output.
pub const Vm = struct {
    mem: [MEM_SIZE]u16,
    out_buf: [OUT_CAP]u8,

    pub fn init() Vm {
        return .{
            .mem = undefined,
            .out_buf = undefined,
        };
    }

    fn loadMemory(self: *Vm, cells: []const u32) void {
        @memset(&self.mem, 0);
        var i: usize = 0;
        while (i < cells.len and i < MEM_SIZE) : (i += 1) {
            self.mem[i] = @intCast(cells[i]);
        }
        i = @min(cells.len, MEM_SIZE);
        while (i < MEM_SIZE) : (i += 1) {
            const prev1 = if (i >= 1) self.mem[i - 1] else self.mem[MEM_SIZE - 1];
            const prev2 = if (i >= 2) self.mem[i - 2] else self.mem[MEM_SIZE - 1];
            self.mem[i] = @intCast(crazy(prev1, prev2));
        }
    }

    pub fn runProgram(self: *Vm, cells: []const u32, input: []const u8, max_steps: u32) RunOutcome {
        return self.runProgramWithOutputCap(cells, input, max_steps, OUT_CAP);
    }

    pub fn runProgramWithTrace(self: *Vm, cells: []const u32, input: []const u8, max_steps: u32, trace: *TraceSink) RunOutcome {
        return self.runProgramWithOutputCapAndTrace(cells, input, max_steps, OUT_CAP, trace);
    }

    // Hook de prueba y de recursos: la API normal usa OUT_CAP, mientras que
    // los callers con presupuesto propio pueden validar output_limit.
    pub fn runProgramWithOutputCap(self: *Vm, cells: []const u32, input: []const u8, max_steps: u32, output_cap: usize) RunOutcome {
        return self.runProgramWithOutputCapAndTrace(cells, input, max_steps, output_cap, null);
    }

    fn runProgramWithOutputCapAndTrace(self: *Vm, cells: []const u32, input: []const u8, max_steps: u32, output_cap: usize, trace: ?*TraceSink) RunOutcome {
        for (cells) |cell| {
            if (cell > std.math.maxInt(u16)) return .{
                .steps = 0,
                .terminated = false,
                .reason = .invalid_protocol_cell,
                .output_len = 0,
                .final_c = 0,
                .final_a = 0,
                .final_d = 0,
            };
        }
        self.loadMemory(cells);

        var a: u32 = 0;
        var c: u32 = 0;
        var d: u32 = 0;
        var executed: u64 = 0;
        var terminated = false;
        var reason: StopReason = .step_limit;
        var input_pos: usize = 0;
        var output_len: usize = 0;

        run_loop: while (executed < max_steps) {
            executed += 1;
            const pre_c = c;
            const pre_a = a;
            const pre_d = d;
            const op = decodeOpcode(self.mem[@intCast(c)], c);
            var effects: u8 = 0;
            var jumped = false;
            var c_target: u32 = 0;
            switch (op) {
                4 => {
                    c_target = self.mem[@intCast(d)];
                    jumped = true;
                    effects |= 1;
                },
                5 => {
                    if (output_len < output_cap and output_len < OUT_CAP) {
                        self.out_buf[output_len] = @intCast(a % 256);
                        output_len += 1;
                        effects |= 2;
                    } else {
                        reason = .output_limit;
                        recordTrace(trace, executed, pre_c, pre_a, pre_d, op, effects, c, a, d, reason);
                        break :run_loop;
                    }
                },
                23 => {
                    if (input_pos < input.len) {
                        a = input[input_pos];
                        input_pos += 1;
                        effects |= 4;
                    } else {
                        terminated = true;
                        reason = .input_underflow;
                        recordTrace(trace, executed, pre_c, pre_a, pre_d, op, effects, c, a, d, reason);
                        break :run_loop;
                    }
                },
                39 => {
                    const r = rotate(self.mem[@intCast(d)]);
                    self.mem[@intCast(d)] = @intCast(r);
                    a = r;
                    effects |= 8;
                },
                40 => d = self.mem[@intCast(d)],
                62 => {
                    const r = crazy(a, self.mem[@intCast(d)]);
                    self.mem[@intCast(d)] = @intCast(r);
                    a = r;
                    effects |= 8;
                },
                81 => {
                    terminated = true;
                    reason = .halt;
                    recordTrace(trace, executed, pre_c, pre_a, pre_d, op, effects, c, a, d, reason);
                    break :run_loop;
                },
                else => {},
            }
            if (jumped) c = c_target;
            const enc = self.mem[@intCast(c)];
            if (enc >= 33 and enc <= 126) {
                self.mem[@intCast(c)] = ENCRYPT[enc - 33];
                effects |= 16;
            }
            c = if (c == LAST) 0 else c + 1;
            d = if (d == LAST) 0 else d + 1;
            recordTrace(trace, executed, pre_c, pre_a, pre_d, op, effects, c, a, d, .running);
        }

        return .{
            .steps = executed,
            .terminated = terminated,
            .reason = reason,
            .output_len = output_len,
            .final_c = c,
            .final_a = a,
            .final_d = d,
        };
    }
};

test "Vm instances keep independent mutable state" {
    buildCrazy5();
    var first = Vm.init();
    var second = Vm.init();
    const cells = [_]u32{ 'u', 'b' };

    const first_outcome = first.runProgram(&cells, "A", 100);
    var first_output: [OUT_CAP]u8 = undefined;
    @memcpy(first_output[0..first_outcome.output_len], first.out_buf[0..first_outcome.output_len]);
    const first_mem0 = first.mem[0];

    _ = second.runProgram(&cells, "B", 100);

    try std.testing.expectEqualSlices(u8, first_output[0..first_outcome.output_len], first.out_buf[0..first_outcome.output_len]);
    try std.testing.expectEqual(first_mem0, first.mem[0]);
}

test "Vm reports an explicit output limit" {
    buildCrazy5();
    var machine = Vm.init();
    const cells = [_]u32{ 'c' };
    const outcome = machine.runProgramWithOutputCap(&cells, "", 100, 0);
    try std.testing.expectEqual(@as(u8, 3), @intFromEnum(outcome.reason));
    try std.testing.expect(!outcome.terminated);
}

test "Vm rejects protocol cells outside u16" {
    buildCrazy5();
    var machine = Vm.init();
    const cells = [_]u32{ 65536 };
    const outcome = machine.runProgram(&cells, "", 10);
    try std.testing.expectEqual(@as(u8, 4), @intFromEnum(outcome.reason));
    try std.testing.expectEqual(@as(u64, 0), outcome.steps);
}

test "Vm emits bounded deterministic trace events" {
    buildCrazy5();
    var machine = Vm.init();
    var events: [64]TraceEvent = undefined;
    var sink = TraceSink{ .events = &events };
    const cells = [_]u32{ 'u', 'b' };
    const outcome = machine.runProgramWithTrace(&cells, "A", 100, &sink);
    try std.testing.expectEqual(outcome.steps, sink.len);
    try std.testing.expectEqual(@as(usize, 0), sink.dropped);
    try std.testing.expectEqual(@as(u64, 1), sink.events[0].step);
    try std.testing.expectEqual(outcome.reason, sink.events[sink.len - 1].reason);

    var short_events: [1]TraceEvent = undefined;
    var short_sink = TraceSink{ .events = &short_events };
    _ = machine.runProgramWithTrace(&cells, "A", 100, &short_sink);
    try std.testing.expect(short_sink.dropped > 0);
}

pub fn buildCrazy5() void {
    // Compatibilidad con callers v1; la tabla ya existe en tiempo de compilacion.
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
