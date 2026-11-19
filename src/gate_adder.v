module full_adder (
    input wire a,
    input wire b,
    input wire cin,
    output wire sum,
    output wire cout
);
    wire inxor; 

    assign inxor = a ^ b;
    assign sum = inxor ^ cin;
    assign cout = (a & b) | (cin & (inxor));
    
endmodule

