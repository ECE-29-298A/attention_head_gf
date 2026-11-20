`timescale 1ns/1ps
// Black-box check of spi_read: only its ports are used. The flash model checks
// the SPI side; this file checks the request/response contract: req held with
// a stable addr until ack, exactly 8 rx_valid strobes carrying the byte MSB
// first, a one-cycle ack, and req kept high after ack meaning the next read.
module tb_spi_read;
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, req = 0;
    logic [11:0] addr = 0;
    wire ack, rx_valid, mosi, sck, cs_n, miso;
    spi_read dut (.*);
    spi_flash_model #(.SIZE(4096)) flash (.clk, .abort_ok(!rst_n), .cs_n, .sck, .mosi, .mosi_oe(1'b1), .miso);

    bit pending = 0, was_reset = 0;
    logic [11:0] pending_addr;
    logic [7:0] byte_in;
    int age = 0, bits_in = 0, responses = 0;
    always @(posedge clk) begin
        if (was_reset)
            assert (cs_n && !sck) else $fatal(1, "One clock of reset did not release the bus");
        was_reset = !rst_n;
        if (!rst_n) pending = 0;
        else begin
            if (rx_valid) begin
                assert (pending && bits_in < 8) else $fatal(1, "rx_valid outside the 8 data bits of a read");
                byte_in = {byte_in[6:0], miso}; bits_in++;
            end
            if (ack) begin
                assert (pending) else $fatal(1, "ack without a request (or longer than one cycle)");
                assert (flash.bits == 40 && flash.command == {20'h03000, pending_addr})
                    else $fatal(1, "ack before the flash finished reading %h", pending_addr);
                assert (bits_in == 8 && byte_in == flash.memory[pending_addr])
                    else $fatal(1, "Address %h: %0d bits %h, flash holds %h", pending_addr, bits_in, byte_in, flash.memory[pending_addr]);
                pending = 0; responses++;
            end else if (pending) begin
                age++;
                assert (req && addr == pending_addr) else $fatal(1, "Testbench dropped a request");
                assert (age < 100) else $fatal(1, "No ack for address %h", pending_addr);
            end else if (req) begin
                pending = 1; pending_addr = addr; age = 0; bits_in = 0;
            end
        end
    end

    // addr is only meaningful while req is high: garbage otherwise.
    task automatic read(input logic [11:0] a);
        if (!req) repeat ($urandom_range(0, 3)) begin addr = 12'($urandom); @(negedge clk); end
        addr = a; req = 1;
        do @(negedge clk); while (!ack);
        @(negedge clk);
        req = 1'($urandom);  // keep requesting: the next read starts back to back
        if (!req) addr = 12'($urandom);
    endtask

    initial begin
        foreach (flash.memory[i]) flash.memory[i] = 8'($urandom);
        @(negedge clk);  // power-up state is random: one clock of reset must be enough
        rst_n = 1;
        for (int a = 0; a < 4096; a++) read(12'(a));
        for (int i = 0; i < 20000; i++) read(12'($urandom));
        req = 0;
        repeat (4) @(negedge clk);
        assert (!pending && flash.reads == responses && cs_n)
            else $fatal(1, "Flash completed %0d reads for %0d acks", flash.reads, responses);
        // Reset on every cycle of a transaction, for one and for two clocks.
        for (int offset = 0; offset < 90; offset++)
            for (int length = 1; length <= 2; length++) begin
                addr = 12'($urandom); req = 1;
                repeat (offset) @(negedge clk);
                rst_n = 0; req = 0;
                repeat (length) @(negedge clk);
                rst_n = 1;
                repeat (3) read(12'($urandom));
                req = 0;
                do @(negedge clk); while (pending);
            end
        $display("PASS: spi_read %0d reads; every address, 0x03 framing, MOSI setup, MISO window, 8 strobes per byte, one-cycle ack, back-to-back requests, reset on every cycle", responses);
        $finish;
    end
    initial begin #2000000000; $fatal(1, "spi_read timeout"); end
endmodule
