`timescale 1ns/1ps
// Pin-level check of the Tiny Tapeout top against docs/pin-protocol.md and the
// Python model. Only the pins are used: no signal inside the chip is read.
// Every input the protocol leaves free is driven with random data.
module tb_top;
    localparam int K_BASE = 'h400, V_BASE = 'h800, SIZE = 'hC00;
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, ena = 1, host = 0;
    logic [7:0] ui_in = 0, junk = 0;
    wire [7:0] uo_out, uio_out, uio_oe;
    wire miso;
    // uio[6] is the host handshake and uio[1] is MISO. The rest is noise.
    wire [7:0] uio_in = {junk[7], host, junk[5:2], miso, junk[0]};
    wire active = rst_n && ena;
    tt_um_attention_head_gf dut (.*);
    spi_flash_model #(.SIZE(SIZE)) flash (
        .clk, .abort_ok(!active), .cs_n(uio_out[5]), .sck(uio_out[4]),
        .mosi(uio_out[0]), .mosi_oe(uio_oe[0]), .miso
    );

    int count, shift, chunk, expected [0:3];
    int received = 0, ready_odds = 1;
    bit outputs = 0;   // between the config byte and the eighth result byte
    bit stalled = 0, was_reset = 0;
    logic [7:0] held;

    function automatic logic [7:0] result_byte(input int index);
        logic [15:0] word = 16'(expected[index / 2]);
        return index % 2 != 0 ? word[15:8] : word[7:0];
    endfunction

    always @(posedge clk) begin
        assert (uio_oe[7:1] == 7'b1011000 && !uio_out[6] && uio_out[3:1] == 0)
            else $fatal(1, "Pin directions or unused outputs changed: oe=%b out=%b", uio_oe, uio_out);
        if (was_reset)
            assert (uio_out[5] && !uio_out[4])
                else $fatal(1, "One clock of reset/ena low did not release the flash");
        was_reset = !active;
        if (!active) stalled = 0;
        else if (outputs) begin
            if (stalled)
                assert (uio_out[7] && uo_out == held) else $fatal(1, "Result byte changed while stalled");
            stalled = uio_out[7] && !host;
            held = uo_out;
            if (uio_out[7] && host) begin
                assert (uo_out == result_byte(received))
                    else $fatal(1, "N=%0d shift=%0d chunk=%0d byte %0d: got %h, Python %h",
                                count, shift, chunk, received, uo_out, result_byte(received));
                received++;
                if (received == 8) outputs = 0;
            end
        end
    end

    // One clock. While results are expected the host is ready at random.
    task automatic tick;
        @(negedge clk);
        junk = 8'($urandom); ui_in = 8'($urandom);
        host = outputs && $urandom_range(1, ready_odds) == 1;
    endtask
    // Present a config byte until the chip is ready on a rising edge.
    task automatic send(input logic [7:0] value);
        repeat ($urandom_range(0, 2)) tick();
        for (int waited = 0; ; waited++) begin
            tick(); ui_in = value; host = 1; #1;
            if (uio_out[7]) break;
            assert (waited < 16) else $fatal(1, "Config byte %h never accepted", value);
        end
    endtask
    // N, optionally after invalid counts that must be refused, then {chunk, shift}.
    task automatic configure;
        logic [7:0] bad;
        repeat ($urandom_range(0, 3)) begin
            bad = 8'($urandom_range(17, 256));  // 256 wraps to 0
            repeat ($urandom_range(1, 3)) begin
                tick(); ui_in = bad; host = 1; #1;
                assert (!uio_out[7]) else $fatal(1, "Invalid N=%0d accepted", bad);
            end
        end
        send(8'(count));
        send({4'(chunk), 4'(shift)});
        tick();
        outputs = 1; received = 0;
        case ($urandom_range(0, 3))
            0: ready_odds = 1;    // always ready, even before the first result
            1: ready_odds = 2;
            2: ready_odds = 16;
            3: ready_odds = 200;  // long stalls
        endcase
    endtask
    task automatic abort;
        if ($urandom_range(0, 1) == 0) rst_n = 0; else ena = 0;
        repeat ($urandom_range(1, 3)) tick();   // the protocol asks for one clock edge
        rst_n = 1; ena = 1; outputs = 0; host = 0;  // host valid must be low when the chip restarts
        tick();  // a read that finished on the reset edge is counted here
        foreach (flash.count[i]) flash.count[i] = 0;
    endtask
    // Run to completion, or abort after `limit` clocks or once `bytes` results arrived.
    task automatic run(input int limit, input int bytes, output bit completed);
        configure();
        for (int cycles = 0; outputs; cycles++) begin
            if (cycles == limit || received == bytes) begin abort(); completed = 0; return; end
            assert (cycles < 3000000) else $fatal(1, "N=%0d: no result", count);
            tick();
        end
        completed = 1;
        // Every Q and K byte twice per token, the selected V chunk once, nothing else.
        for (int i = 0; i < SIZE; i++) begin
            int want = i < K_BASE ? (i < 64 ? 2 * count : 0)
                     : i < V_BASE ? ((i - K_BASE) / 64 < count ? 2 : 0)
                     : ((i - V_BASE) / 64 < count && ((i - V_BASE) % 64) / 4 == chunk ? 1 : 0);
            assert (flash.count[i] == want)
                else $fatal(1, "N=%0d chunk=%0d: address %h read %0d times, expected %0d", count, chunk, i, flash.count[i], want);
            flash.count[i] = 0;
        end
    endtask

    task automatic scan(input int fd, output int value);
        assert ($fscanf(fd, "%d", value) == 1) else $fatal(1, "Truncated vector file");
    endtask
    string path;
    int fd, temp, cases, checked = 0, aborted = 0;
    bit completed;
    initial begin
        assert ($value$plusargs("VECTORS=%s", path)) else $fatal(1, "Missing vectors");
        assert ($value$plusargs("CASES=%d", cases)) else $fatal(1, "Missing case count");
        fd = $fopen(path, "r");
        assert (fd != 0) else $fatal(1, "Cannot read vectors");
        foreach (flash.count[i]) flash.count[i] = 0;
        tick();  // power-up state is random: one clock edge of reset must be enough
        rst_n = 1;
        while ($fscanf(fd, "%d", count) == 1) begin
            scan(fd, shift); scan(fd, chunk);
            // Rows past N, unselected chunks and everything else hold noise.
            foreach (flash.memory[i]) flash.memory[i] = 8'($urandom);
            for (int i = 0; i < 64; i++) begin scan(fd, temp); flash.memory[i] = 8'(temp); end
            for (int i = 0; i < 64*count; i++) begin scan(fd, temp); flash.memory[K_BASE+i] = 8'(temp); end
            for (int i = 0; i < 64*count; i++) begin scan(fd, temp); flash.memory[V_BASE+i] = 8'(temp); end
            for (int i = 0; i < 4; i++) scan(fd, expected[i]);
            repeat (2*count) scan(fd, temp);  // scores and weights: internal, not visible on pins
            // Abort attempts first: between the two config bytes, at a random
            // clock, and (first case) with 0..7 result bytes already taken.
            if (checked % 4 == 0) begin
                send(8'(count)); abort(); aborted++;
            end
            if (checked == 0)
                for (int bytes = 0; bytes < 8; bytes++) begin
                    run(-1, bytes, completed); aborted++;
                    assert (!completed) else $fatal(1, "Abort point missed");
                end
            repeat (checked % 2 + 1) begin
                run($urandom_range(0, 25000 * count), -1, completed);
                if (!completed) aborted++;
            end
            if (!completed) run(-1, -1, completed);
            checked++;
        end
        assert (checked == cases) else $fatal(1, "Missing cases");
        repeat (200) begin
            tick();
            assert (uio_out[5]) else $fatal(1, "Flash access after the last result");
        end
        $display("PASS: top pins, %0d Python cases and %0d aborted runs; flash protocol, read counts, invalid N, backpressure, noise on free inputs", checked, aborted);
        $finish;
    end
    initial begin #100000000000; $fatal(1, "Top timeout"); end
endmodule
