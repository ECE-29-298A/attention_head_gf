// Tiny Tapeout wrapper. The host sends N,Q0,Q1,Q2,Q3 on ui_in; the chip
// reads K/V from external QSPI flash and streams four result bytes on uo_out.
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
    localparam [2:0] COUNT = 3'd0, Q0 = 3'd1, Q1 = 3'd2,
                     Q2 = 3'd3, Q3 = 3'd4, LAUNCH = 3'd5, RUN = 3'd6;
    reg [2:0] stage;
    reg [4:0] count;
    reg [31:0] query;

    // uio[6] is host valid during configuration and host ready during output.
    // uio[7] is chip ready during configuration and chip valid during output.
    wire active = rst_n && ena;
    wire count_valid = ui_in >= 8'd1 && ui_in <= 8'd16;
    wire cfg_ready = active &&
        ((stage == COUNT && count_valid) ||
         stage == Q0 || stage == Q1 || stage == Q2 || stage == Q3);
    wire cfg_accept = cfg_ready && uio_in[6];

    wire core_start_ready, core_busy, core_done;
    wire core_mem_req_valid, core_mem_req_ready, core_mem_write;
    wire core_mem_rsp_valid, core_out_valid;
    wire [15:0] core_mem_addr;
    wire [7:0] core_mem_wdata, core_mem_rdata;
    wire signed [7:0] core_out_data;
    wire core_start = active && stage == LAUNCH && core_start_ready;
    wire [3:0] spi_io_o, spi_io_oe;
    wire spi_sck, spi_cs_n;

    attention_controller #(.LATCH_QUERY(1'b0)) core (
        .clk(clk), .rst_n(active),
        .start(core_start), .token_count(count), .query_packed(query),
        .start_ready(core_start_ready), .busy(core_busy), .done(core_done),
        .mem_req_valid(core_mem_req_valid), .mem_req_ready(core_mem_req_ready),
        .mem_write(core_mem_write), .mem_addr(core_mem_addr),
        .mem_wdata(core_mem_wdata),
        .mem_rsp_valid(core_mem_rsp_valid), .mem_rdata(core_mem_rdata),
        .out_valid(core_out_valid), .out_ready(uio_in[6]),
        .out_data(core_out_data)
    );
    qspi_read_adapter memory (
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

    // All five bytes are replaced before launch. Keep the query stable
    // throughout RUN so the controller can use this bank directly.
    wire query_phase = stage == Q0 || stage == Q1 || stage == Q2 || stage == Q3;
    always @(posedge clk) begin
        if (cfg_accept && stage == COUNT) count <= ui_in[4:0];
        if (cfg_accept && query_phase) query <= {ui_in, query[31:8]};
    end

    always @(posedge clk) begin
        if (!active) begin
            stage <= COUNT;
        end else begin
            case (stage)
                COUNT: if (cfg_accept) stage <= Q0;
                Q0: if (cfg_accept) stage <= Q1;
                Q1: if (cfg_accept) stage <= Q2;
                Q2: if (cfg_accept) stage <= Q3;
                Q3: if (cfg_accept) stage <= LAUNCH;
                LAUNCH: if (core_start_ready) stage <= RUN;
                RUN: if (core_done) stage <= COUNT;
                default: stage <= COUNT;
            endcase
        end
    end
endmodule

`default_nettype wire
