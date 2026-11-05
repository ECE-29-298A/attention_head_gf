`timescale 1ns/1ps

module tb_spi_byte;
    parameter integer LANES = 4;
    reg clk = 0;
    always #5 clk = ~clk;

    reg rst_n = 0, start = 0, wide = 0, tx_en = 0, last = 0;
    reg [7:0] tx_data = 0;
    reg [LANES-1:0] io_i = 0;
    wire ready, done, cs_n, sck;
    wire [7:0] rx_data;
    wire [LANES-1:0] io_o, io_oe;

    generate if (LANES == 4) begin : quad
        qspi_byte dut (
            .clk(clk), .rst_n(rst_n), .start(start), .wide(wide),
            .tx_en(tx_en), .last(last), .tx_data(tx_data),
            .ready(ready), .done(done), .rx_data(rx_data),
            .cs_n(cs_n), .sck(sck), .io_i(io_i),
            .io_o(io_o), .io_oe(io_oe)
        );
    end else begin : octal
        ospi_byte dut (
            .clk(clk), .rst_n(rst_n), .start(start), .wide(wide),
            .tx_en(tx_en), .last(last), .tx_data(tx_data),
            .ready(ready), .done(done), .rx_data(rx_data),
            .cs_n(cs_n), .sck(sck), .io_i(io_i),
            .io_o(io_o), .io_oe(io_oe)
        );
    end endgenerate

    task check;
        input condition;
        input [255:0] message;
        begin
            if (!condition) begin
                $display("FAIL %0d lanes: %0s at %0t", LANES, message, $time);
                $fatal(1);
            end
        end
    endtask

    task transfer;
        input use_wide, drive, end_cs;
        input [7:0] sent, received;
        integer nbeats, width, j;
        reg [LANES-1:0] expected_oe, expected_out;
        begin
            width = use_wide ? LANES : 1;
            nbeats = 8 / width;
            expected_oe = drive ? (use_wide ? {LANES{1'b1}} :
                                   {{(LANES-1){1'b0}},1'b1}) : 0;
            @(negedge clk);
            check(ready && !done && !sck, "not ready before start");
            wide = use_wide;
            tx_en = drive;
            last = end_cs;
            tx_data = sent;
            start = 1;
            @(posedge clk); #1;
            check(!ready && !cs_n && !sck, "start timing");
            check(io_oe == expected_oe, "output enables");
            for (j = 0; j < nbeats; j = j + 1) begin
                @(negedge clk);
                start = 0;
                wide = ~use_wide;
                tx_en = ~drive;
                last = ~end_cs;
                tx_data = ~sent;
                if (use_wide) begin
                    io_i = received >> (8 - (j + 1) * width);
                    expected_out = sent >> (8 - (j + 1) * width);
                end else begin
                    io_i = 0;
                    io_i[1] = received[7-j];
                    expected_out = 0;
                    expected_out[0] = sent[7-j];
                end
                check(io_o == expected_out, "transmit lane order");
                check(io_oe == expected_oe, "latched output enables");
                @(posedge clk); #1;
                check(sck && !done && !ready, "rising clock");
                @(posedge clk); #1;
                check(!sck && !done && !ready, "falling clock");
            end
            @(posedge clk); #1;
            check(done && ready && !sck, "completion pulse");
            check(cs_n == end_cs, "chip select completion");
            check(rx_data == received, "receive byte");
            if (end_cs)
                check(io_oe == 0, "released pins after transaction");
            @(posedge clk); #1;
            check(!done && ready, "done must pulse once");
        end
    endtask

    initial begin
        repeat (2) @(posedge clk);
        @(negedge clk); rst_n = 1;
        #1; check(ready && cs_n && !sck && !done, "reset state");
        transfer(0, 1, 0, 8'h9f, 8'ha5);
        transfer(1, 0, 0, 8'h00, 8'h3c);
        transfer(1, 1, 1, 8'hd2, 8'h5a);
        transfer(0, 0, 1, 8'h00, 8'hc7);
        @(negedge clk);
        start = 1;
        wide = 1;
        tx_en = 1;
        last = 0;
        tx_data = 8'h69;
        @(posedge clk); #1;
        check(!ready && !cs_n, "transaction before abort");
        @(negedge clk);
        start = 0;
        rst_n = 0;
        #1;
        check(ready && cs_n && !sck && !done && io_oe == 0,
              "asynchronous reset abort");
        @(negedge clk); rst_n = 1;
        transfer(1, 0, 1, 8'h00, 8'h96);
        $display("PASS %0d lanes", LANES);
        $finish;
    end
endmodule
