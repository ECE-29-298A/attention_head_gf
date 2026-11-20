// 0x03 (1-1-1) SPI flash read, mode 0: 8 command + 24 address + 8 data bits per
// byte, one CS pulse each. req must stay high with a stable addr until ack (one
// cycle); keeping req high after ack starts the next read. The data byte arrives
// on miso, MSB first: it is valid on the clock edges that end rx_valid cycles.
`default_nettype none
module spi_read (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        req,
    input  wire [11:0] addr,
    output wire        ack,
    output wire        rx_valid,
    output wire        mosi,
    output wire        sck,
    output reg         cs_n
);
    reg [6:0] n; // {bit index 0..39, SCK phase}
    wire [15:0] addr16 = {4'b0, addr};
    assign ack = n == 7'd79;
    assign sck = n[0];
    // Data bits, sampled on the rising SCK edge. n steps to 80 on the ack edge, as CS rises.
    assign rx_valid = !cs_n && n[6] && !n[0];
    // Bits 0..7: 0x03. 8..15: zero top address byte. 16..31: addr16, MSB first.
    assign mosi = n[5] ? addr16[~n[4:1]] : n[4:2] == 3'b011;
    always @(posedge clk) begin
        cs_n <= !rst_n || (cs_n ? !req : ack);
        n <= !rst_n || cs_n ? 7'd0 : n + 7'd1;
    end
endmodule
`default_nettype wire
