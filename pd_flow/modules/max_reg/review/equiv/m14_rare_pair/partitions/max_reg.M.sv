module miter (
  input  [ 21:0] \__pi_S_in ,
  input  [  0:0] \__pi_clk ,
  input  [  0:0] \__pi_en ,
  input  [  0:0] \__pi_first ,
`ifdef DIRECT_CROSS_POINTS
`else
`endif
  output [ 21:0] \__po_M__gold ,
  output [ 21:0] \__po_M__gate
);
  \gold.max_reg.M gold (
    .\__pi_S_in (\__pi_S_in ),
    .\__pi_clk (\__pi_clk ),
    .\__pi_en (\__pi_en ),
    .\__pi_first (\__pi_first ),
`ifdef DIRECT_CROSS_POINTS
`else
`endif
    .\__po_M (\__po_M__gold )
  );
  \gate.max_reg.M gate (
    .\__pi_S_in (\__pi_S_in ),
    .\__pi_clk (\__pi_clk ),
    .\__pi_en (\__pi_en ),
    .\__pi_first (\__pi_first ),
`ifdef DIRECT_CROSS_POINTS
`else
`endif
    .\__po_M (\__po_M__gate )
  );
`ifdef ASSUME_DEFINED_INPUTS
  miter_def_prop #(22, "assume") \__pi_S_in__assume (\__pi_S_in );
  miter_def_prop #(1, "assume") \__pi_clk__assume (\__pi_clk );
  miter_def_prop #(1, "assume") \__pi_en__assume (\__pi_en );
  miter_def_prop #(1, "assume") \__pi_first__assume (\__pi_first );
`endif
`ifndef DIRECT_CROSS_POINTS
`endif
`ifdef CHECK_MATCH_POINTS
`endif
`ifdef CHECK_OUTPUTS
  miter_cmp_prop #(22, "assert") \__po_M__assert (\__po_M__gold , \__po_M__gate );
`endif
`ifdef COVER_DEF_CROSS_POINTS
  `ifdef DIRECT_CROSS_POINTS
  `else
  `endif
`endif
`ifdef COVER_DEF_GOLD_MATCH_POINTS
`endif
`ifdef COVER_DEF_GATE_MATCH_POINTS
`endif
`ifdef COVER_DEF_GOLD_OUTPUTS
  miter_def_prop #(22, "cover") \__po_M__gold_cover (\__po_M__gold );
`endif
`ifdef COVER_DEF_GATE_OUTPUTS
  miter_def_prop #(22, "cover") \__po_M__gate_cover (\__po_M__gate );
`endif
endmodule
module miter_cmp_prop #(parameter WIDTH=1, parameter TYPE="assert") (input [WIDTH-1:0] in_gold, in_gate);
  reg okay;
  integer i;
  always @* begin
    okay = 1;
    for (i = 0; i < WIDTH; i = i+1)
      okay = okay && (in_gold[i] === 1'bx || in_gold[i] === in_gate[i]);
  end
  generate
    if (TYPE == "assert") always @* assert(okay);
    if (TYPE == "assume") always @* assume(okay);
    if (TYPE == "cover")  always @* cover(okay);
  endgenerate
endmodule
module miter_def_prop #(parameter WIDTH=1, parameter TYPE="assert") (input [WIDTH-1:0] in);
  wire okay = ^in !== 1'bx;
  generate
    if (TYPE == "assert") always @* assert(okay);
    if (TYPE == "assume") always @* assume(okay);
    if (TYPE == "cover")  always @* cover(okay);
  endgenerate
endmodule
module \gold.max_reg.M (
  input  [ 21:0] \__pi_S_in ,
  input  [  0:0] \__pi_clk ,
  input  [  0:0] \__pi_en ,
  input  [  0:0] \__pi_first ,
  output [ 21:0] \__po_M
);
endmodule
module \gate.max_reg.M (
  input  [ 21:0] \__pi_S_in ,
  input  [  0:0] \__pi_clk ,
  input  [  0:0] \__pi_en ,
  input  [  0:0] \__pi_first ,
  output [ 21:0] \__po_M
);
endmodule
