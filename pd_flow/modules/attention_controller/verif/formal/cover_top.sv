// Cover witness driver (SPEC.md section 8). The cover groups of ctrl_int_props.vh need traces
// that hold a whole 1024-clock score row, which a free-input BMC cannot reach in time. Each
// group task therefore drives the controller's inputs from this fixed host stimulus (clk is
// the only free signal; the power-up state of every non-reset register stays free) and abc
// bmc3 replays it on the formal model: refuting w_group is the witness that every cover of the
// group was reached after a reset. A stimulus only exhibits a trace; it constrains nothing that
// any assertion relies on (the assertions are proven in int_P with every input free).
//   DRV_G1  continue run, last = 0, all P results read (shift, then ready one clock later)
//   DRV_G2  fresh run, last = 1      DRV_G3  fresh run, last = 0      DRV_G4  continue, last = 1
//   DRV_G5  fresh start + reset in RESTART, fresh start + reset in CMD, continue + reset in SCORE
//   DRV_RST=<state>  continue run, last = 0, one reset in the first clock of that state
`default_nettype none
module cover_top #(parameter P = 8) (input wire clk);
    reg [11:0] c = 12'd0;
    always @(posedge clk) if (c != 12'hfff) c <= c + 12'd1;
    wire [2:0] w_state;   // the controller's state register, tied by `connect` (read-only)
    wire idle, spi_cs_n, spi_sck, spi_mosi, spi_mosi_oe, out_valid, out_bit;
    reg ovp = 1'b0;
    always @(posedge clk) ovp <= out_valid;
    wire out_shift = out_valid && !ovp;
    wire out_ready = out_valid && ovp;
    reg fired = 1'b0;
`ifdef DRV_G5
    wire rst_n = !(c == 12'd0 || c == 12'd3 || c == 12'd9 || c == 12'd13);
    wire start = c == 12'd2 || c == 12'd5 || c == 12'd11;
    wire cont = c == 12'd11;
    wire [3:0] last = 4'd0;
`else
`ifdef DRV_RST
    wire hit = c > 12'd2 && w_state == 3'd`DRV_RST && !fired;
    always @(posedge clk) if (hit) fired <= 1'b1;
    wire rst_n = c != 12'd0 && !hit;
`else
    wire rst_n = c != 12'd0;
`endif
    wire start = c == 12'd2;
`ifdef DRV_G2
    wire cont = 1'b0; wire [3:0] last = 4'd1;
`elsif DRV_G3
    wire cont = 1'b0; wire [3:0] last = 4'd0;
`elsif DRV_G4
    wire cont = 1'b1; wire [3:0] last = 4'd1;
`else
    wire cont = 1'b1; wire [3:0] last = 4'd0;
`endif
`endif
    attention_controller #(.OUTPUTS(P)) ctl (
        .clk(clk), .rst_n(rst_n), .start(start), .last(last), .score_shift(4'd0), .cont(cont),
        .idle(idle), .spi_cs_n(spi_cs_n), .spi_sck(spi_sck), .spi_mosi(spi_mosi),
        .spi_mosi_oe(spi_mosi_oe), .spi_io(4'd0), .out_valid(out_valid), .out_ready(out_ready),
        .out_shift(out_shift), .out_bit(out_bit));
    wire _unused = &{idle, spi_cs_n, spi_sck, spi_mosi, spi_mosi_oe, out_bit, fired, 1'b0};
endmodule
`default_nettype wire
