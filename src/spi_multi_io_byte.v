// Minimal mode-0 SDR SPI byte engine. One instance is either x1/x4 or x1/x8.
// No FIFO, divider, memory map, opcode decoder, or device-specific sequencing.
module spi_multi_io_byte #(
    parameter integer LANES = 4
) (
    input  wire                 clk,
    input  wire                 rst_n,
    input  wire                 start,
    input  wire                 wide,
    input  wire                 tx_en,
    input  wire                 last,
    input  wire [7:0]           tx_data,
    output wire                 ready,
    output reg                  done,
    output wire [7:0]           rx_data,
    output reg                  cs_n,
    output reg                  sck,
    input  wire [LANES-1:0]     io_i,
    output wire [LANES-1:0]     io_o,
    output wire [LANES-1:0]     io_oe
);
    localparam [1:0] IDLE = 2'd0, RISE = 2'd1,
                     FALL = 2'd2, FINISH = 2'd3;
    localparam [2:0] WIDE_LAST = (LANES == 4) ? 3'd1 : 3'd0;

    reg [1:0] state;
    reg [2:0] beats_left;
    reg [7:0] shift;
    reg [LANES-1:0] sampled;
    reg wide_r, tx_en_r, last_r;

    assign ready   = (state == IDLE);
    assign rx_data = shift;
    assign io_o    = wide_r ? shift[7 -: LANES] :
                     {{(LANES-1){1'b0}}, shift[7]};
    assign io_oe   = (tx_en_r && !cs_n) ? (wide_r ? {LANES{1'b1}} :
                     {{(LANES-1){1'b0}}, 1'b1}) : {LANES{1'b0}};

    // These registers are loaded by start/RISE before they are ever consumed.
    // Leaving them without reset permits smaller plain DFFs in GF180.
    always @(posedge clk) begin
        if (state == IDLE && start) begin
            shift      <= tx_data;
            beats_left <= wide ? WIDE_LAST : 3'd7;
            wide_r     <= wide;
            tx_en_r    <= tx_en;
            last_r     <= last;
        end else if (state == RISE) begin
            sampled <= io_i;
        end else if (state == FALL) begin
            shift <= wide_r ? (shift << LANES) |
                     {{(8-LANES){1'b0}}, sampled} :
                     {shift[6:0], sampled[1]};
            beats_left <= beats_left - 3'd1;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= IDLE;
            cs_n     <= 1'b1;
            sck      <= 1'b0;
            done     <= 1'b0;
        end else begin
            done <= 1'b0;
            case (state)
                IDLE: if (start) begin
                    cs_n     <= 1'b0;
                    state    <= RISE;
                end
                RISE: begin
                    sck <= 1'b1;
                    state <= FALL;
                end
                FALL: begin
                    sck <= 1'b0;
                    if (beats_left == 3'd0)
                        state <= FINISH;
                    else
                        state <= RISE;
                end
                FINISH: begin
                    if (last_r)
                        cs_n <= 1'b1;
                    done  <= 1'b1;
                    state <= IDLE;
                end
            endcase
        end
    end
endmodule
