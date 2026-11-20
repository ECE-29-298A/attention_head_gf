`timescale 1ns/1ps
// Divider contract: start is accepted when idle and latches sum_in; denominator
// is held by the caller until done; starts while busy are ignored; done pulses
// once, 24 edges after the accepted start; result is valid from done until the
// next start. Everything the contract leaves free is driven with random data.
module tb_divider;
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, start = 0;
    logic signed [19:0] sum_in = 0;
    logic [11:0] denominator = 1;
    wire done;
    wire signed [11:0] result;
    divider dut (.*);
    wire busy = dut.state != dut.IDLE;

    task automatic reset_block(input int length);
        rst_n = 0; start = 1'($urandom); sum_in = 20'($urandom);
        repeat (length) @(negedge clk);
        assert (!busy) else $fatal(1, "Reset did not idle the divider");
        rst_n = 1; start = 0;
    endtask

    task automatic check(input int value, divisor, expected);
        // Called at a falling edge; the next rising edge accepts start.
        assert (!busy) else $fatal(1, "Previous division still busy");
        sum_in = 20'(value); denominator = 12'(divisor); start = 1;
        @(negedge clk);
        assert (busy && !done) else $fatal(1, "Start was not accepted");
        for (int cycle = 1; cycle <= 24; cycle++) begin
            // sum_in is latched; random starts while busy must be ignored.
            sum_in = 20'($urandom);
            start = $urandom_range(0, 3) == 0;
            @(negedge clk);
            if (cycle < 24)
                assert (busy && !done) else $fatal(1, "Early completion at cycle %0d", cycle);
            else
                assert (!busy && done && result == 12'(expected))
                    else $fatal(1, "O=%0d L=%0d: got %0d expected %0d", value, divisor, result, expected);
        end
        start = 0;
        // Idle with random inputs: done must not repeat and result must hold.
        repeat ($urandom_range(0, 7) == 0 ? $urandom_range(1, 5) : 0) begin
            sum_in = 20'($urandom); denominator = 12'($urandom);
            @(negedge clk);
            assert (!busy && !done && result == 12'(expected))
                else $fatal(1, "Result not held or done repeated while idle");
        end
    endtask

    string path;
    int fd, value, divisor, expected, checked = 0, status;
    initial begin
        reset_block(1);  // power-up state is random: one clock of reset must be enough
        // Abort at every divider stage, including the rounding state.
        for (int delay_cycles = 0; delay_cycles < 24; delay_cycles++) begin
            start = 1; sum_in = -522240; denominator = 4080;
            @(negedge clk); start = 0;
            repeat (delay_cycles) @(negedge clk);
            reset_block(delay_cycles % 2 + 1);
            @(negedge clk);  // a ROUND cut by reset may still pulse done here; it is ignored
            repeat (26) begin
                @(negedge clk);
                assert (!busy && !done) else $fatal(1, "Activity after reset");
            end
            check(-1, 2, -8);  // -1/2 = -0.5 = -8 sixteenths
        end
        assert ($value$plusargs("VECTORS=%s", path)) else $fatal(1, "Missing vectors");
        fd = $fopen(path, "r");
        assert (fd != 0) else $fatal(1, "Cannot read vectors");
        status = $fscanf(fd, "%d %d %d", value, divisor, expected);
        while (status == 3) begin
            check(value, divisor, expected);
            checked++;
            status = $fscanf(fd, "%d %d %d", value, divisor, expected);
        end
        assert (status == -1 && checked > 100000) else $fatal(1, "Incomplete vector file");
        $display("PASS: divider %0d vectors; 24-cycle latency, 12-bit signed rounding, sum latching, ignored busy starts, idle hold, resets at every step", checked);
        $finish;
    end
    initial begin #1000000000; $fatal(1, "Divider timeout"); end
endmodule
