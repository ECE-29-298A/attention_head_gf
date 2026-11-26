// edge_<P> item: directed edge cases plus fixed-seed spot checks (user decision D9b), Icarus
// 4-state. Not exhaustive. Cycles come from edges.txt (model/golden_model.py edges): one line
// per clock, "inputs... kS S kL L kO O0 class" (hex). The expected values are the outputs
// BEFORE that clock's edge (the state after all earlier edges); k* = 0 marks a value that
// is still a power-up value (not compared). Every known output is compared with !== (X or Z
// fails), so this also checks that the flush the model applies leaves no X behind.
// -DP_OUTPUTS=2|4|8 -DP_SELW=1|2|3 select the configuration; -DGATE instantiates a netlist.
// Gate mode runs under Verilator (2-state, random power-up state, two seeds) on the Yosys
// view, because Icarus 4-state X-pessimism in the mapped netlist keeps L[11:8] X after the
// first-token load (an xor2 with an X input masked elsewhere), although the value is
// determined (fv_spec_<P> proves the netlist from every 2-state start state). SPEC 7.
`timescale 1ns/1ps
`default_nettype none
module tb_edge;
    localparam P = `P_OUTPUTS;
    reg clk = 1'b0;
    reg am, load, sub, se, first, ae;
    reg [21:0] M;
    reg [7:0] qi, ki, W, v;
    reg [`P_SELW-1:0] sel;
    reg [2:0] bs;
    wire [21:0] S;
    wire [11:0] L;
    wire [19:0] O0;
`ifdef GATE
    mac_unit dut (
`else
    mac_unit #(.OUTPUTS(P)) dut (
`endif
        .clk(clk), .accum_mode(am), .load(load), .subtract(sub), .M(M), .score_en(se),
        .qi(qi), .ki(ki), .first(first), .accum_en(ae), .W(W), .sel(sel), .v(v), .bit_sel(bs),
        .S(S), .L(L), .O0(O0));

    integer fd, r, cycles = 0, checks = 0, errs = 0, unknown = 0;
    reg [31:0] f_am, f_load, f_sub, f_M, f_se, f_qi, f_ki, f_first, f_ae, f_W, f_sel, f_v, f_bs;
    reg [31:0] kS, eS, kL, eL, kO, eO;
    reg [8*16-1:0] cls;
    reg [8*256-1:0] path;
    initial begin
        if (!$value$plusargs("EDGES=%s", path)) path = "edges.txt";
        fd = $fopen(path, "r");
        if (fd == 0) begin $display("RESULT sim=icarus error=cannot-open"); $fatal(1); end
        while (!$feof(fd)) begin
            r = $fscanf(fd, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %s\n",
                        f_am, f_load, f_sub, f_M, f_se, f_qi, f_ki, f_first, f_ae, f_W, f_sel, f_v, f_bs,
                        kS, eS, kL, eL, kO, eO, cls);
            if (r == 20) begin
                am = f_am[0]; load = f_load[0]; sub = f_sub[0]; M = f_M[21:0]; se = f_se[0];
                qi = f_qi[7:0]; ki = f_ki[7:0]; first = f_first[0]; ae = f_ae[0]; W = f_W[7:0];
                sel = f_sel[`P_SELW-1:0]; v = f_v[7:0]; bs = f_bs[2:0];
                #4;
                cycles = cycles + 1;
                if (kS[0] && kL[0] && kO[0]) checks = checks + 1; else unknown = unknown + 1;
                if ((kS[0] && S !== eS[21:0]) || (kL[0] && L !== eL[11:0]) || (kO[0] && O0 !== eO[19:0])) begin
                    errs = errs + 1;
                    if (errs <= 10)
                        $display("MISMATCH cycle=%0d class=%0s S=%h(exp %h,%0d) L=%h(exp %h,%0d) O0=%h(exp %h,%0d)",
                                 cycles, cls, S, eS[21:0], kS[0], L, eL[11:0], kL[0], O0, eO[19:0], kO[0]);
                end
                #1 clk = 1'b1;
                #5 clk = 1'b0;
            end else if (r > 0) begin
                errs = errs + 1;
                $display("MALFORMED line after cycle %0d (fields=%0d)", cycles, r);
            end
        end
        $fclose(fd);
`ifdef VERILATOR
        $display("RESULT sim=verilator outputs=%0d cycles=%0d checked=%0d partial=%0d errors=%0d", P, cycles, checks, unknown, errs);
`else
        $display("RESULT sim=icarus outputs=%0d cycles=%0d checked=%0d partial=%0d errors=%0d", P, cycles, checks, unknown, errs);
`endif
        if (errs != 0) $fatal(1);
        $finish;
    end
endmodule
// restore the default for the files that follow (the PDK cell models use implicit nets)
`default_nettype wire
