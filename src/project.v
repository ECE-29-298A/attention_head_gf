// Tiny Tapeout wrapper. The host sends {2'b00, chunk[4], N[4:0]}, then
// {chunk[3:0], shift[3:0]} on ui_in; the chip reads Q/K/V from external QSPI
// flash and streams four result bytes on uo_out: V components 2*chunk and
// 2*chunk+1 of the attention output as two signed 12-bit results (1/16 V steps),
// each low byte first, sign-extended.
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
    reg chunk_hi;          // chunk[4], sent in bit 5 of the count byte
    reg [7:0] config_byte; // {chunk[3:0], shift}

    // uio[6] is host valid during configuration and host ready during output.
    // uio[7] is chip ready during configuration and chip valid during output.
    wire active = rst_n && ena;
    // Count byte: {2'b00, chunk[4], N}. Bits 7:6 are reserved and must be zero.
    wire count_valid = ui_in[7:6] == 2'b00 && ui_in[4:0] >= 5'd1 && ui_in[4:0] <= 5'd16;
    wire cfg_ready = active && ((stage == COUNT && count_valid) || stage == CONFIG);
    wire cfg_accept = cfg_ready && uio_in[6];

    wire core_start_ready, core_busy, core_done;
    wire core_mem_req_valid, core_mem_req_ready, core_mem_write;
    wire core_mem_rsp_valid, core_out_valid;
    wire [15:0] core_mem_addr;
    wire [7:0] core_mem_wdata, core_mem_rdata;
    wire [7:0] core_out_data;
    wire core_start = active && stage == LAUNCH && core_start_ready;
    wire [3:0] spi_io_o, spi_io_oe;
    wire spi_sck, spi_cs_n;

    attention_controller #(.LATCH_CONFIG(1'b0)) core (
        .clk(clk), .rst_n(active),
        .start(core_start), .token_count(count),
        .score_shift(config_byte[3:0]), .chunk({chunk_hi, config_byte[7:4]}),
        .start_ready(core_start_ready), .busy(core_busy), .done(core_done),
        .mem_req_valid(core_mem_req_valid), .mem_req_ready(core_mem_req_ready),
        .mem_write(core_mem_write), .mem_addr(core_mem_addr),
        .mem_wdata(core_mem_wdata),
        .mem_rsp_valid(core_mem_rsp_valid), .mem_rdata(core_mem_rdata),
        .out_valid(core_out_valid), .out_ready(uio_in[6]),
        .out_data(core_out_data)
    );
    // The controller holds mem_addr stable from request until response.
    qspi_read_adapter #(.LATCH_ADDR(0)) memory (
        .clk(clk), .rst_n(active),
        .req_valid(core_mem_req_valid), .req_ready(core_mem_req_ready),
        .req_addr(core_mem_addr), .rsp_valid(core_mem_rsp_valid),
        .rsp_data(core_mem_rdata),
        .io_i(uio_in[3:0]), .io_o(spi_io_o), .io_oe(spi_io_oe),
        .sck(spi_sck), .cs_n(spi_cs_n)
    );

    // uio[3:0] QSPI IO0..3; [4] SCK; [5] CS_n; [6] host valid/ready;
    // [7] chip ready/valid. The flash must support 0x03 single-lane reads.
    assign uio_out = {cfg_ready || core_out_valid, 1'b0,
                      spi_cs_n, spi_sck, spi_io_o};
    assign uio_oe = {1'b1, 1'b0, 2'b11, spi_io_oe};
    assign uo_out = core_out_valid ? core_out_data : 8'd0;
    wire _unused = &{uio_in[7], uio_in[5:4], core_mem_write,
                     core_mem_wdata, core_busy, core_done, 1'b0};

    // Both bytes are replaced before launch. Keep the config stable
    // throughout RUN so the controller can use it directly.
    always @(posedge clk) begin
        if (cfg_accept && stage == COUNT) {chunk_hi, count} <= ui_in[5:0];
        if (cfg_accept && stage == CONFIG) config_byte <= ui_in;
    end

    always @(posedge clk) begin
        if (!active) begin
            stage <= COUNT;
        end else begin
            case (stage)
                COUNT: if (cfg_accept) stage <= CONFIG;
                CONFIG: if (cfg_accept) stage <= LAUNCH;
                LAUNCH: if (core_start_ready) stage <= RUN;
                RUN: if (core_done) stage <= COUNT;
                default: stage <= COUNT;
            endcase
        end
    end
endmodule

`default_nettype wire
