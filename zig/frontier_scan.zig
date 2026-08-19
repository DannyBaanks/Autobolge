// frontier_scan.zig - Escaneo exhaustivo del frontier de Autobolge, TODO en
// Zig (sin Python en el hot path).
//
// Enumera TODOS los programas validos de longitud exacta `length`
// (8^length candidatos, orden mixed-radix con los mismos caracteres validos
// que build_catalog), los ejecuta con vm.zig (misma maquina que bolge.exe),
// filtra los que producen el output objetivo y escribe evidencia JSON.
//
// Uso: frontier_scan.exe <target> <length> <out.json> [max_steps]
//
// La evidencia incluye: total de programas, tiempo, tasa, hits (con
// programa, output, steps, terminated, estado final) y el negativo honesto.

const std = @import("std");
const vm = @import("vm.zig");

const OPS_VALID = [_]u32{ 4, 5, 23, 39, 40, 62, 68, 81 };
const MAX_LENGTH: usize = 16;
const PROGRESS_EVERY: u64 = 64 * 1024 * 1024;

// Caracter valido en la posicion `pos` para el opcode `op`:
// chr(33 + (opcode - 33 - pos) % 94)  -- misma formula que valid_opcode_chars
fn validCharAt(pos: usize, op: u32) u8 {
    const v: i64 = 33 + @mod(@as(i64, op) - 33 - @as(i64, @intCast(pos)), 94);
    return @intCast(v);
}

fn escapeJson(alloc: std.mem.Allocator, bytes: []const u8) ![]u8 {
    var out = std.ArrayList(u8).empty;
    for (bytes) |b| {
        if (b == '"') {
            try out.appendSlice(alloc, "\\\"");
        } else if (b == '\\') {
            try out.appendSlice(alloc, "\\\\");
        } else if (b >= 32 and b < 127) {
            try out.append(alloc, b);
        } else {
            var buf: [6]u8 = undefined;
            _ = std.fmt.bufPrint(&buf, "\\u00{x:0>2}", .{b}) catch unreachable;
            try out.appendSlice(alloc, &buf);
        }
    }
    return out.items;
}

fn monoNow(io: std.Io) std.Io.Clock.Timestamp {
    return std.Io.Clock.Timestamp.now(io, .awake);
}

