// dsl.zig - ISA semantica del workload Autobolge (v0).
//
// No es un lenguaje de proposito general: es una maquina de busqueda con
// sintaxis programable. El programa describe LA BUSQUEDA (no el computo),
// y este runtime Zig sabe exactamente que significa cada primitiva:
//
//   FRONTIER <target> LENGTH <n> [MAX_STEPS <n>] [INPUT <s>] [EMIT <path>]
//     = ENUMERATE + EXECUTE + FILTER(output==target) + EMIT(evidencia)
//   CATALOG LENGTH <n> [MAX_STEPS <n>] [INPUT <s>] [EMIT <path>]
//     = ENUMERATE + EXECUTE + DEDUP(outputs) + EMIT(catalogo + resumen)
//
// Extension de programa: .bolge  (una linea = un comando, '#' = comentario)
//
// Uso: bolge-dsl.exe <programa.bolge>
//
// El runtime comparte vm.zig con bolge.exe (la maquina gate-verificada).
// Futuras primitivas (v1): FILTER/PRUNE por predicado, TRACE por hit,
// CHECK contra cache de referencia, benchmark (Zig puro vs DSL).

const std = @import("std");
const vm = @import("vm.zig");

const OPS_VALID = [_]u32{ 4, 5, 23, 39, 40, 62, 68, 81 };
const MAX_LENGTH: usize = 16;
const PROGRESS_FRONTIER: u64 = 64 * 1024 * 1024;
const PROGRESS_CATALOG: u64 = 8 * 1024 * 1024;

const Options = struct {
    target: []const u8 = "",
    length: usize = 0,
    max_steps: u32 = 3000,
    input: []const u8 = "",
    emit: []const u8 = "",
};

const Token = struct {
    text: []const u8,
    quoted: bool,
};

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

fn hexDigest(alloc: std.mem.Allocator, data: []const u8) ![]u8 {
    var digest: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(data, &digest, .{});
    var out = std.ArrayList(u8).empty;
    for (digest) |b| {
        var buf: [2]u8 = undefined;
        _ = std.fmt.bufPrint(&buf, "{x:0>2}", .{b}) catch unreachable;
        try out.appendSlice(alloc, &buf);
    }
    return out.items;
}

fn monoNow(io: std.Io) std.Io.Clock.Timestamp {
    return std.Io.Clock.Timestamp.now(io, .awake);
}

fn tokenizeLine(alloc: std.mem.Allocator, line: []const u8, out: *std.ArrayList(Token)) !void {
    var i: usize = 0;
    while (i < line.len) {
        while (i < line.len and (line[i] == ' ' or line[i] == '\t' or line[i] == '\r')) i += 1;
        if (i >= line.len) break;
        if (line[i] == '#') break;
        var quoted = false;
        if (line[i] == '"') {
            quoted = true;
            i += 1;
        }
        const start = i;
        if (quoted) {
            while (i < line.len and line[i] != '"') i += 1;
        } else {
            while (i < line.len and line[i] != ' ' and line[i] != '\t' and line[i] != '\r') i += 1;
        }
        try out.append(alloc, .{ .text = try alloc.dupe(u8, line[start..i]), .quoted = quoted });
        if (quoted and i < line.len and line[i] == '"') i += 1;
    }
}

fn fail(msg: []const u8) noreturn {
    std.debug.print("dsl: error: {s}\n", .{msg});
    std.process.exit(2);
}

fn parseOptions(toks: []const Token, start: usize, opts: *Options) void {
    var i = start;
    while (i + 1 < toks.len) : (i += 2) {
        const key = toks[i].text;
        const val = toks[i + 1];
        if (std.ascii.eqlIgnoreCase(key, "LENGTH")) {
            if (val.quoted) fail("LENGTH requiere un numero");
            opts.length = std.fmt.parseInt(usize, val.text, 10) catch fail("LENGTH mal formado");
        } else if (std.ascii.eqlIgnoreCase(key, "MAX_STEPS")) {
            if (val.quoted) fail("MAX_STEPS requiere un numero");
            opts.max_steps = std.fmt.parseInt(u32, val.text, 10) catch fail("MAX_STEPS mal formado");
        } else if (std.ascii.eqlIgnoreCase(key, "INPUT")) {
            opts.input = val.text;
        } else if (std.ascii.eqlIgnoreCase(key, "EMIT")) {
            opts.emit = val.text;
        } else {
            fail("opcion desconocida (LENGTH/MAX_STEPS/INPUT/EMIT)");
        }
    }
    if (i < toks.len) fail("opcion sin valor");
}

