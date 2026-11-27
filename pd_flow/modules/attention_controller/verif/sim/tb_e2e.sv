`timescale 1ns/1ps
// End-to-end smoke simulation (SPEC.md section 9, non-proof evidence): the DUT at its PORTS
// only, against a 0x6B quad-output flash model holding the tape and a host that reads every
// result frame. Derived from test/controller/tb_controller.sv without its internal probes, so
// it runs on any candidate RTL or netlist. Checks: every result bit (Python chip_attention),
// the flash command and address, IO0 drive window and contention, SCK mode 0, run length in
// SCK rises, idle after the run, and quiet outputs after a mid-run reset.
// -DP_OUTPUTS=P selects OUTPUTS; -DGATE instantiates a netlist without parameter.
module tb_e2e;
    localparam int P = `P_OUTPUTS;
    localparam int MAX_TAPE = 16 * (128 + 64 / P * (128 + P));
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, start = 0, cont = 0, out_ready = 0, out_shift = 0;
    logic [3:0] last = 0, score_shift = 0;
    wire idle, spi_cs_n, spi_sck, spi_mosi, spi_mosi_oe, out_valid, out_bit;
    logic [7:0] tape [0:MAX_TAPE-1];
    int tape_len = 0, bits = 0, errors = 0;
    logic [31:0] command = 0;
    logic prev_sck = 0, prev_cs = 1, prev_mosi = 0, checking = 0;
    wire driving = !spi_cs_n && bits >= 40;
    wire [3:0] spi_io = driving && bits < 40 + 2 * tape_len
        ? (bits % 2 ? tape[(bits - 40) / 2][3:0] : tape[(bits - 40) / 2][7:4]) : 4'h5;
`ifdef GATE
    attention_controller dut (
`else
    attention_controller #(.OUTPUTS(P)) dut (
`endif
        .clk(clk), .rst_n(rst_n), .start(start), .last(last), .score_shift(score_shift), .cont(cont),
        .idle(idle), .spi_cs_n(spi_cs_n), .spi_sck(spi_sck), .spi_mosi(spi_mosi), .spi_mosi_oe(spi_mosi_oe),
        .spi_io(spi_io), .out_valid(out_valid), .out_ready(out_ready), .out_shift(out_shift), .out_bit(out_bit));

    task automatic fail(input string m);
        errors++; $display("ERROR %s (SCK rise %0d)", m, bits);
    endtask
    always @(posedge clk) begin
        prev_sck <= spi_sck; prev_cs <= spi_cs_n; prev_mosi <= spi_mosi;
        if (checking) begin
            if (driving && spi_mosi_oe) fail("IO0 contention");
            if ((spi_cs_n || bits > 32 || (bits == 32 && spi_sck)) && spi_mosi_oe) fail("IO0 driven outside the command");
            if (!spi_cs_n && bits < 32 && !spi_mosi_oe) fail("IO0 released inside the command");
            if (spi_sck && (spi_cs_n || prev_cs)) fail("SCK high with CS# high or falling");
            if (!spi_cs_n && spi_sck && !prev_sck && bits < 32 && spi_mosi !== prev_mosi) fail("IO0 changes at an SCK rise");
        end
        if (spi_cs_n) bits <= 0;
        else if (spi_sck && !prev_sck) begin
            if (bits < 32) command <= {command[30:0], spi_mosi};
            if (bits == 32 && command != 32'h6B00_0000) fail($sformatf("flash command %h", command));
            bits <= bits + 1;
        end
    end

    int exp_r [0:7];
    task automatic do_reset;
        @(negedge clk); rst_n = 0; start = 0; out_ready = 0; out_shift = 0;
        repeat (2) @(negedge clk);
        if (!(idle && spi_cs_n && !spi_sck && !out_valid)) fail("reset state");
        rst_n = 1; checking = 1;
    endtask
    task automatic launch(input bit c);
        @(negedge clk); if (!idle) fail("start while busy");
        cont = c; start = 1; @(negedge clk); start = 0;
        if (idle) fail("start not accepted");
    endtask
    // read P result frames: 16 shifts (12-bit result MSB first, then 4 zeros), then ready
    task automatic read_results;
        for (int i = 0; i < P; i++) begin
            int t = 0;
            while (!out_valid && t < 200000) begin @(negedge clk); t++; end
            if (!out_valid) begin fail("no result"); return; end
            for (int b = 0; b < 16; b++) begin
                logic [15:0] fr = 16'(exp_r[i]) << 4;
                if (out_bit !== fr[15 - b]) fail($sformatf("result %0d bit %0d: got %b want %b", i, b, out_bit, fr[15 - b]));
                out_shift = 1; @(negedge clk); out_shift = 0;
                if (b % 3 == 0) @(negedge clk);   // uneven host pace
            end
            out_ready = 1; @(negedge clk); out_ready = 0;
        end
    endtask

    string path; int fd, n, sh, nch, rst_at, tmp, cases = 0, runs = 0;
    initial begin
        if (!$value$plusargs("VECTORS=%s", path)) $fatal(1, "no +VECTORS");
        fd = $fopen(path, "r");
        do_reset();
        while ($fscanf(fd, "%d %d %d %d %d", n, sh, nch, rst_at, tape_len) == 5) begin
            for (int i = 0; i < tape_len; i++) begin tmp = $fscanf(fd, "%d", tape[i]); end
            last = 4'(n - 1); score_shift = 4'(sh);
            if (rst_at > 0) begin   // mid-run abort, then quiet outputs
                launch(0);
                while (bits < rst_at) @(negedge clk);
                do_reset();
                repeat (40) begin @(negedge clk); if (!(idle && spi_cs_n && !out_valid && !spi_sck)) fail("activity after reset"); end
            end
            for (int r = 0; r < nch; r++) begin
                for (int i = 0; i < P; i++) tmp = $fscanf(fd, "%d", exp_r[i]);
                launch(r != 0);
                read_results();
                @(negedge clk);
                if (!idle) fail("not idle after the last result");
                if (bits != 40 + 2 * n * (128 * (2 + r) + P * (1 + r))) fail($sformatf("run length %0d SCK rises", bits));
                runs++;
            end
            if (bits != 40 + 2 * tape_len) fail("tape not fully read");
            cases++;
        end
        $display("RESULT sim outputs=%0d cases=%0d runs=%0d errors=%0d", P, cases, runs, errors);
        $finish;
    end
    initial begin #(64'd200_000_000); $display("RESULT sim timeout errors=1"); $finish; end
endmodule
