`timescale 1ns/1ps
// The real controller and arithmetic blocks against a sequential-read flash
// model. The testbench supplies only the tape and the host handshake; it probes
// the scores, pass-2 differences, weights, sums and divider inputs on the way.
module tb_controller;
    localparam int MAX_TAPE = 16 * (128 + 32 * 130);
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, start = 0, cont = 0, out_ready = 0;
    logic [4:0] token_count = 1;
    logic [3:0] score_shift = 0;
    wire idle, spi_cs_n, spi_sck, spi_mosi, out_valid;
    wire [7:0] out_data;

    // Flash: 0x03 and a 24-bit address, then bytes in order, MSB first, until CS
    // rises. Bit n is on MISO before SCK rising edge n; anything else is junk.
    logic [7:0] tape [0:MAX_TAPE-1];
    int tape_len = 0, bits = 0;
    logic [31:0] command = 0;
    logic prev_sck = 0, junk = 0;
    wire data_phase = !spi_cs_n && bits >= 32 && bits < 32 + 8 * tape_len;
    wire spi_miso = data_phase ? tape[(bits - 32) / 8][7 - (bits - 32) % 8] : junk;
    attention_controller dut (.*);

    bit active = 0, force_stall = 0, stalled = 0;
    logic [7:0] held_output;
    int count = 1, scores [0:15], weights [0:15], expected_max, expected_l;
    int expected_o [0:1], expected [0:1];
    int pass1 = 0, pass2 = 0, max_updates = 0, div_calls = 0, received = 0;
    int cycles = 0, total_cycles = 0;

    // Output byte i: result i/2 as signed 16 bits, low byte first.
    function automatic logic [7:0] output_byte(input int index);
        logic [15:0] word = 16'(expected[index / 2]);
        return index % 2 != 0 ? word[15:8] : word[7:0];
    endfunction

    always @(negedge clk) out_ready = rst_n && !force_stall && $urandom_range(0, 3) == 0;
    always @(posedge clk) begin
        junk <= 1'($urandom);
        prev_sck <= spi_sck;
        if (spi_cs_n) bits <= 0;
        else if (spi_sck && !prev_sck) begin
            if (bits < 32) command <= {command[30:0], spi_mosi};
            if (bits == 32) assert (command == 32'h0300_0000) else $fatal(1, "Flash command %h", command);
            bits <= bits + 1;
        end
        if (stalled) assert (out_valid && out_data == held_output) else $fatal(1, "Unstable output");
        stalled <= rst_n && out_valid && !out_ready;
        held_output <= out_data;
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
                assert (div_calls < 2 && pass2 == count && dut.o0 == 20'(expected_o[div_calls]) &&
                        dut.weight_sum == 12'(expected_l))
                    else $fatal(1, "Divider request %0d mismatch", div_calls);
                div_calls++;
            end
            if (out_valid && out_ready) begin
                assert (received < 4 && div_calls == received / 2 + 1 && out_data == output_byte(received))
                    else $fatal(1, "Output byte %0d mismatch", received);
                received++;
            end
        end
    end

    task automatic reset_core;
        rst_n = 0; start = 0;
        repeat (2) @(negedge clk);
        assert (idle && spi_cs_n && !spi_sck && !out_valid) else $fatal(1, "Reset failed");
        rst_n = 1;
    endtask
    task automatic launch(input bit continue_run);
        @(negedge clk);
        assert (idle) else $fatal(1, "Start while busy");
        cont = continue_run; start = 1;
        @(negedge clk); start = 0;
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
            token_count = 5'(count); score_shift = 4'(shift_in);

            // Before the first case: reset in every phase of a run, then expect a clean restart.
            if (checked == 0) begin
                force_stall = 1;
                for (int phase = 0; phase < 9; phase++) begin
                    launch(0);
                    hit = 0; ticks = 0;
                    while (!hit && ticks < 100000) begin
                        @(negedge clk); ticks++;
                        case (phase)
                            0: hit = 1;                                  // CS still high
                            1: hit = !spi_cs_n && bits == 7;             // inside the command
                            2: hit = bits == 40;                         // first Q byte
                            3: hit = dut.state == dut.SCORE && dut.second_pass && dut.pos == 500;
                            4: hit = dut.state == dut.VALUE && dut.pos == 9;
                            5: hit = dut.div_busy && dut.divider_unit.step == 3;
                            6: hit = dut.div_busy && dut.divider_unit.step == 20;
                            7: hit = out_valid && dut.output_index == 0;
                            default: hit = out_valid && dut.output_index == 1;
                        endcase
                        if (phase == 8 && out_valid && dut.output_index == 0) begin
                            force_stall = 0; @(negedge clk); force_stall = 1; // let component 0 through
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
                for (int i = 0; i < 2; i++) scan(fd, expected_o[i]);
                for (int i = 0; i < 2; i++) scan(fd, expected[i]);
                pass2 = 0; div_calls = 0; received = 0; active = 1;
                launch(run != 0);
                ticks = 0;
                while (!idle && ticks < 200000) begin @(negedge clk); ticks++; end
                // A fresh run reads pass 1 and one pass-2 block; a continue run one more block.
                assert (idle && received == 4 && pass2 == count && div_calls == 2 &&
                        pass1 == count && max_updates == count && !spi_cs_n && !spi_sck &&
                        bits == 32 + 8 * count * (128 * (2 + run) + 2 * (1 + run)))
                    else $fatal(1, "Incomplete run %0d of case %0d", run, checked);
                active = 0;
                repeat ($urandom_range(0, 3)) @(negedge clk);
            end
            assert (bits == 32 + 8 * tape_len) else $fatal(1, "Tape not fully read");
            total_cycles += cycles; checked++;
        end
        assert (checked == cases) else $fatal(1, "Missing controller cases");
        $display("PASS: integrated RTL controller, %0d Python cases; reset in every phase, output stalls, continue runs, intermediate results and outputs", checked);
        $display("METRICS total_cycles=%0d", total_cycles);
        $finish;
    end
    // 10 s of simulated time; sized because it exceeds 32 bits (older Verilator rejects it unsized).
    initial begin #(64'd10_000_000_000); $fatal(1, "Core timeout"); end
endmodule
