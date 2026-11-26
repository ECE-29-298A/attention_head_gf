`timescale 1ns/1ps
// The real controller and arithmetic blocks against a 0x6B quad-output flash
// model. The testbench supplies only the tape and the host side of the SPI target
// (as the top's synchronized pulses); it probes the scores, pass-2 differences,
// weights, sums and divider inputs on the way.
module tb_controller #(parameter int OUTPUTS = 8);
    localparam int MAX_TAPE = 16 * (128 + 64 / OUTPUTS * (128 + OUTPUTS));
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, start_request = 0, cont = 0, out_ready = 0, out_shift = 0;
    logic [3:0] last = 0;
    logic [3:0] score_shift = 0;
    wire idle, spi_cs_n, spi_sck, spi_mosi, spi_mosi_oe, out_valid, out_bit;
    // As in the top, one CS# rise is both start and out_ready.
    wire start = start_request || out_ready;

    // Flash, Fast Read Quad Output: 0x6B and a 24-bit address on IO0, 8 dummy
    // clocks, then nibbles in order (high nibble first, IO3 = MSB) until CS rises.
    // `bits` counts SCK rises; it increments at the clk edge that ends the SCK-high
    // cycle, i.e. at the SCK fall, which is when the flash changes its outputs.
    // Nibble n is driven after fall 40 + n; anything else on the lines is junk.
    logic [7:0] tape [0:MAX_TAPE-1];
    int tape_len = 0, bits = 0;
    logic [31:0] command = 0;
    logic prev_sck = 0, reset_seen = 0, prev_mosi = 0, prev_cs = 1;
    logic [3:0] junk = 0;
    wire driving = !spi_cs_n && bits >= 40; // the flash drives IO3..IO0
    wire [3:0] spi_io = driving && bits < 40 + 2 * tape_len
        ? (bits % 2 ? tape[(bits - 40) / 2][3:0] : tape[(bits - 40) / 2][7:4]) : junk;
    attention_controller #(.OUTPUTS(OUTPUTS)) dut (.*);

    bit active = 0, force_stall = 0, stalled = 0;
    logic held_bit;
    int frame_bits = 0;
    logic [15:0] frame;
    int count = 1, scores [0:15], weights [0:15], expected_max, expected_l;
    int expected_o [0:OUTPUTS-1], expected [0:OUTPUTS-1];
    int pass1 = 0, pass2 = 0, max_updates = 0, div_calls = 0, received = 0;
    int cycles = 0, total_cycles = 0;

    // Host: while out_valid, read a 16-bit frame (16 shifts, then out_ready) at a
    // random pace and check each bit: the 12-bit result MSB first, then 4 zeros.
    // Otherwise send random shifts and, while busy, CS# rises (a config write
    // while busy, or a stray SCK); the controller must ignore them.
    always @(negedge clk) begin
        out_ready = 0; out_shift = 0;
        if (rst_n && !force_stall) begin
            if (!out_valid) begin
                out_shift = $urandom_range(0, 7) == 0;
                out_ready = !idle && $urandom_range(0, 15) == 0;
            end else if ($urandom_range(0, 3) == 0) begin
                if (frame_bits < 16) begin
                    frame = 16'(expected[received]) << 4;
                    assert (!active || out_bit == frame[15 - frame_bits])
                        else $fatal(1, "Output %0d bit %0d mismatch", received, frame_bits);
                    out_shift = 1; frame_bits++;
                end else begin
                    out_ready = 1; frame_bits = 0;
                end
            end
        end
    end
    always @(posedge clk) begin
        junk <= 4'($urandom);
        prev_sck <= spi_sck;
        prev_mosi <= spi_mosi;
        prev_cs <= spi_cs_n;
        // IO0: the chip drives it while it sends the command and address and releases
        // it by the first dummy clock, long before the flash drives it (also through
        // resets, restarts and continue runs; outputs are checked once reset is seen).
        if (reset_seen) begin
            assert (!(driving && spi_mosi_oe)) else $fatal(1, "IO0 contention at SCK rise %0d", bits);
            if (spi_cs_n || bits > 32 || (bits == 32 && spi_sck))
                assert (!spi_mosi_oe) else $fatal(1, "IO0 driven at SCK rise %0d, CS# %0d", bits, spi_cs_n);
            if (!spi_cs_n && bits < 32)
                assert (spi_mosi_oe) else $fatal(1, "IO0 released in the command, SCK rise %0d", bits);
        end
        if (reset_seen) begin
            // Mode 0: SCK is low whenever CS# is high and when CS# falls.
            assert (!(spi_sck && (spi_cs_n || prev_cs))) else $fatal(1, "SCK high with CS# high or falling");
            // IO0 is set up before each command rise and held through the SCK-high cycle.
            if (!spi_cs_n && spi_sck && !prev_sck && bits < 32)
                assert (spi_mosi == prev_mosi) else $fatal(1, "IO0 changes at SCK rise %0d", bits);
        end
        if (!rst_n) reset_seen <= 1;
        if (spi_cs_n) bits <= 0;
        else if (spi_sck && !prev_sck) begin
            if (bits < 32) command <= {command[30:0], spi_mosi};
            if (bits == 32) assert (command == 32'h6B00_0000) else $fatal(1, "Flash command %h", command);
            bits <= bits + 1;
        end
        if (stalled) assert (out_valid && out_bit == held_bit) else $fatal(1, "Unstable output");
        stalled <= rst_n && out_valid && !out_ready && !out_shift;
        held_bit <= out_bit;
        if (active && rst_n) begin
            if (!idle) cycles++;
            // The finished score is visible in the score_done cycle. Pass 1 yields S;
            // pass 2 starts at M and subtracts, so it yields D = M - S and the weight.
            if (dut.score_done) begin
                if (!dut.second_pass) begin
                    assert (pass1 < count && dut.score == 22'(scores[pass1]) && dut.max_unit.en)
                        else $fatal(1, "Pass-1 score %0d mismatch", pass1);
                    pass1++;
                end else begin
                    assert (pass2 < count && dut.maximum == 22'(expected_max) &&
                            dut.score == 22'(expected_max - scores[pass2]) &&
                            dut.weight == 8'(weights[pass2]))
                        else $fatal(1, "Pass-2 difference or weight %0d mismatch", pass2);
                    pass2++;
                end
            end
            if (dut.max_unit.en) max_updates++;
            if (dut.divider_unit.start) begin
                assert (div_calls < OUTPUTS && pass2 == count && dut.o0 == 20'(expected_o[div_calls]) &&
                        dut.weight_sum == 12'(expected_l))
                    else $fatal(1, "Divider request %0d mismatch", div_calls);
                div_calls++;
            end
            if (out_valid && out_ready) begin
                assert (received < OUTPUTS && div_calls == received + 1)
                    else $fatal(1, "Output %0d out of order", received);
                received++;
            end
        end
    end

    task automatic reset_core;
        rst_n = 0; start_request = 0; frame_bits = 0;
        repeat (2) @(negedge clk);
        assert (idle && spi_cs_n && !spi_sck && !out_valid) else $fatal(1, "Reset failed");
        rst_n = 1;
    endtask
    task automatic launch(input bit continue_run);
        @(negedge clk);
        assert (idle) else $fatal(1, "Start while busy");
        cont = continue_run; start_request = 1;
        @(negedge clk); start_request = 0;
        assert (!idle) else $fatal(1, "Start not accepted");
    endtask
    task automatic scan(input int fd, output int value);
        assert ($fscanf(fd, "%d", value) == 1) else $fatal(1, "Truncated vector file");
    endtask

    string path;
    int fd, shift_in, chunks, temp, cases, checked = 0, ticks;
    bit hit;
    initial begin
        assert ($value$plusargs("VECTORS=%s", path)) else $fatal(1, "Missing vectors");
        assert ($value$plusargs("CASES=%d", cases)) else $fatal(1, "Missing case count");
        fd = $fopen(path, "r");
        assert (fd != 0) else $fatal(1, "Cannot read vectors");
        reset_core();
        while ($fscanf(fd, "%d", count) == 1) begin
            scan(fd, shift_in); scan(fd, chunks); scan(fd, tape_len);
            for (int i = 0; i < tape_len; i++) begin scan(fd, temp); tape[i] = 8'(temp); end
            expected_max = -1040384;
            for (int i = 0; i < count; i++) begin
                scan(fd, scores[i]);
                if (scores[i] > expected_max) expected_max = scores[i];
            end
            expected_l = 0;
            for (int i = 0; i < count; i++) begin scan(fd, weights[i]); expected_l += weights[i]; end
            @(negedge clk);
            last = 4'(count - 1); score_shift = 4'(shift_in);

            // Before the first case: reset in every phase of a run, then expect a clean restart.
            if (checked == 0) begin
                force_stall = 1;
                for (int phase = 0; phase < 10; phase++) begin
                    launch(0);
                    hit = 0; ticks = 0;
                    while (!hit && ticks < 100000) begin
                        @(negedge clk); ticks++;
                        case (phase)
                            0: hit = 1;                                  // CS still high
                            1: hit = !spi_cs_n && bits == 7;             // inside the command
                            2: hit = bits == 41;                         // first data nibble
                            3: hit = dut.state == dut.SCORE && dut.second_pass && dut.pos == 500;
                            4: hit = dut.state == dut.VALUE && dut.pos == 9;
                            5: hit = dut.div_busy && dut.divider_unit.step == 3;
                            6: hit = dut.div_busy && dut.divider_unit.step == 20;
                            7: hit = out_valid && dut.output_index == 0;
                            8: hit = out_valid && int'(dut.output_index) == OUTPUTS - 1;
                            default: hit = !spi_cs_n && bits == 36;      // dummy clocks
                        endcase
                        if (phase == 8 && out_valid && int'(dut.output_index) != OUTPUTS - 1) begin
                            force_stall = 0; @(negedge clk); force_stall = 1; // let earlier components through
                        end
                    end
                    assert (hit) else $fatal(1, "Missing reset point %0d", phase);
                    reset_core();
                    repeat (30) begin
                        @(negedge clk);
                        assert (idle && spi_cs_n && !out_valid) else $fatal(1, "Activity after reset");
                    end
                end
                force_stall = 0;
            end

            pass1 = 0; max_updates = 0; cycles = 0;
            for (int run = 0; run < chunks; run++) begin
                for (int i = 0; i < OUTPUTS; i++) scan(fd, expected_o[i]);
                for (int i = 0; i < OUTPUTS; i++) scan(fd, expected[i]);
                pass2 = 0; div_calls = 0; received = 0; active = 1;
                launch(run != 0);
                ticks = 0;
                while (!idle && ticks < 200000) begin @(negedge clk); ticks++; end
                // A fresh run reads pass 1 and one pass-2 block; a continue run one more block.
                assert (idle && received == OUTPUTS && pass2 == count && div_calls == OUTPUTS &&
                        pass1 == count && max_updates == count && !spi_cs_n && !spi_sck &&
                        bits == 40 + 2 * count * (128 * (2 + run) + OUTPUTS * (1 + run)))
                    else $fatal(1, "Incomplete run %0d of case %0d", run, checked);
                active = 0;
                repeat ($urandom_range(0, 3)) @(negedge clk);
            end
            assert (bits == 40 + 2 * tape_len) else $fatal(1, "Tape not fully read");
            total_cycles += cycles; checked++;
        end
        assert (checked == cases) else $fatal(1, "Missing controller cases");
        $display("PASS: integrated RTL controller, OUTPUTS=%0d, %0d Python cases; reset in every phase, serial output reads at random pace, ignored shifts and CS# rises while busy, continue runs, intermediate results and outputs", OUTPUTS, checked);
        $display("METRICS total_cycles=%0d", total_cycles);
        $finish;
    end
    // 10 s of simulated time; sized because it exceeds 32 bits (older Verilator rejects it unsized).
    initial begin #(64'd10_000_000_000); $fatal(1, "Core timeout"); end
endmodule