fn writeFile(io: std.Io, path: []const u8, data: []const u8) !void {
    const file = try std.Io.Dir.createFileAbsolute(io, path, .{});
    defer file.close(io);
    try file.writeStreamingAll(io, data);
}

fn runFrontier(io: std.Io, alloc: std.mem.Allocator, opts: Options) !void {
    if (opts.target.len == 0) fail("FRONTIER requiere target");
    if (opts.length == 0 or opts.length > MAX_LENGTH) fail("FRONTIER: LENGTH debe estar en 1..16");

    var chars: [MAX_LENGTH][8]u8 = undefined;
    for (0..opts.length) |pos| {
        for (OPS_VALID, 0..) |op, k| {
            chars[pos][k] = validCharAt(pos, op);
        }
    }

    const total: u64 = std.math.pow(u64, 8, @intCast(opts.length));
    var idx: [MAX_LENGTH]u8 = [_]u8{0} ** MAX_LENGTH;
    var cells: [MAX_LENGTH]u32 = undefined;
    for (0..opts.length) |pos| {
        cells[pos] = chars[pos][0];
    }

    const t0 = monoNow(io);
    var hits = std.ArrayList(u8).empty;
    try hits.appendSlice(alloc, "[");
    var n_hits: u64 = 0;

    var index: u64 = 0;
    while (index < total) : (index += 1) {
        const outcome = vm.runProgram(cells[0..opts.length], opts.input, opts.max_steps);
        if (std.mem.eql(u8, vm.out_buf[0..outcome.output_len], opts.target)) {
            if (n_hits > 0) try hits.append(alloc, ',');
            n_hits += 1;

            var prog = std.ArrayList(u8).empty;
            for (0..opts.length) |pos| {
                try prog.append(alloc, chars[pos][idx[pos]]);
            }
            try hits.appendSlice(alloc, "{\"program\":\"");
            try hits.appendSlice(alloc, try escapeJson(alloc, prog.items));
            try hits.appendSlice(alloc, "\",\"output\":\"");
            try hits.appendSlice(alloc, try escapeJson(alloc, vm.out_buf[0..outcome.output_len]));
            try hits.appendSlice(alloc, "\",\"steps\":");
            var nb: [32]u8 = undefined;
            try hits.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{outcome.steps}) catch unreachable);
            try hits.appendSlice(alloc, ",\"terminated\":");
            try hits.appendSlice(alloc, if (outcome.terminated) "true" else "false");
            try hits.appendSlice(alloc, ",\"final_pc\":");
            try hits.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{outcome.final_c}) catch unreachable);
            try hits.appendSlice(alloc, ",\"final_a\":");
            try hits.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{outcome.final_a}) catch unreachable);
            try hits.appendSlice(alloc, ",\"final_d\":");
            try hits.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{outcome.final_d}) catch unreachable);
            try hits.appendSlice(alloc, "}");
        }

        var pos: usize = opts.length;
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

        if (index + 1 == total or (index + 1) % PROGRESS_FRONTIER == 0) {
            const elapsed_ns = t0.untilNow(io).raw.nanoseconds;
            const rate: f64 = @as(f64, @floatFromInt(index + 1)) * 1e9 / @as(f64, @floatFromInt(@max(@as(i128, 1), elapsed_ns)));
            std.debug.print("  {d} / {d} ({d:.0} prog/s)\n", .{ index + 1, total, rate });
        }
    }
    try hits.appendSlice(alloc, "]");

    const elapsed_ns = t0.untilNow(io).raw.nanoseconds;
    const elapsed_s = @as(f64, @floatFromInt(elapsed_ns)) / 1e9;
    const rate: f64 = @as(f64, @floatFromInt(total)) * 1e9 / @as(f64, @floatFromInt(@max(@as(i128, 1), elapsed_ns)));

    var json = std.ArrayList(u8).empty;
    try json.appendSlice(alloc, "{\"target\":\"");
    try json.appendSlice(alloc, try escapeJson(alloc, opts.target));
    try json.appendSlice(alloc, "\",\"input\":\"");
    try json.appendSlice(alloc, try escapeJson(alloc, opts.input));
    try json.appendSlice(alloc, "\",\"length\":");
    var nb: [32]u8 = undefined;
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{opts.length}) catch unreachable);
    try json.appendSlice(alloc, ",\"max_steps\":");
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{opts.max_steps}) catch unreachable);
    try json.appendSlice(alloc, ",\"total_programs\":");
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{total}) catch unreachable);
    try json.appendSlice(alloc, ",\"elapsed_s\":");
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d:.3}", .{elapsed_s}) catch unreachable);
    try json.appendSlice(alloc, ",\"rate_prog_per_s\":");
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d:.1}", .{rate}) catch unreachable);
    try json.appendSlice(alloc, ",\"engine\":\"zig/vm.zig + zig/dsl.zig\",\"hits\":");
    try json.appendSlice(alloc, hits.items);
    try json.appendSlice(alloc, ",\"negative\":");
    try json.appendSlice(alloc, if (n_hits == 0) "true" else "false");
    const evidence_hash = try hexDigest(alloc, json.items);
    try json.appendSlice(alloc, ",\"sha256\":\"");
    try json.appendSlice(alloc, evidence_hash);
    try json.appendSlice(alloc, "\"}\n");

    if (opts.emit.len > 0) {
        try writeFile(io, opts.emit, json.items);
    }
    std.debug.print("  FRONTIER FINAL: {d} programas en {d:.1}s ({d:.0} prog/s), {d} hits, sha256 {s}\n", .{ total, elapsed_s, rate, n_hits, evidence_hash });
}

