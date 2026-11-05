`timescale 1ns/1ps
module tb_divider;
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, start = 0;
    logic signed [15:0] sum_in = 0;
    logic [11:0] denominator = 1;
    wire busy, done;
    wire signed [7:0] result;
    divider dut (.*);

    task automatic reset_block;
        rst_n = 0; start = 0;
        repeat (2) @(negedge clk);
        assert (!busy && !done && result == 0) else $fatal(1, "Reset failed");
        rst_n = 1;
    endtask

    task automatic check(input int value, divisor, expected, input bit disturb);
        logic signed [7:0] previous_result;
        // Called at a falling edge; next rising edge accepts start.
        assert (!busy) else $fatal(1, "Previous division still busy");
        previous_result = result;
        sum_in = 16'(value); denominator = 12'(divisor); start = 1;
        @(negedge clk);
        assert (busy && !done) else $fatal(1, "Start was not accepted");
        start = 0;
        // Test input latching and ignore-start-while-busy without altering the answer.
        for (int cycle = 1; cycle <= 20; cycle++) begin
            sum_in = 16'h1234; denominator = 12'd3;
            start = disturb && (cycle == 3 || cycle == 19 || cycle == 20);
            @(negedge clk);
            if (cycle < 20) begin
                assert (busy && !done && result == previous_result)
                    else $fatal(1, "Early completion/result change at cycle %0d", cycle);
            end else begin
                assert (!busy && done && result == 8'(expected))
                    else $fatal(1, "O=%0d L=%0d: got %0d expected %0d", value, divisor, result, expected);
            end
        end
        start = 0;
    endtask

    string path;
    int fd, value, divisor, expected, checked = 0, status;
    initial begin
        reset_block();
        // Abort at every divider stage, including the rounding state.
        for (int delay_cycles = 0; delay_cycles < 20; delay_cycles++) begin
            start = 1; sum_in = -32640; denominator = 4080;
            @(negedge clk); start = 0;
            repeat (delay_cycles) @(negedge clk);
            reset_block();
            repeat (22) begin
                @(negedge clk);
                assert (!busy && !done && result == 0) else $fatal(1, "Stale completion after reset");
            end
            check(-1, 32, -1, 0);
        end
        assert ($value$plusargs("VECTORS=%s", path)) else $fatal(1, "Missing vectors");
        fd = $fopen(path, "r");
        assert (fd != 0) else $fatal(1, "Cannot read vectors");
        status = $fscanf(fd, "%d %d %d", value, divisor, expected);
        while (status == 3) begin
            check(value, divisor, expected, (checked % 97) == 0);
            // Most cases start immediately after done. Other cases test idle hold.
            if (checked % 101 == 0) begin
                repeat (4) begin
                    @(negedge clk);
                    assert (!busy && !done && result == 8'(expected))
                        else $fatal(1, "Result not held or done not a pulse");
                end
            end
            checked++;
            status = $fscanf(fd, "%d %d %d", value, divisor, expected);
        end
        assert (status == -1 && checked > 100000) else $fatal(1, "Incomplete vector file");
        $display("PASS: divider %0d vectors; 20-cycle latency, signed rounding, invalid inputs, input latching, busy starts, resets and consecutive operations", checked);
        $finish;
    end
    initial begin #100000000; $fatal(1, "Divider timeout"); end
endmodule
