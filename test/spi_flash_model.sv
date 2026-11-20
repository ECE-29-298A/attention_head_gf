`timescale 1ns/1ps
// Behavioural SPI NOR flash: standard 0x03 read in mode 0, one data byte per CS
// pulse. Written from the flash protocol, not from the RTL. Pins change on the
// rising clk edge, so the model samples them on the falling edge.
// MISO only carries data while SCK is low before each data bit's rising edge
// (mode 0 samples on the rise). Everywhere else it is random, so a master
// sampling on the wrong edge or at the wrong time reads garbage.
module spi_flash_model #(parameter int SIZE = 16) (
    input  wire  clk,
    input  wire  abort_ok,  // master is being reset: CS may rise mid-transaction
    input  wire  cs_n,
    input  wire  sck,
    input  wire  mosi,
    input  wire  mosi_oe,
    output logic miso
);
    logic [7:0] memory [0:SIZE-1];
    int count [0:SIZE-1];      // completed reads per address
    int reads = 0, bits = 0;   // completed reads in total; SCK rises in this CS pulse
    logic [31:0] command = 0;  // {opcode, 24-bit address} as shifted in
    logic prev_cs = 1, prev_sck = 0, prev_mosi = 0, prev_oe = 0;
    logic data_valid = 0, data_bit = 0, abort_seen = 0;
    wire [23:0] address = command[23:0];

    always @(posedge clk) if (abort_ok) abort_seen = 1;
    always @(negedge clk) begin
        if (cs_n) begin
            assert (!sck) else $fatal(1, "SCK high while the flash is deselected");
            if (!prev_cs) begin
                if (bits == 40) begin reads++; count[int'(address)]++; end
                else assert (abort_seen) else $fatal(1, "CS released after %0d of 40 bits", bits);
            end
            data_valid = 0;
        end else if (prev_cs) begin
            assert (!sck) else $fatal(1, "Mode 0 needs SCK low when CS falls");
            bits = 0; abort_seen = 0;
        end else if (sck && !prev_sck) begin
            assert (bits < 40) else $fatal(1, "More than 40 SCK pulses in one CS pulse");
            if (bits < 32) begin
                // The flash samples MOSI on this rise: it must have been set up a clock earlier.
                assert (mosi_oe && prev_oe && mosi == prev_mosi)
                    else $fatal(1, "MOSI not driven and stable at SCK rise %0d", bits);
                command = {command[30:0], mosi};
                if (bits == 31)
                    assert (command[31:24] == 8'h03 && address < 24'(SIZE))
                        else $fatal(1, "Bad flash command %h", command);
            end
            bits++;
        end else if (!sck && prev_sck) begin
            data_valid = bits >= 32 && bits < 40;
            if (data_valid) data_bit = memory[int'(address)][39 - bits];
        end
        miso = data_valid && !sck ? data_bit : 1'($urandom);
        prev_cs = cs_n; prev_sck = sck; prev_mosi = mosi; prev_oe = mosi_oe;
    end
endmodule
