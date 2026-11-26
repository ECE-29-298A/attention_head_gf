// refcheck item: the formal reference formal/ref_divider_seq.v against the Python golden
// model (model/golden_model.py) on every edge-case and spot-check point of edges.txt.
// For each point: load S, L, run 23 steps (bits 22..0), compare `value` with the model's
// 1/1 result (0 for an invalid request) and, where the 0/0 value is defined, with it too.
// 4-state compare (!==). Exit status 0 only with every point checked and no mismatch.
`timescale 1ns/1ps
`default_nettype none
module tb_ref;
    reg clk = 1'b0, load = 1'b0, step = 1'b0;
    reg [4:0] bitpos = 5'd0;
    reg signed [19:0] S_in = 20'sd0;
    reg [11:0] L_in = 12'd0;
    wire signed [19:0] S;
    wire [11:0] L, value;
    wire [23:0] rs, qs, Z;
    wire valid, tie;
    ref_divider_seq r (.clk(clk), .load(load), .step(step), .bitpos(bitpos), .S_in(S_in),
                       .L_in(L_in), .S(S), .L(L), .rs(rs), .qs(qs), .Z(Z), .valid(valid),
                       .value(value), .tie(tie));
    integer fd, rc, s, l, e1, e0, n = 0, bad = 0, n0 = 0, c;
    reg [8*16-1:0] e0s, cls;
    reg [8*256-1:0] fname;
    task tick; begin #5 clk = 1'b1; #5 clk = 1'b0; end endtask
    initial begin
        if (!$value$plusargs("EDGES=%s", fname)) begin
            $display("RESULT refcheck points=0 mismatches=1 (missing +EDGES)"); $finish_and_return(1);
        end
        fd = $fopen(fname, "r");
        if (fd == 0) begin $display("RESULT refcheck points=0 mismatches=1 (cannot open)"); $finish_and_return(1); end
        while (!$feof(fd)) begin
            rc = $fscanf(fd, "%d %d %s %d %s\n", s, l, e0s, e1, cls);
            if (rc == 5) begin
                S_in = s; L_in = l; load = 1'b1; step = 1'b0;
                tick;
                load = 1'b0; step = 1'b1;
                for (c = 1; c <= 23; c = c + 1) begin bitpos = 5'd23 - c; tick; end
                step = 1'b0;
                #1;
                n = n + 1;
                if (value !== e1[11:0]) begin
                    bad = bad + 1;
                    if (bad <= 10) $display("MISMATCH S=%0d L=%0d ref=%0d model_11=%0d", s, l, $signed(value), e1);
                end
                if (e0s != "x") begin
                    rc = $sscanf(e0s, "%d", e0);
                    n0 = n0 + 1;
                    if (!valid || value !== e0[11:0]) begin
                        bad = bad + 1;
                        if (bad <= 10) $display("MISMATCH0 S=%0d L=%0d ref=%0d model_00=%0d", s, l, $signed(value), e0);
                    end
                end else if (valid) begin
                    bad = bad + 1;
                    if (bad <= 10) $display("MISMATCH valid S=%0d L=%0d: reference valid, model outside the domain", s, l);
                end
            end
        end
        $display("RESULT refcheck points=%0d domain_points=%0d mismatches=%0d", n, n0, bad);
        if (bad != 0 || n == 0) $finish_and_return(1);
        $finish;
    end
endmodule
`default_nettype wire
