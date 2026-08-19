// bolge.zig - CLI batch de la maquina Malbolge (motor Zig para el hot path
// del sintetizador). La maquina vive en vm.zig (semantica EXACTA del
// debugger del paquete `malbolge` con SparseMemory, incluyendo su
// lazy-fill con overlay).
//
// Interfaz: bolge.exe <in.bin> <out.bin>
//   in.bin:  "BOLG1" + u64 count + count records
//   record:  u32 prog_len + prog_len*u32 (celdas, LE) + u32 input_len +
//            input_len*u8 + u32 max_steps
//   out.bin: "BOLG2" + u64 count + count results
//   result:  u32 output_len + output_len*u8 + u64 steps + u8 terminated +
//            u8 reason(0=running,1=terminated) + u32 final_c + u32 final_a +
//            u32 final_d

const std = @import("std");
const vm = @import("vm.zig");

fn readU32(data: []const u8, pos: *usize) !u32 {
    if (pos.* + 4 > data.len) return error.BadInput;
    const v = std.mem.readInt(u32, data[pos.*..][0..4], .little);
    pos.* += 4;
    return v;
}

fn readU64(data: []const u8, pos: *usize) !u64 {
    if (pos.* + 8 > data.len) return error.BadInput;
    const v = std.mem.readInt(u64, data[pos.*..][0..8], .little);
    pos.* += 8;
    return v;
}

fn writeU32(alloc: std.mem.Allocator, list: *std.ArrayList(u8), v: u32) !void {
    var buf: [4]u8 = undefined;
    std.mem.writeInt(u32, &buf, v, .little);
    try list.appendSlice(alloc, &buf);
}

fn writeU64(alloc: std.mem.Allocator, list: *std.ArrayList(u8), v: u64) !void {
    var buf: [8]u8 = undefined;
    std.mem.writeInt(u64, &buf, v, .little);
    try list.appendSlice(alloc, &buf);
}

fn runRecord(alloc: std.mem.Allocator, cells: []const u32, input: []const u8, max_steps: u32, out: *std.ArrayList(u8)) !void {
    const outcome = vm.runProgram(cells, input, max_steps);
    const out_start = out.items.len;
    try out.appendNTimes(alloc, 0, 4); // placeholder para output_len
    try out.appendSlice(alloc, vm.out_buf[0..outcome.output_len]);
    const olen: u32 = @intCast(outcome.output_len);
    var lenbuf: [4]u8 = undefined;
    std.mem.writeInt(u32, &lenbuf, olen, .little);
    @memcpy(out.items[out_start..][0..4], &lenbuf);
    try writeU64(alloc, out, outcome.steps);
    try out.append(alloc, if (outcome.terminated) 1 else 0);
    try out.append(alloc, if (outcome.terminated) 1 else 0);
    try writeU32(alloc, out, outcome.final_c);
    try writeU32(alloc, out, outcome.final_a);
    try writeU32(alloc, out, outcome.final_d);
}

fn usage() void {
    std.debug.print("usage: bolge.exe <in.bin> <out.bin>\n", .{});
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
    if (args.len != 3) {
        usage();
        std.process.exit(1);
    }

    vm.buildCrazy5();

    const data = try (std.Io.Dir.cwd()).readFileAlloc(io, args[1], alloc, .unlimited);
    defer alloc.free(data);

    if (data.len < 13 or !std.mem.eql(u8, data[0..5], "BOLG1")) {
        std.debug.print("bolge: bad input file\n", .{});
        std.process.exit(2);
    }
    var pos: usize = 5;
    const count = readU64(data, &pos) catch {
        std.debug.print("bolge: truncated input file\n", .{});
        std.process.exit(2);
    };

    var out = std.ArrayList(u8).empty;
    defer out.deinit(alloc);

    try out.appendSlice(alloc, "BOLG2");
    try writeU64(alloc, &out, count);

    var cells: [vm.MEM_SIZE]u32 = undefined;
    var r: u64 = 0;
    while (r < count) : (r += 1) {
        const plen = readU32(data, &pos) catch {
            std.debug.print("bolge: truncated record header\n", .{});
            std.process.exit(2);
        };
        if (plen > vm.MEM_SIZE or pos + @as(usize, plen) * 4 > data.len) {
            std.debug.print("bolge: bad program length\n", .{});
            std.process.exit(2);
        }
        var cell_i: usize = 0;
        while (cell_i < plen) : (cell_i += 1) {
            cells[cell_i] = readU32(data, &pos) catch {
                std.debug.print("bolge: truncated program cells\n", .{});
                std.process.exit(2);
            };
        }
        const ilen = readU32(data, &pos) catch {
            std.debug.print("bolge: truncated input length\n", .{});
            std.process.exit(2);
        };
        if (pos + @as(usize, ilen) > data.len) {
            std.debug.print("bolge: bad input length\n", .{});
            std.process.exit(2);
        }
        const input = data[pos .. pos + ilen];
        pos += ilen;
        const max_steps = readU32(data, &pos) catch {
            std.debug.print("bolge: truncated max_steps\n", .{});
            std.process.exit(2);
        };
        if (max_steps == 0) {
            std.debug.print("bolge: max_steps must be > 0\n", .{});
            std.process.exit(2);
        }
        runRecord(alloc, cells[0..plen], input, max_steps, &out) catch |err| {
            std.debug.print("bolge: run error: {s}\n", .{@errorName(err)});
            std.process.exit(2);
        };
    }

    if (pos != data.len) {
        std.debug.print("bolge: trailing bytes in input file\n", .{});
        std.process.exit(2);
    }

    const file = try std.Io.Dir.createFileAbsolute(io, args[2], .{});
    defer file.close(io);
    try file.writeStreamingAll(io, out.items);
}