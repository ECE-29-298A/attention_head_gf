// One-outstanding-byte adapter for a 0x03 (1-1-1) SPI read from QSPI flash.
// A request is accepted only in IDLE; response-valid pulses after CS releases.
`default_nettype none
module qspi_read_adapter #(
    parameter [23:0] FLASH_BASE = 24'h000000
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        req_valid,
    output wire        req_ready,
    input  wire [15:0] req_addr,
    output reg         rsp_valid,
    output reg  [7:0]  rsp_data,
    input  wire [3:0]  io_i,
    output wire [3:0]  io_o,
    output wire [3:0]  io_oe,
    output wire        sck,
    output wire        cs_n
);
    localparam [1:0] IDLE = 2'd0, ISSUE = 2'd1, WAIT_BYTE = 2'd2;
    reg [1:0] state;
    reg [2:0] byte_index;
    reg [23:0] address;
    wire byte_ready, byte_done;
    wire [7:0] byte_rx;
    wire byte_start = rst_n && state == ISSUE && byte_ready;
    wire [7:0] byte_tx = byte_index == 3'd0 ? 8'h03 :
                         byte_index == 3'd1 ? address[23:16] :
                         byte_index == 3'd2 ? address[15:8] :
                         byte_index == 3'd3 ? address[7:0] : 8'd0;

    assign req_ready = rst_n && state == IDLE && byte_ready;
    qspi_byte serial (
        .clk(clk), .rst_n(rst_n), .start(byte_start),
        .wide(1'b0), .tx_en(byte_index != 3'd4), .last(byte_index == 3'd4),
        .tx_data(byte_tx), .ready(byte_ready), .done(byte_done),
        .rx_data(byte_rx), .cs_n(cs_n), .sck(sck),
        .io_i(io_i), .io_o(io_o), .io_oe(io_oe)
    );

    always @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            byte_index <= 0;
            address <= 0;
            rsp_valid <= 0;
            rsp_data <= 0;
        end else begin
            rsp_valid <= 0;
            case (state)
                IDLE: if (req_valid && req_ready) begin
                    address <= FLASH_BASE + {8'd0, req_addr};
                    byte_index <= 0;
                    state <= ISSUE;
                end
                ISSUE: if (byte_ready) state <= WAIT_BYTE;
                WAIT_BYTE: if (byte_done) begin
                    if (byte_index == 3'd4) begin
                        rsp_data <= byte_rx;
                        rsp_valid <= 1;
                        state <= IDLE;
                    end else begin
                        byte_index <= byte_index + 1'b1;
                        state <= ISSUE;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