fn runCatalog(io: std.Io, alloc: std.mem.Allocator, opts: Options) !void {
    if (opts.length == 0 or opts.length > MAX_LENGTH) fail("CATALOG: LENGTH debe estar en 1..16");

    var chars: [MAX_LENGTH][8]u8 = undefined;
    for (0..opts.length) |pos| {
        for (OPS_VALID, 0..) |op, k| {
            chars[pos][k] = validCharAt(pos, op);
        }
    }

    var total: u64 = 0;
    for (0..opts.length + 1) |l| {
        total += std.math.pow(u64, 8, @intCast(l));
    }

    var distinct = std.StringHashMap(void).init(alloc);
    var longest_len: usize = 0;
    var longest_prog: []const u8 = "";
    var longest_out: []const u8 = "";

    const t0 = monoNow(io);
    var entries = std.ArrayList(u8).empty;
    try entries.appendSlice(alloc, "[");
    var n_entries: u64 = 0;
    var processed: u64 = 0;

    for (0..opts.length + 1) |length| {
        var idx: [MAX_LENGTH]u8 = [_]u8{0} ** MAX_LENGTH;
        var cells: [MAX_LENGTH]u32 = undefined;
        for (0..length) |pos| {
            cells[pos] = chars[pos][0];
        }
        const level_total: u64 = std.math.pow(u64, 8, @intCast(length));
        var level_index: u64 = 0;
        while (level_index < level_total) : (level_index += 1) {
            const outcome = vm.runProgram(cells[0..length], opts.input, opts.max_steps);
            if (n_entries > 0) try entries.append(alloc, ',');
            n_entries += 1;

            var prog = std.ArrayList(u8).empty;
            for (0..length) |pos| {
                try prog.append(alloc, chars[pos][idx[pos]]);
            }
            const output = try alloc.dupe(u8, vm.out_buf[0..outcome.output_len]);
            try distinct.put(output, {});

            try entries.appendSlice(alloc, "{\"program\":\"");
            try entries.appendSlice(alloc, try escapeJson(alloc, prog.items));
            try entries.appendSlice(alloc, "\",\"output\":\"");
            try entries.appendSlice(alloc, try escapeJson(alloc, output));
            try entries.appendSlice(alloc, "\",\"steps\":");
            var nb: [32]u8 = undefined;
            try entries.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{outcome.steps}) catch unreachable);
            try entries.appendSlice(alloc, ",\"terminated\":");
            try entries.appendSlice(alloc, if (outcome.terminated) "true" else "false");
            try entries.appendSlice(alloc, ",\"stop_reason\":\"");
            try entries.appendSlice(alloc, if (outcome.terminated) "StopReason.TERMINATED" else "StopReason.RUNNING");
            try entries.appendSlice(alloc, "\",\"final_a\":");
            try entries.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{outcome.final_a}) catch unreachable);
            try entries.appendSlice(alloc, ",\"final_pc\":");
            try entries.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{outcome.final_c}) catch unreachable);
            try entries.appendSlice(alloc, ",\"final_d\":");
            try entries.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{outcome.final_d}) catch unreachable);
            try entries.appendSlice(alloc, "}");

            if (outcome.output_len > longest_len) {
                longest_len = outcome.output_len;
                longest_prog = try alloc.dupe(u8, prog.items);
                longest_out = output;
            }

            processed += 1;
            if (processed % PROGRESS_CATALOG == 0) {
            const elapsed_ns = t0.untilNow(io).raw.nanoseconds;
                const rate: f64 = @as(f64, @floatFromInt(processed)) * 1e9 / @as(f64, @floatFromInt(@max(@as(i128, 1), elapsed_ns)));
                std.debug.print("  {d} / {d} ({d:.0} prog/s)\n", .{ processed, total, rate });
            }

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
        }
    }
    try entries.appendSlice(alloc, "]");

    const elapsed_ns = t0.untilNow(io).raw.nanoseconds;
    const elapsed_s = @as(f64, @floatFromInt(elapsed_ns)) / 1e9;
    const rate: f64 = @as(f64, @floatFromInt(total)) * 1e9 / @as(f64, @floatFromInt(@max(@as(i128, 1), elapsed_ns)));

    var json = std.ArrayList(u8).empty;
    try json.appendSlice(alloc, "{\"length\":");
    var nb: [32]u8 = undefined;
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{opts.length}) catch unreachable);
    try json.appendSlice(alloc, ",\"input\":\"");
    try json.appendSlice(alloc, try escapeJson(alloc, opts.input));
    try json.appendSlice(alloc, "\",\"max_steps\":");
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{opts.max_steps}) catch unreachable);
    try json.appendSlice(alloc, ",\"total_programs\":");
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{total}) catch unreachable);
    try json.appendSlice(alloc, ",\"distinct_outputs\":");
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{distinct.count()}) catch unreachable);
    try json.appendSlice(alloc, ",\"longest_output_len\":");
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d}", .{longest_len}) catch unreachable);
    try json.appendSlice(alloc, ",\"longest_example\":{\"program\":\"");
    try json.appendSlice(alloc, try escapeJson(alloc, longest_prog));
    try json.appendSlice(alloc, "\",\"output\":\"");
    try json.appendSlice(alloc, try escapeJson(alloc, longest_out));
    try json.appendSlice(alloc, "\"},\"elapsed_s\":");
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d:.3}", .{elapsed_s}) catch unreachable);
    try json.appendSlice(alloc, ",\"rate_prog_per_s\":");
    try json.appendSlice(alloc, std.fmt.bufPrint(&nb, "{d:.1}", .{rate}) catch unreachable);
    try json.appendSlice(alloc, ",\"engine\":\"zig/vm.zig + zig/dsl.zig\",\"entries\":");
    try json.appendSlice(alloc, entries.items);
    const evidence_hash = try hexDigest(alloc, json.items);
    try json.appendSlice(alloc, ",\"sha256\":\"");
    try json.appendSlice(alloc, evidence_hash);
    try json.appendSlice(alloc, "\"}\n");

    if (opts.emit.len > 0) {
        try writeFile(io, opts.emit, json.items);
    }
    std.debug.print("  CATALOG FINAL: {d} programas en {d:.1}s ({d:.0} prog/s), {d} outputs distintos, sha256 {s}\n", .{ total, elapsed_s, rate, distinct.count(), evidence_hash });
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
    if (args.len != 2) {
        std.debug.print("usage: bolge-dsl.exe <programa.bolge>\n", .{});
        std.process.exit(1);
    }

    const src = std.Io.Dir.cwd().readFileAlloc(io, args[1], alloc, .unlimited) catch |e| {
        std.debug.print("dsl: no puedo leer {s}: {s}\n", .{ args[1], @errorName(e) });
        std.process.exit(1);
    };

    vm.buildCrazy5();

    var lines = std.mem.splitScalar(u8, src, '\n');
    var n_cmds: usize = 0;
    while (lines.next()) |line| {
        var toks = std.ArrayList(Token).empty;
        try tokenizeLine(alloc, line, &toks);
        if (toks.items.len == 0) continue;
        n_cmds += 1;
        const cmd = toks.items[0].text;
        if (std.ascii.eqlIgnoreCase(cmd, "FRONTIER")) {
            if (toks.items.len < 2) fail("FRONTIER requiere target");
            var opts: Options = .{};
            opts.target = toks.items[1].text;
            parseOptions(toks.items, 2, &opts);
            std.debug.print("== FRONTIER target=\"{s}\" LENGTH {d} MAX_STEPS {d}\n", .{ opts.target, opts.length, opts.max_steps });
            try runFrontier(io, alloc, opts);
        } else if (std.ascii.eqlIgnoreCase(cmd, "CATALOG")) {
            if (toks.items.len < 2) fail("CATALOG requiere opciones");
            var opts: Options = .{};
            parseOptions(toks.items, 1, &opts);
            std.debug.print("== CATALOG LENGTH {d} MAX_STEPS {d}\n", .{ opts.length, opts.max_steps });
            try runCatalog(io, alloc, opts);
        } else {
            fail("comando desconocido (FRONTIER/CATALOG)");
        }
    }
    if (n_cmds == 0) fail("programa vacio");
}
