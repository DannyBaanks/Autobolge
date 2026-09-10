const std = @import("std");
const vm = @import("vm.zig");

fn reasonName(reason: vm.StopReason) []const u8 {
    return switch (reason) {
        .step_limit => "StopReason.RUNNING",
        .running => "StopReason.RUNNING",
        .halt => "StopReason.TERMINATED",
        .input_underflow => "StopReason.INPUT_UNDERFLOW",
        .output_limit => "StopReason.OUTPUT_LIMIT",
        .invalid_protocol_cell => "StopReason.INVALID_PROTOCOL_CELL",
    };
}

pub fn main(init: std.process.Init) !void {
    const allocator = init.gpa;
    var args = try std.process.Args.Iterator.initAllocator(init.minimal.args, allocator);
    defer args.deinit();
    _ = args.next() orelse return error.InvalidArguments;
    const program = args.next() orelse return error.InvalidArguments;
    const input_data = args.next() orelse return error.InvalidArguments;
    const steps_text = args.next() orelse return error.InvalidArguments;
    if (args.next() != null) return error.InvalidArguments;

    var cells = try allocator.alloc(u32, program.len);
    for (program, 0..) |char, index| cells[index] = char;
    const max_steps = try std.fmt.parseInt(u32, steps_text, 10);
    var events = try allocator.alloc(vm.TraceEvent, max_steps);
    var sink = vm.TraceSink{ .events = events };
    var machine = vm.Vm.init();
    const outcome = machine.runProgramWithTrace(cells, input_data, max_steps, &sink);
    std.debug.print("{{\"schema\":\"autobolge-trace/v1\",\"events\":[", .{});
    for (events[0..sink.len], 0..) |event, index| {
        if (index != 0) std.debug.print(",", .{});
        std.debug.print("{{\"step\":{},\"pre_a\":{},\"pre_c\":{},\"pre_d\":{},\"opcode\":{},\"effects\":{},\"post_a\":{},\"post_c\":{},\"post_d\":{},\"reason\":\"{s}\"}}", .{
            event.step, event.pre_a, event.pre_c, event.pre_d, event.opcode,
            event.effects, event.post_a, event.post_c, event.post_d,
            reasonName(event.reason),
        });
    }
    std.debug.print("],\"outcome\":{{\"steps\":{},\"terminated\":{},\"reason\":\"{s}\",\"output_len\":{},\"final_a\":{},\"final_c\":{},\"final_d\":{}}}}}\n", .{
        outcome.steps, outcome.terminated, reasonName(outcome.reason), outcome.output_len,
        outcome.final_a, outcome.final_c, outcome.final_d,
    });
}