pub fn main(init: std.process.Init) !void {
    const io = init.io;
    const alloc = init.arena.allocator();

    var args_it = try std.process.Args.Iterator.initAllocator(init.minimal.args, alloc);
    defer args_it.deinit();
    var arg_list: std.ArrayList([]const u8) = .empty;
    while (args_it.next()) |arg| {
        try arg_list.append(alloc, try alloc.dupe(u8, arg));
    }
    const args = arg_list.items;
    if (args.len < 4 or args.len > 5) {
        std.debug.print("usage: frontier_scan.exe <target> <length> <out.json> [max_steps]\n", .{});
        std.process.exit(1);
    }
    const target = args[1];
    const length = std.fmt.parseInt(usize, args[2], 10) catch {
        std.debug.print("frontier: bad length\n", .{});
        std.process.exit(2);
    };
    const out_path = args[3];
    const max_steps = if (args.len == 5)
        std.fmt.parseInt(u32, args[4], 10) catch {
            std.debug.print("frontier: bad max_steps\n", .{});
            std.process.exit(2);
        }
    else
        3000;

    if (length == 0 or length > MAX_LENGTH) {
        std.debug.print("frontier: length must be in 1..{d}\n", .{MAX_LENGTH});
        std.process.exit(2);
    }

    vm.buildCrazy5();

    // tablas de caracteres validos por posicion (orden OPS_VALID, igual que
    // build_catalog / valid_opcode_chars)
    var chars: [MAX_LENGTH][8]u8 = undefined;
    for (0..length) |pos| {
        for (OPS_VALID, 0..) |op, k| {
            chars[pos][k] = validCharAt(pos, op);
        }
    }

    const total: u64 = std.math.pow(u64, 8, @intCast(length));
    var idx: [MAX_LENGTH]u8 = [_]u8{0} ** MAX_LENGTH; // indice 0..7 por posicion
    var cells: [MAX_LENGTH]u32 = undefined;
    for (0..length) |pos| {
        cells[pos] = chars[pos][0];
    }

    const t0 = monoNow(io);
    var hits = std.ArrayList(u8).empty; // JSON de hits
    try hits.appendSlice(alloc, "[");

    var index: u64 = 0;
    var first = true;
    while (index < total) : (index += 1) {
        const outcome = vm.runProgram(cells[0..length], "", max_steps);
        if (std.mem.eql(u8, vm.out_buf[0..outcome.output_len], target)) {
            if (!first) try hits.append(alloc, ',');
            first = false;

            var prog = std.ArrayList(u8).empty;
            for (0..length) |pos| {
                try prog.append(alloc, chars[pos][idx[pos]]);
            }

            try hits.appendSlice(alloc, "{\"program\":\"");
            try hits.appendSlice(alloc, try escapeJson(alloc, prog.items));
            try hits.appendSlice(alloc, "\",\"output\":\"");
            try hits.appendSlice(alloc, try escapeJson(alloc, vm.out_buf[0..outcome.output_len]));
            try hits.appendSlice(alloc, "\",\"steps\":");
            var nb: [32]u8 = undefined;
            const steps_s = std.fmt.bufPrint(&nb, "{d}", .{outcome.steps}) catch unreachable;
            try hits.appendSlice(alloc, steps_s);
            try hits.appendSlice(alloc, ",\"terminated\":");
            try hits.appendSlice(alloc, if (outcome.terminated) "true" else "false");
            try hits.appendSlice(alloc, ",\"final_pc\":");
            const pc_s = std.fmt.bufPrint(&nb, "{d}", .{outcome.final_c}) catch unreachable;
            try hits.appendSlice(alloc, pc_s);
            try hits.appendSlice(alloc, ",\"final_a\":");
            const a_s = std.fmt.bufPrint(&nb, "{d}", .{outcome.final_a}) catch unreachable;
            try hits.appendSlice(alloc, a_s);
            try hits.appendSlice(alloc, ",\"final_d\":");
            const d_s = std.fmt.bufPrint(&nb, "{d}", .{outcome.final_d}) catch unreachable;
            try hits.appendSlice(alloc, d_s);
            try hits.appendSlice(alloc, "}");
        }

        // siguiente programa (mixed-radix; posicion 0 = mas significativa)
        var pos: usize = length;
        while (pos > 0) {
            pos -= 1;
            if (idx[pos] < 7) {
                idx[pos] += 1;
                cells[pos] = chars[pos][idx[pos]];
                break;
            }
            idx[pos] = 0;
            cells[pos] = chars[pos][0];
        }

        if (index + 1 == total or (index + 1) % PROGRESS_EVERY == 0) {
            const elapsed_ns = t0.untilNow(io).raw.nanoseconds;
            const elapsed_ms = @as(u64, @intCast(elapsed_ns)) / 1_000_000;
            const rate: f64 = @as(f64, @floatFromInt(index + 1)) * 1e9 / @as(f64, @floatFromInt(@max(@as(i128, 1), elapsed_ns)));
            std.debug.print("  {d} / {d} en {d} ms ({d:.0} prog/s)\n", .{ index + 1, total, elapsed_ms, rate });
        }
    }

    try hits.appendSlice(alloc, "]");

    const elapsed_ns = t0.untilNow(io).raw.nanoseconds;
    const elapsed_s = @as(f64, @floatFromInt(elapsed_ns)) / 1e9;
    const rate: f64 = @as(f64, @floatFromInt(total)) * 1e9 / @as(f64, @floatFromInt(@max(@as(i128, 1), elapsed_ns)));

    var json = std.ArrayList(u8).empty;
    try json.appendSlice(alloc, "{\"target\":\"");
    try json.appendSlice(alloc, try escapeJson(alloc, target));
    try json.appendSlice(alloc, "\",\"input\":\"\",\"length\":");
    var nb: [32]u8 = undefined;
    const len_s = std.fmt.bufPrint(&nb, "{d}", .{length}) catch unreachable;
    try json.appendSlice(alloc, len_s);
    try json.appendSlice(alloc, ",\"total_programs\":");
    const tot_s = std.fmt.bufPrint(&nb, "{d}", .{total}) catch unreachable;
    try json.appendSlice(alloc, tot_s);
    try json.appendSlice(alloc, ",\"elapsed_s\":");
    const el_s = std.fmt.bufPrint(&nb, "{d:.3}", .{elapsed_s}) catch unreachable;
    try json.appendSlice(alloc, el_s);
    try json.appendSlice(alloc, ",\"rate_prog_per_s\":");
    const ra_s = std.fmt.bufPrint(&nb, "{d:.1}", .{rate}) catch unreachable;
    try json.appendSlice(alloc, ra_s);
    try json.appendSlice(alloc, ",\"engine\":\"zig/vm.zig\",\"hits\":");
    try json.appendSlice(alloc, hits.items);
    try json.appendSlice(alloc, ",\"negative\":");
    try json.appendSlice(alloc, if (first) "true" else "false");
    try json.appendSlice(alloc, "}\n");

    const file = try std.Io.Dir.createFileAbsolute(io, out_path, .{});
    defer file.close(io);
    try file.writeStreamingAll(io, json.items);

    std.debug.print("  FINAL: {d} programas en {d:.1}s ({d:.0} prog/s), hits: {s}\n", .{ total, elapsed_s, rate, if (first) "0" else "1+" });
}