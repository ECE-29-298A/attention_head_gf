// Tiny Tapeout wrapper. The host sends N (1..16), then {cont, 3'b000, shift[3:0]}
// on ui_in; the chip reads its Q/K/V tape from external SPI flash and streams four
// result bytes on uo_out: two V components of the attention output as signed
// 12-bit results (1/16 V steps), each low byte first, sign-extended.
// cont = 0 restarts the tape (pass 1, then the first chunk); cont = 1 computes the
// next chunk on the tape. See attention_controller.sv for the tape layout.
`default_nettype none

module tt_um_attention_head_gf (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    localparam [1:0] COUNT = 2'd0, CONFIG = 2'd1, LAUNCH = 2'd2, RUN = 2'd3;
    reg [1:0] stage;
    reg [4:0] count;
    reg cont;
    reg [3:0] shift;

    // uio[6] is host valid during configuration and host ready during output.
    // uio[7] is chip ready during configuration and chip valid during output.
    wire active = rst_n && ena;
    wire count_valid = ui_in >= 8'd1 && ui_in <= 8'd16;
    wire cfg_ready = active && ((stage == COUNT && count_valid) || stage == CONFIG);
    wire cfg_accept = cfg_ready && uio_in[6];

    wire core_idle, core_out_valid, spi_cs_n, spi_sck, spi_mosi;
    wire [7:0] core_out_data;

    attention_controller core (
        .clk(clk), .rst_n(active), .start(stage == LAUNCH),
        .token_count(count), .score_shift(shift), .cont(cont), .idle(core_idle),
        .spi_cs_n(spi_cs_n), .spi_sck(spi_sck), .spi_mosi(spi_mosi), .spi_miso(uio_in[1]),
        .out_valid(core_out_valid), .out_ready(uio_in[6]), .out_data(core_out_data)
    );

    // uio[0] MOSI; [1] MISO; [3:2] unused (the board holds flash WP#/HOLD# high);
    // [4] SCK; [5] CS_n; [6] host valid/ready; [7] chip ready/valid.
    assign uio_out = {cfg_ready || core_out_valid, 1'b0, spi_cs_n, spi_sck, 3'b000, spi_mosi};
    assign uio_oe = 8'b1011_0001;
    assign uo_out = core_out_valid ? core_out_data : 8'd0;
    wire _unused = &{uio_in[7], uio_in[5:2], uio_in[0], 1'b0};

    // Both bytes are replaced before launch and stay stable throughout RUN.
    always @(posedge clk) begin
        if (cfg_accept && stage == COUNT) count <= ui_in[4:0];
        if (cfg_accept && stage == CONFIG) {cont, shift} <= {ui_in[7], ui_in[3:0]};
    end

    always @(posedge clk) begin
        if (!active) begin
            stage <= COUNT;
        end else begin
            case (stage)
                COUNT: if (cfg_accept) stage <= CONFIG;
                CONFIG: if (cfg_accept) stage <= LAUNCH;
                LAUNCH: stage <= RUN; // the controller is idle here and accepts start
                RUN: if (core_idle) stage <= COUNT;
                default: stage <= COUNT;
            endcase
        end
    end
endmodule

`default_nettype wire
