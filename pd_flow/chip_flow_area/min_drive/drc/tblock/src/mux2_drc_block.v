// Routed DRC test block for gf180mcu_fd_sc_mcu7t5v0__mux2_1 (chip_flow_area/min_drive, experiment 2).
// 64 hand-instantiated mux2_1 (4 registered stages x 16 bits) guarantee the cell in many placements and
// orientations; the inferred 2:1 muxes, XORs, adders and flops around them give it mixed neighbours.
`default_nettype none
module mux2_drc_block (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [15:0] a,
    input  wire [15:0] b,
    input  wire [7:0]  s,
    output wire [15:0] y,
    output reg  [15:0] z,
    output reg  [15:0] w
);
    reg  [15:0] r [0:4];
    wire [15:0] m [0:3];
    genvar k, i;
    generate
        for (k = 0; k < 4; k = k + 1) begin : stage
            for (i = 0; i < 16; i = i + 1) begin : bitm
                gf180mcu_fd_sc_mcu7t5v0__mux2_1 u_mux (
                    .I0(r[k][i]), .I1(r[k][(i + 5) % 16] ^ b[(i + k) % 16]), .S(s[k] ^ r[k][(i + 3) % 16]), .Z(m[k][i]));
            end
        end
    endgenerate
    integer j;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (j = 0; j < 5; j = j + 1) r[j] <= 16'h0;
            z <= 16'h0;
            w <= 16'h0;
        end else begin
            w    <= s[1] ? a : b;  // plain 2:1 mux bank for synthesis to map
            r[0] <= a;
            r[1] <= m[0];
            r[2] <= m[1] + {8'h0, s};
            r[3] <= s[5] ? m[2] : (m[2] ^ a);
            r[4] <= m[3];
            z    <= s[6] ? (r[4] & b) : (s[7] ? r[4] : (r[4] | a));
        end
    end
    assign y = r[4] ^ {r[3][7:0], r[2][15:8]};
endmodule
