`timescale 1ns/1ps
module tb_controller #(
    parameter logic [15:0] TEST_Q_BASE = 16'h0000,
    parameter logic [15:0] TEST_K_BASE = 16'h0040,
    parameter logic [15:0] TEST_V_BASE = 16'h0440
);
    // Testbench memory slots: Q 0..63, K token t component c at K_SLOT+64t+c,
    // V token t component c at V_SLOT+64t+c. The DUT's bases map onto these.
    localparam int K_SLOT = 64, V_SLOT = 64 + 1024, SLOTS = V_SLOT + 1024;
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, start = 0;
    logic [4:0] token_count = 0;
    logic [3:0] score_shift = 0;
    logic [4:0] chunk = 0;
    wire start_ready, busy, done, mem_req_valid, mem_write, out_valid;
    wire [15:0] mem_addr;
    wire [7:0] mem_wdata;
    wire signed [7:0] out_data;
    logic mem_req_ready = 0, mem_rsp_valid = 0, out_ready = 0;
    logic [7:0] mem_rdata = 0;
    attention_controller #(.Q_BASE(TEST_Q_BASE), .K_BASE(TEST_K_BASE), .V_BASE(TEST_V_BASE)) dut (.*);

    // The testbench supplies only a memory model and host signals. No arithmetic
    // result or completion signal is driven from the testbench into the controller.
    logic [7:0] memory [0:SLOTS-1];
    int reads [0:SLOTS-1];
    int mem_delay = -1, pending_slot = 0, memory_cycles = 0;
    bit force_output_stall = 0, active_case = 0;
    bit request_stalled = 0, output_stalled = 0, check_sums = 0;
    bit score_ready = 0;
    bit div_pending = 0;
    logic [11:0] held_denominator;
    logic [15:0] held_address;
    logic [7:0] held_output;
    int count = 1, case_chunk = 0, expected [0:1], scores [0:15], weights [0:15];
    int expected_max, expected_l, expected_o [0:1];
    int running_l = 0, running_o [0:1];
    int captures = 0, mac_cycles = 0, max_updates = 0, accum_updates = 0;
    int exp_results = 0, div_calls = 0, div_results = 0, received = 0;
    int cycles = 0, total_cycles = 0, divide_start_cycle = 0;

    function automatic int memory_slot(input logic [15:0] address);
        if (int'(address) >= int'(TEST_Q_BASE) && int'(address) < int'(TEST_Q_BASE)+64)
            return int'(address)-int'(TEST_Q_BASE);
        if (int'(address) >= int'(TEST_K_BASE) && int'(address) < int'(TEST_K_BASE)+1024)
            return K_SLOT+int'(address)-int'(TEST_K_BASE);
        if (int'(address) >= int'(TEST_V_BASE) && int'(address) < int'(TEST_V_BASE)+1024)
            return V_SLOT+int'(address)-int'(TEST_V_BASE);
        $fatal(1, "Out-of-map memory address %h", address);
        return 0;
    endfunction
    // Every Q byte is read once per token per pass, K bytes twice, and only
    // the selected 2-byte chunk of each V row once.
    function automatic int expected_reads(input int slot);
        if (slot < K_SLOT) return 2*count;
        if (slot < V_SLOT) return slot-K_SLOT < 64*count ? 2 : 0;
        return (slot-V_SLOT)/64 < count && ((slot-V_SLOT)%64)/2 == case_chunk ? 1 : 0;
    endfunction
    // Output byte i: result i/2 as signed 16 bits, low byte first.
    function automatic logic [7:0] output_byte(input int index);
        logic [15:0] word = 16'(expected[index / 2]);
        return index % 2 != 0 ? word[15:8] : word[7:0];
    endfunction
    function automatic int value_component(input int token, component);
        return int'($signed(memory[V_SLOT+64*token+2*case_chunk+component]));
    endfunction

    always @(negedge clk) begin
        mem_req_ready = rst_n && mem_delay < 0 && (memory_cycles > 0 || $urandom_range(0,3) != 0);
        out_ready = rst_n && !force_output_stall && (memory_cycles > 0 || $urandom_range(0,3) == 0);
    end
    always @(posedge clk) begin
        if (!rst_n) begin
            mem_rsp_valid <= 0; mem_delay = -1;
            request_stalled = 0; output_stalled = 0;
            div_pending = 0;
        end else begin
            assert (!mem_write && mem_wdata == 0) else $fatal(1, "Core attempted a memory write");
            if (request_stalled)
                assert (mem_req_valid && mem_addr == held_address) else $fatal(1, "Unstable memory request");
            request_stalled = mem_req_valid && !mem_req_ready;
            held_address = mem_addr;
            if (output_stalled)
                assert (out_valid && out_data == held_output) else $fatal(1, "Unstable output");
            output_stalled = out_valid && !out_ready;
            held_output = out_data;
            mem_rsp_valid <= 0;
            if (mem_delay == 0) begin
                mem_rdata <= memory[pending_slot];
                reads[pending_slot]++;
                mem_rsp_valid <= 1;
                mem_delay = -1;
            end else if (mem_delay > 0) mem_delay--;
            if (mem_req_valid && mem_req_ready) begin
                assert (mem_delay < 0) else $fatal(1, "Overlapping requests");
                pending_slot = memory_slot(mem_addr);
                if (active_case) begin
                    if (pending_slot < K_SLOT) begin
                        assert (reads[pending_slot] < 2*count) else $fatal(1, "Extra Q access");
                    end else if (pending_slot < V_SLOT) begin
                        assert (pending_slot-K_SLOT < 64*count && reads[pending_slot] < 2)
                            else $fatal(1, "Invalid K access");
                        if (reads[pending_slot] == 0)
                            assert (max_updates == (pending_slot-K_SLOT)/64 && exp_results == 0 && accum_updates == 0)
                                else $fatal(1, "Pass 1 scheduled incorrectly");
                        else assert (max_updates == count && accum_updates == (pending_slot-K_SLOT)/64)
                            else $fatal(1, "Pass 2 scheduled incorrectly");
                    end else
                        assert (expected_reads(pending_slot) == 1 && reads[pending_slot] == 0 &&
                                exp_results == (pending_slot-V_SLOT)/64+1)
                            else $fatal(1, "Wrong V chunk, repeated V read, or V read before the token's weight");
                end
                mem_delay = memory_cycles > 0 ? memory_cycles-2 : int'($urandom_range(0,7));
            end

            if (active_case) begin
                if (busy || (start && start_ready)) cycles++;
                if (max_updates == count)
                    assert (dut.maximum == 22'(expected_max)) else $fatal(1, "Final max changed");
                if (dut.mac.score_en) mac_cycles++;
                // The completed score is consumed one edge after the final MAC. Pass 1
                // yields S; pass 2 starts at M and subtracts, yielding D = M - S, and the
                // combinational LUT weight for that D must already be correct.
                if (score_ready) begin
                    if (captures < count)
                        assert (dut.score == 22'(scores[captures])) else $fatal(1, "Dot-product mismatch");
                    else begin
                        assert (captures < 2*count && max_updates == count &&
                                dut.exp_delta == 22'(expected_max - scores[captures - count]))
                            else $fatal(1, "Pass-2 difference mismatch");
                        assert (dut.exp_weight == 8'(weights[exp_results]))
                            else $fatal(1, "Real LUT result mismatch");
                        exp_results++;
                    end
                    captures++;
                end
                // A score is complete after the last bit of dimension 63.
                score_ready = dut.mac.score_en && dut.bit_index == 7 && dut.dim == 63;
                if (dut.max_unit.en) begin
                    assert (max_updates < count) else $fatal(1, "Max updated in pass 2");
                    max_updates++;
                end
                // The accum ring rotates every clock: register k holds component (phase + k) % 2.
                if (check_sums)
                    assert (dut.div_denominator == 12'(running_l) &&
                            dut.o0 == 20'(running_o[(int'(dut.component) + 0) % 2]) &&
                            dut.o1 == 20'(running_o[(int'(dut.component) + 1) % 2]))
                        else $fatal(1, "Running sums mismatch");
                // Accumulation is serial: one bit of one component per en cycle, L on the first.
                // No clear: sums are only defined once token 0 has loaded every component.
                if (dut.mac.accum_en) begin
                    assert (accum_updates < count && exp_results == accum_updates+1 &&
                            dut.weight == 8'(weights[accum_updates])) else $fatal(1, "Bad accumulate");
                    if (dut.component == 0 && dut.bit_index == 0) running_l += weights[accum_updates];
                    if ((value_component(accum_updates, dut.component) >> dut.bit_index) & 1)
                        running_o[dut.component] += weights[accum_updates] *
                            (dut.bit_index == 7 ? -128 : (1 << dut.bit_index));
                    if (dut.component == 1 && dut.bit_index == 7) begin
                        accum_updates++;
                        check_sums = 1;
                    end
                end
                // div_sum is the rotating ring head; the divider latches it at start.
                if (div_pending)
                    assert (!dut.div_start && dut.div_denominator == held_denominator)
                        else $fatal(1, "Divider denominator changed or start repeated while waiting");
                if (dut.div_start) begin
                    assert (!dut.div_busy && div_calls < 2 && accum_updates == count &&
                            dut.div_sum == 20'(expected_o[div_calls]) &&
                            dut.div_denominator == 12'(expected_l) && expected_l > 0)
                        else $fatal(1, "Bad divider request");
                    divide_start_cycle = cycles;
                    div_calls++;
                    held_denominator = dut.div_denominator; div_pending = 1;
                end
                if (dut.div_done) begin
                    // Result registered 24 edges after start, sampled here on edge 25.
                    assert (div_results < div_calls && cycles-divide_start_cycle == 25 &&
                            dut.div_result == 12'(expected[div_results])) else $fatal(1, "Real divider mismatch");
                    div_results++;
                    div_pending = 0;
                end
                if (out_valid && out_ready) begin
                    assert (received < 4 && div_results == received/2+1 && out_data == output_byte(received))
                        else $fatal(1, "Output %0d mismatch", received);
                    received++;
                end
            end
        end
    end

    task automatic reset_core;
        // Caller is at a falling edge (or time zero); no rising edge can sneak in.
        rst_n = 0; start = 0;
        repeat (2) @(negedge clk);
        assert (!busy && !done && !out_valid && !dut.div_done && !dut.div_busy)
            else $fatal(1, "Reset failed");
        rst_n = 1;
    endtask
    task automatic launch;
        @(negedge clk);
        assert (start_ready) else $fatal(1, "Start not ready");
        start = 1;
        @(negedge clk); start = 0;
        assert (busy && !done) else $fatal(1, "Start did not clear done/set busy");
    endtask
    task automatic scan(input int fd, output int value);
        assert ($fscanf(fd, "%d", value) == 1) else $fatal(1, "Truncated vector file");
    endtask

    string path;
    int fd, shift_in, temp, cases, checked = 0, ticks;
    bit reset_point;
    initial begin
        if ($value$plusargs("MEM_CYCLES=%d", memory_cycles))
            assert (memory_cycles >= 2 && memory_cycles <= 100) else $fatal(1, "Invalid memory latency");
        assert ($value$plusargs("VECTORS=%s", path)) else $fatal(1, "Missing vectors");
        assert ($value$plusargs("CASES=%d", cases)) else $fatal(1, "Missing case count");
        fd = $fopen(path, "r");
        assert (fd != 0) else $fatal(1, "Cannot read vectors");
        reset_core();
        token_count = 0; start = 1;
        repeat (3) @(negedge clk);
        assert (!busy && !start_ready) else $fatal(1, "Accepted N=0");
        token_count = 17;
        repeat (3) @(negedge clk);
        assert (!busy && !start_ready) else $fatal(1, "Accepted N=17");
        start = 0;
        token_count = 1; score_shift = 0; chunk = 0;
        foreach (memory[i]) memory[i] = 0;
        // Include reset with a pass-2 weight live, mid-accumulate, and every divider stage.
        for (int phase = 0; phase < 30; phase++) begin
            foreach (reads[i]) reads[i] = 0;
            force_output_stall = 1;
            launch();
            reset_point = 0; ticks = 0;
            while (!reset_point && ticks < 200000) begin
                @(negedge clk); ticks++;
                case (phase)
                    0: reset_point = mem_delay >= 0;
                    1: reset_point = mem_delay >= 0 && pending_slot == 0 && reads[0] == 1;
                    2: reset_point = dut.mac.score_en && dut.second_pass && dut.bit_index == 7 &&
                                     dut.dim == 63;
                    3: reset_point = dut.mac.accum_en;
                    4: reset_point = mem_delay >= 0 && pending_slot == V_SLOT;
                    5: reset_point = out_valid;
                    default: reset_point = dut.div_busy &&
                        ((phase < 29 && int'(dut.divider_unit.step) == phase-6) ||
                         (phase == 29 && dut.divider_unit.state == dut.divider_unit.ROUND));
                endcase
            end
            assert (reset_point) else $fatal(1, "Missing reset point %0d", phase);
            reset_core();
            repeat (29) begin
                @(negedge clk);
                assert (!done && !out_valid && !dut.div_done && !dut.div_busy)
                    else $fatal(1, "Stale result after reset");
            end
        end
        force_output_stall = 0;
        while ($fscanf(fd, "%d", count) == 1) begin
            scan(fd, shift_in); scan(fd, case_chunk);
            @(negedge clk);
            token_count = 5'(count); score_shift = 4'(shift_in); chunk = 5'(case_chunk);
            foreach (memory[i]) begin memory[i] = 8'ha5; reads[i] = 0; end
            for (int i = 0; i < 64; i++) begin scan(fd, temp); memory[i] = 8'(temp); end
            for (int i = 0; i < 64*count; i++) begin scan(fd, temp); memory[K_SLOT+i] = 8'(temp); end
            for (int i = 0; i < 64*count; i++) begin scan(fd, temp); memory[V_SLOT+i] = 8'(temp); end
            for (int i = 0; i < 2; i++) scan(fd, expected[i]);
            for (int i = 0; i < count; i++) scan(fd, scores[i]);
            for (int i = 0; i < count; i++) scan(fd, weights[i]);
            expected_l = 0; expected_max = -1040384;
            foreach (expected_o[i]) begin expected_o[i] = 0; running_o[i] = 0; end
            for (int i = 0; i < count; i++) begin
                if (scores[i] > expected_max) expected_max = scores[i];
                expected_l += weights[i];
                for (int c = 0; c < 2; c++) expected_o[c] += weights[i]*value_component(i,c);
            end
            captures = 0; mac_cycles = 0; max_updates = 0; accum_updates = 0;
            exp_results = 0; div_calls = 0; div_results = 0; received = 0;
            running_l = 0; check_sums = 0; score_ready = 0; cycles = 0; active_case = 1;
            launch();
            score_shift = ~score_shift; chunk = ~chunk; token_count = 0; start = 1;
            repeat (2) @(negedge clk);
            start = 0; ticks = 0;
            while (!done && ticks < 1000000) begin @(negedge clk); ticks++; end
            assert (done && !busy && received == 4 && captures == 2*count && mac_cycles == 1024*count &&
                    max_updates == count && accum_updates == count && exp_results == count && div_calls == 2 && div_results == 2)
                else $fatal(1, "Incomplete transaction %0d", checked);
            for (int i = 0; i < SLOTS; i++)
                assert (reads[i] == expected_reads(i)) else $fatal(1, "Wrong read count at slot %0d", i);
            repeat (3) @(negedge clk);
            assert (done && !out_valid && !dut.div_done) else $fatal(1, "Status did not settle");
            active_case = 0; total_cycles += cycles; checked++;
        end
        assert (checked == cases) else $fatal(1, "Missing controller cases");
        $display("PASS: integrated RTL controller, %0d Python cases; memory_cycles=%0d Q=%h K=%h V=%h; reset, stalls, intermediate results and outputs", checked, memory_cycles, TEST_Q_BASE, TEST_K_BASE, TEST_V_BASE);
        $display("METRICS total_cycles=%0d", total_cycles);
        $finish;
    end
    // 10 s of simulated time; sized because it exceeds 32 bits (older Verilator rejects it unsized).
    initial begin #(64'd10_000_000_000); $fatal(1, "Core timeout"); end
endmodule
