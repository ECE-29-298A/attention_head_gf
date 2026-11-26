// Second-simulator (Icarus) check: applies golden-model vectors "a b cin s" (hex)
// to ripple_add #(N) and compares s with the file. Plusarg +VEC=<file>.
`timescale 1ns/1ps
module tb_vectors;
    parameter N = 22;
    reg  [N-1:0] a, b, e;
    reg          cin;
    wire [N-1:0] s;
`ifdef GATE_LEVEL
    ripple_add dut (.a(a), .b(b), .cin(cin), .s(s));   // fixed-width netlist, width N
`else
    ripple_add #(.N(N)) dut (.a(a), .b(b), .cin(cin), .s(s));
`endif

    integer fd, rc, n_vec, n_bad, c_in;
    reg [1023:0] fname;
    reg [8*128-1:0] line;
    initial begin
        n_vec = 0; n_bad = 0;
        if (!$value$plusargs("VEC=%s", fname)) begin
            $display("RESULT sim=icarus N=%0d vectors=0 mismatches=1 (no +VEC)", N);
            $finish_and_return(1);
        end
        fd = $fopen(fname, "r");
        if (fd == 0) begin
            $display("RESULT sim=icarus N=%0d vectors=0 mismatches=1 (cannot open)", N);
            $finish_and_return(1);
        end
        while (!$feof(fd)) begin
            rc = $fgets(line, fd);
            if (rc > 0 && line[8*rc-1 -: 8] != "#") begin
                rc = $sscanf(line, "%h %h %h %h", a, b, c_in, e);
                if (rc == 4) begin
                    cin = c_in[0];
                    #1;
                    n_vec = n_vec + 1;
                    if (s !== e) begin
                        n_bad = n_bad + 1;
                        if (n_bad <= 20)
                            $display("MISMATCH N=%0d a=%h b=%h cin=%b s=%h exp=%h", N, a, b, cin, s, e);
                    end
                end
            end
        end
        $fclose(fd);
        $display("RESULT sim=icarus N=%0d vectors=%0d mismatches=%0d", N, n_vec, n_bad);
        if (n_bad != 0 || n_vec == 0) $finish_and_return(1);
        $finish;
    end
endmodule
