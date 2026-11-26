// Tiny Tapeout wrapper: an SPI target (mode 0) for the host, and the quad SPI
// flash controller for the Q/K/V tape on the TT QSPI Pmod pins.
// docs/pin-protocol.md has the host timing rules.
// Config frame (16 bits, MSB first): 7 zeros, cont, shift[3:0], N-1[3:0]; the run
// starts when CS# rises. Each result frame (16 bits, sent while DRDY is high) is a
// signed 12-bit result, then 4 zeros; its CS# rise moves on to the next of the
// OUTPUTS components (8), and after the last one the chip is idle.
// cont = 0 restarts the tape (pass 1, then the first chunk); cont = 1 computes the
// next chunk on the tape. See attention_controller.sv for the tape layout.
`default_nettype none

module tt_um_attention_head_gf #(
    parameter OUTPUTS = 8 // outputs per run: 2, 4 or 8
) (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    // SCK and CS# pass through two synchronizer flops, then one more for edge
    // detection. None of these are reset: the host holds CS# high during reset
    // (>= 3 clk). MOSI needs no synchronizer: the chain takes it 2-3 clk after
    // the SCK pin rises, and the host holds it from 4 clk before to 4 clk after.
    reg [2:0] sck_sync, cs_sync;
    // Config shift chain {cont, shift[3:0], last[3:0]}, last = N - 1. It shifts
    // only while the core is idle, so it is held for the whole run.
    reg [8:0] config_chain;

    wire sck_rise = sck_sync[1] && !sck_sync[2];
    wire sck_fall = !sck_sync[1] && sck_sync[2];
    wire cs_low = !cs_sync[1];
    wire cs_rise = cs_sync[1] && !cs_sync[2];

    wire core_idle, drdy, miso, spi_cs_n, spi_sck, spi_mosi, spi_mosi_oe;

    // A CS# rise starts a run when idle and finishes a result read when DRDY is
    // high; the controller ignores it in every other state.
    attention_controller #(.OUTPUTS(OUTPUTS)) core (
        .clk(clk), .rst_n(rst_n && ena), .start(cs_rise),
        .last(config_chain[3:0]), .score_shift(config_chain[7:4]), .cont(config_chain[8]),
        .idle(core_idle),
        .spi_cs_n(spi_cs_n), .spi_sck(spi_sck), .spi_mosi(spi_mosi), .spi_mosi_oe(spi_mosi_oe),
        .spi_io({uio_in[5:4], uio_in[2:1]}),
        .out_valid(drdy), .out_ready(cs_rise), .out_shift(sck_fall && cs_low), .out_bit(miso)
    );

    // TT QSPI Pmod: uio[0] flash CS#; [1] IO0, driven only for command and
    // address; [2] IO1; [3] SCK; [4] IO2; [5] IO3; [7:6] the RAMs' CS#, held high.
    assign uio_out = {2'b11, 2'b00, spi_sck, 1'b0, spi_mosi, spi_cs_n};
    assign uio_oe = {2'b11, 2'b00, 1'b1, 1'b0, spi_mosi_oe, 1'b1};
    assign uo_out = {6'd0, drdy, miso};
    wire _unused = &{ui_in[7:3], uio_in[7:6], uio_in[3], uio_in[0], 1'b0};

    always @(posedge clk) begin
        sck_sync <= {sck_sync[1:0], ui_in[0]};
        cs_sync <= {cs_sync[1:0], ui_in[2]};
        if (sck_rise && cs_low && core_idle) config_chain <= {config_chain[7:0], ui_in[1]};
    end
endmodule

`default_nettype wire
