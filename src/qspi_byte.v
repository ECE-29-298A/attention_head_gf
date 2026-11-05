module qspi_byte (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,
    input  wire       wide,
    input  wire       tx_en,
    input  wire       last,
    input  wire [7:0] tx_data,
    output wire       ready,
    output wire       done,
    output wire [7:0] rx_data,
    output wire       cs_n,
    output wire       sck,
    input  wire [3:0] io_i,
    output wire [3:0] io_o,
    output wire [3:0] io_oe
);
    spi_multi_io_byte #(.LANES(4)) engine (
        .clk(clk), .rst_n(rst_n), .start(start), .wide(wide),
        .tx_en(tx_en), .last(last), .tx_data(tx_data),
        .ready(ready), .done(done), .rx_data(rx_data),
        .cs_n(cs_n), .sck(sck), .io_i(io_i),
        .io_o(io_o), .io_oe(io_oe)
    );
endmodule
