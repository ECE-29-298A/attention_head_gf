`timescale 1ns/1ps
// White-box check of attention_controller with the real spi_read and the
// behavioural flash. Cases come from the Python model (test/controller/run.py)
// with its intermediate scores and weights, so a failure names the first wrong
// intermediate value. The host side (start, out_ready) is driven at random.
module tb_controller;
    localparam int K_BASE = 'h400, V_BASE = 'h800, SIZE = 'hC00;
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, start = 0, out_ready = 0;
    logic [3:0] last = 0, score_shift = 0, chunk = 0;
    wire idle, mem_req, mem_ack, rx_valid, mosi, sck, cs_n, miso, out_valid;
    wire [11:0] mem_addr;
    wire [7:0] out_data;
    attention_controller dut (.clk, .rst_n, .start, .last, .score_shift, .chunk, .idle,
        .mem_req, .mem_addr, .mem_ack, .rx_valid, .rx_bit(miso), .out_valid, .out_ready, .out_data);
    spi_read memory (.clk, .rst_n, .req(mem_req), .addr(mem_addr), .ack(mem_ack), .rx_valid,
                     .mosi, .sck, .cs_n);
    spi_flash_model #(.SIZE(SIZE)) flash (.clk, .abort_ok(!rst_n), .cs_n, .sck, .mosi,
                                          .mosi_oe(1'b1), .miso);
    wire div_start = dut.divider_unit.start && dut.divider_unit.state == 0;

    int count = 1, case_chunk = 0, expected [0:3], scores [0:15], weights [0:15];
    int expected_max, expected_l, expected_o [0:3], running_l, running_o [0:3];
    int captures, accumulated, div_calls, div_results, received, cycles, div_start_cycle;
    bit active_case = 0, force_output_stall = 0, stalled = 0, check_sums = 0;
    logic [7:0] held;

    function automatic logic [7:0] output_byte(input int index);
        logic [15:0] word = 16'(expected[index / 2]);
        return index % 2 != 0 ? word[15:8] : word[7:0];
    endfunction
    function automatic int value_component(input int token, component);
        return int'($signed(flash.memory[V_BASE + 64*token + 4*case_chunk + component]));
    endfunction
    function automatic int expected_reads(input int i);
        if (i < K_BASE) return i < 64 ? 2*count : 0;
        if (i < V_BASE) return (i - K_BASE)/64 < count ? 2 : 0;
        return (i - V_BASE)/64 < count && ((i - V_BASE)%64)/4 == case_chunk ? 1 : 0;
    endfunction

    always @(negedge clk) begin
        out_ready = !force_output_stall && $urandom_range(0, 3) == 0;
        // A start held during a run must be ignored (until the outputs, so no new run begins).
        if (active_case && !dut.idle && div_calls == 0) start = 1'($urandom);
    end
    always @(posedge clk) if (rst_n && active_case) begin
        cycles++;
        assert (cycles < 4000000) else $fatal(1, "Controller timeout");
        // Scores: one per token per pass, complete on the last MAC edge.
        if (dut.score_done) begin
            assert (captures < 2*count && dut.second_pass == (captures >= count) &&
                    dut.token == 4'(captures % count)) else $fatal(1, "Score %0d out of order", captures);
            assert (dut.score_next == 22'(scores[captures % count]))
                else $fatal(1, "Score %0d: RTL %0d, Python %0d", captures, dut.score_next, scores[captures % count]);
            captures++;
        end
        if (dut.second_pass && !dut.idle)
            assert (dut.maximum == 22'(expected_max))
                else $fatal(1, "Maximum: RTL %0d, Python %0d", dut.maximum, expected_max);
        // The ring rotates every clock: register k holds component (phase + k) % 4.
        if (check_sums)
            assert (dut.weight_sum == 12'(running_l) &&
                    dut.o0 == 20'(running_o[(dut.phase + 0) % 4]) &&
                    dut.o1 == 20'(running_o[(dut.phase + 1) % 4]) &&
                    dut.o2 == 20'(running_o[(dut.phase + 2) % 4]) &&
                    dut.o3 == 20'(running_o[(dut.phase + 3) % 4]))
                else $fatal(1, "Running sums mismatch after token %0d", accumulated);
        if (dut.state == dut.ACCUM) begin
            // exp_lut has no M < S guard: prove the controller never needs one.
            assert (dut.maximum >= dut.score) else $fatal(1, "exp_lut precondition M >= S broken");
            assert (accumulated < count && dut.token == 4'(accumulated) &&
                    dut.weight == 8'(weights[accumulated]))
                else $fatal(1, "Token %0d weight: RTL %0d, Python %0d", accumulated, dut.weight, weights[accumulated]);
            if (dut.phase == 0 && dut.bit_index == 0) running_l += weights[accumulated];
            if ((value_component(accumulated, dut.phase) >> dut.bit_index) & 1)
                running_o[dut.phase] += weights[accumulated] * (dut.bit_index == 7 ? -128 : (1 << dut.bit_index));
            if (dut.phase == 3 && dut.bit_index == 7) begin accumulated++; check_sums = 1; end
        end
        if (div_start) begin
            assert (div_calls < 4 && accumulated == count &&
                    dut.o0 == 20'(expected_o[div_calls]) && dut.weight_sum == 12'(expected_l))
                else $fatal(1, "Divider request %0d: O=%0d L=%0d", div_calls, dut.o0, dut.weight_sum);
            // The divider does not check its inputs: these keep the quotient inside 12 bits.
            assert (expected_l >= 255 && expected_o[div_calls] >= -128 * expected_l &&
                    expected_o[div_calls] <= 127 * expected_l) else $fatal(1, "Divider precondition broken");
            div_start_cycle = cycles; div_calls++;
        end
        if (dut.div_done) begin
            assert (div_results < div_calls && cycles - div_start_cycle == 25 &&
                    dut.result == 12'(expected[div_results]))
                else $fatal(1, "Divider result %0d: RTL %0d, Python %0d", div_results, dut.result, expected[div_results]);
            div_results++;
        end
        if (stalled) assert (out_valid && out_data == held) else $fatal(1, "Output changed while stalled");
        stalled = out_valid && !out_ready;
        held = out_data;
        if (out_valid && out_ready) begin
            assert (received < 8 && div_results == received/2 + 1 && out_data == output_byte(received))
                else $fatal(1, "Output byte %0d: RTL %h, Python %h", received, out_data, output_byte(received));
            received++;
        end
    end

    task automatic reset_core(input int length);
        rst_n = 0; start = 0;
        repeat (length) @(negedge clk);
        assert (dut.idle && cs_n && !sck && !out_valid) else $fatal(1, "Reset did not idle the core and flash");
        rst_n = 1;
    endtask
    task automatic launch;
        @(negedge clk);
        assert (dut.idle) else $fatal(1, "Not idle before start");
        start = 1;
        @(negedge clk);
        start = 0;
        assert (!dut.idle) else $fatal(1, "Start not accepted");
    endtask
    task automatic scan(input int fd, output int value);
        assert ($fscanf(fd, "%d", value) == 1) else $fatal(1, "Truncated vector file");
    endtask

    string path;
    int fd, shift_in, temp, cases, checked = 0, ticks;
    bit reset_point;
    initial begin
        assert ($value$plusargs("VECTORS=%s", path)) else $fatal(1, "Missing vectors");
        assert ($value$plusargs("CASES=%d", cases)) else $fatal(1, "Missing case count");
        fd = $fopen(path, "r");
        assert (fd != 0) else $fatal(1, "Cannot read vectors");
        reset_core(1);  // power-up state is random: one clock of reset must be enough
        // Reset in every phase: mid command, mid data, at a score, during
        // accumulation, during the V read, with an output stalled, and at every
        // divider step. Each reset is followed by 30 quiet clocks.
        last = 1;
        for (int phase = 0; phase < 30; phase++) begin
            foreach (flash.memory[i]) flash.memory[i] = 8'($urandom);
            force_output_stall = phase == 5;
            launch();
            reset_point = 0; ticks = 0;
            while (!reset_point && ticks < 1000000) begin
                @(negedge clk); ticks++;
                case (phase)
                    0: reset_point = !cs_n && flash.bits == 20;
                    1: reset_point = !cs_n && flash.bits == 35;
                    2: reset_point = dut.score_done;
                    3: reset_point = dut.state == dut.ACCUM;
                    4: reset_point = dut.state == dut.READ && dut.kind == dut.V;
                    5: reset_point = out_valid;
                    default: reset_point = dut.divider_unit.state != 0 &&
                        (phase < 29 ? int'(dut.divider_unit.step) == phase - 6 && dut.divider_unit.state == 1
                                    : dut.divider_unit.state == 2);
                endcase
            end
            assert (reset_point) else $fatal(1, "Missing reset point %0d", phase);
            reset_core(phase % 2 + 1);
            repeat (30) begin
                @(negedge clk);
                assert (dut.idle && cs_n && !out_valid) else $fatal(1, "Activity after reset");
            end
        end
        force_output_stall = 0;
        while ($fscanf(fd, "%d", count) == 1) begin
            scan(fd, shift_in); scan(fd, case_chunk);
            @(negedge clk);
            last = 4'(count - 1); score_shift = 4'(shift_in); chunk = 4'(case_chunk);
            // Unused rows, other chunks and the gaps between regions hold noise.
            foreach (flash.memory[i]) begin flash.memory[i] = 8'($urandom); flash.count[i] = 0; end
            for (int i = 0; i < 64; i++) begin scan(fd, temp); flash.memory[i] = 8'(temp); end
            for (int i = 0; i < 64*count; i++) begin scan(fd, temp); flash.memory[K_BASE+i] = 8'(temp); end
            for (int i = 0; i < 64*count; i++) begin scan(fd, temp); flash.memory[V_BASE+i] = 8'(temp); end
            for (int i = 0; i < 4; i++) scan(fd, expected[i]);
            for (int i = 0; i < count; i++) scan(fd, scores[i]);
            for (int i = 0; i < count; i++) scan(fd, weights[i]);
            expected_l = 0; expected_max = scores[0];
            foreach (expected_o[i]) begin expected_o[i] = 0; running_o[i] = 0; end
            for (int i = 0; i < count; i++) begin
                if (scores[i] > expected_max) expected_max = scores[i];
                expected_l += weights[i];
                for (int c = 0; c < 4; c++) expected_o[c] += weights[i]*value_component(i, c);
            end
            captures = 0; accumulated = 0; div_calls = 0; div_results = 0; received = 0;
            running_l = 0; check_sums = 0; cycles = 0; stalled = 0; active_case = 1;
            launch();
            while (!(dut.idle && received == 8)) @(negedge clk);
            start = 0;
            assert (captures == 2*count && accumulated == count && div_calls == 4 && div_results == 4)
                else $fatal(1, "Incomplete case %0d", checked);
            repeat (100) begin
                @(negedge clk);
                assert (dut.idle && cs_n && !out_valid) else $fatal(1, "Activity after the last output");
            end
            for (int i = 0; i < SIZE; i++)
                assert (flash.count[i] == expected_reads(i))
                    else $fatal(1, "Case %0d: address %h read %0d times, expected %0d", checked, i, flash.count[i], expected_reads(i));
            active_case = 0; checked++;
        end
        assert (checked == cases) else $fatal(1, "Missing controller cases");
        $display("PASS: controller with SPI and flash, %0d Python cases; scores, maximum, weights, running sums, divider requests and results, outputs, read counts, resets in 30 phases", checked);
        $finish;
    end
    initial begin #100000000000; $fatal(1, "Testbench timeout"); end
endmodule
