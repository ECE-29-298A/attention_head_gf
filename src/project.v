// Tiny Tapeout wrapper. The host sends N, then {chunk[3:0], shift[3:0]} on ui_in;
// the chip reads Q/K/V from external SPI flash and streams eight result bytes on
// uo_out: V components 4*chunk..4*chunk+3 of the attention output as four signed
// 12-bit results (1/16 V steps), each low byte first, sign-extended.
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
    reg have_count;        // N accepted; the config byte comes next
    reg [3:0] last;        // N - 1
    reg [7:0] config_byte; // {chunk, shift}
    wire active = rst_n && ena;
    wire idle, out_valid, mem_req, mem_ack, rx_valid, mosi, sck, cs_n;
    wire [11:0] mem_addr;
    // uio[6] is host valid during configuration and host ready during output.
    // uio[7] is chip ready during configuration and chip valid during output.
    wire cfg_ready = idle && (have_count || (ui_in >= 8'd1 && ui_in <= 8'd16));
    wire cfg_accept = cfg_ready && uio_in[6];

    // The config registers only change while idle, so they are stable for a whole run.
    // config_byte follows ui_in while idle and freezes on the start edge.
    always @(posedge clk) begin
        have_count <= active && (have_count ^ cfg_accept);
        if (cfg_accept && !have_count) last <= ui_in[3:0] - 4'd1;
        if (idle) config_byte <= ui_in;
    end

    attention_controller core (
        .clk(clk), .rst_n(active), .start(cfg_accept && have_count), .last(last),
        .score_shift(config_byte[3:0]), .chunk(config_byte[7:4]), .idle(idle),
        .mem_req(mem_req), .mem_addr(mem_addr), .mem_ack(mem_ack),
        .rx_valid(rx_valid), .rx_bit(uio_in[1]),
        .out_valid(out_valid), .out_ready(uio_in[6]), .out_data(uo_out)
    );
    spi_read memory (
        .clk(clk), .rst_n(active), .req(mem_req), .addr(mem_addr), .ack(mem_ack),
        .rx_valid(rx_valid), .mosi(mosi), .sck(sck), .cs_n(cs_n)
    );

    // uio[0] MOSI; [1] MISO; [3:2] unused (the board holds flash WP#/HOLD# high);
    // [4] SCK; [5] CS_n; [6] host valid/ready; [7] chip ready/valid.
    assign uio_out = {cfg_ready || out_valid, 1'b0, cs_n, sck, 3'b0, mosi};
    assign uio_oe = 8'b1011_0001;
    wire _unused = &{uio_in[7], uio_in[5:2], uio_in[0], 1'b0};
endmodule

`default_nettype wire
