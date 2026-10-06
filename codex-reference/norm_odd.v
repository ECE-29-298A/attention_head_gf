// Host-scheduled complete INT8 attention. Chip performs all arithmetic.
// When ready=1, accept command if cmd=1, otherwise accept operand byte.
// Commands: 0 begin head; 1 load scale; 2 Q,K MAC; 3 update max/clear dot;
// 4 exp/add denominator/emit weight; 5 weight,V MAC; 6 normalize/emit output.
// Commands 1/2/5 are followed by 1/2/2 operand bytes respectively.
// Acknowledge valid outputs with send=1. Host caches/replays weights unchanged.
module attention_extended #(parameter NB=10,DB=6,SERIAL=1)(
 input clk,rst_n,send,cmd,input[7:0]din,
 output reg[7:0]dout,output ready,output valid,output kind);
 localparam SW=16+DB,ZW=8+NB,AW=16+NB,W=(SW>AW)?SW:AW;
 localparam CMD=0,SCALE=1,A=2,B=3,MUL=4,MAX=5,EXP=6,WOUT=7,DINIT=8,DIV=9,OUT=10,SIGN=11,ESHIFT=12,ELOOK=13,QOUT=14,QEMIT=15,SQINIT=16,SQSTEP=17,SQEND=18;
 reg[4:0]state;reg quant_mode;reg mode_v;reg[4:0]scale;reg[7:0]operand;
 reg signed[W-1:0]acc;reg signed[SW-1:0]max_score;
 reg signed[AW-1:0]weighted;reg[ZW-1:0]denom;
 reg negative;reg[4:0]count;
 wire signed[8:0]ma=mode_v?$signed({1'b0,operand}):$signed({operand[7],operand});
 wire signed[16:0]product;
 generate if(SERIAL==0)begin assign product=ma*$signed(din);end
 else begin:sm
 reg signed[16:0]mp;
 wire signed[9:0]hi=$signed(mp[16:8]);
 wire signed[9:0]mh=mp[0]?(count==7?hi-ma:hi+ma):hi;
 wire signed[17:0]shifted=$signed({mh,mp[7:0]})>>>1;
 assign product=shifted[16:0];
 always @(posedge clk)begin
 if(state==B && send)begin mp<={9'b0,din};end
 else if(state==MUL)mp<=shifted[16:0];
 end
 end endgenerate
 wire do_sub=state==EXP || state==DIV || state==DINIT || state==MAX || state==SQSTEP;
 wire[W-1:0]alu_a=state==DINIT?{W{1'b0}}:state==EXP?{{(W-SW){max_score[SW-1]}},max_score}:
 (state==DIV || state==SQSTEP || (mode_v && state!=MAX))?{{(W-AW){weighted[AW-1]}},weighted}:acc;
 wire[W-1:0]alu_b=state==SQSTEP?{{(W-ZW){1'b0}},denom}:state==MAX?{{(W-SW){max_score[SW-1]}},max_score}:state==DINIT?{{(W-AW){weighted[AW-1]}},weighted}:do_sub?acc:{{(W-17){product[16]}},product};
 wire[W:0]alu={1'b0,alu_a}+{1'b0,(alu_b^{W{do_sub}})}+do_sub;
 wire[W-1:0]idx_full=acc;
 wire[5:0]idx=(|(idx_full>>5))?6'd63:{1'b0,idx_full[4:0]};
 wire[ZW-1:0]denom_next=denom+(state==SQSTEP?8'd2:exponent);
 reg[7:0]exponent;
 always @*begin
 case(idx)
 0:exponent=255;1:exponent=199;2:exponent=155;3:exponent=120;
 4:exponent=94;5:exponent=73;6:exponent=57;7:exponent=44;
 8:exponent=35;9:exponent=27;10:exponent=21;11:exponent=16;
 12:exponent=13;13:exponent=10;14:exponent=8;15:exponent=6;
 16:exponent=5;17:exponent=4;18:exponent=3;19:exponent=2;
 20:exponent=2;21:exponent=1;22:exponent=1;23:exponent=1;24:exponent=1;
 default:exponent=0;
 endcase
 end
 assign ready=state==CMD || state==SCALE || state==A || state==B;
 assign valid=state==WOUT || state==OUT || state==QEMIT;
 assign kind=state==OUT || state==QEMIT;
 always @(posedge clk)begin
 if(!rst_n)begin state<=CMD;end
 else case(state)
 CMD:if(send && cmd)case(din[3:0])
 0:begin quant_mode<=0;acc<=0;weighted<=0;denom<=0;max_score<={1'b1,{(SW-1){1'b0}}};mode_v<=0;end
 1:state<=SCALE;
 2:begin mode_v<=0;state<=A;end
 3:state<=MAX;
 4:begin quant_mode<=0;state<=EXP;end
 5:begin mode_v<=1;state<=A;end
 6:state<=DINIT;
 8:state<=SQINIT;
 7:begin quant_mode<=1;count<=0;state<=scale==0?QOUT:ESHIFT;end
 default:state<=CMD;
 endcase
 SCALE:if(send)begin scale<=din[4:0];state<=CMD;end
 A:if(send)begin operand<=din;state<=B;end
 B:if(send)begin
 if(SERIAL)begin count<=0;state<=MUL;end
 else begin
 if(mode_v)weighted<=alu[AW-1:0];else acc<=alu[W-1:0];
 state<=CMD;
 end
 end
 MUL:begin count<=count+1'b1;
 if(count==7)begin
 if(mode_v)weighted<=alu[AW-1:0];else acc<=alu[W-1:0];
 state<=CMD;
 end
 end
 MAX:begin if((acc[W-1]!=max_score[SW-1])?!acc[W-1]:!alu[W-1])max_score<=acc[SW-1:0];acc<=0;state<=CMD;end
 EXP:begin acc<=alu[W-1:0];count<=0;state<=ESHIFT;end
 ESHIFT:begin acc<=$signed(acc)>>>1;if(count==(quant_mode?scale-1:scale-3))state<=quant_mode?QOUT:ELOOK;else count<=count+1'b1;end
 ELOOK:begin dout<=exponent;denom<=denom_next;acc<=0;state<=WOUT;end
 QOUT:begin
 dout<=acc>127?8'd127:acc< -128?8'd128:acc[7:0];state<=QEMIT;
 end
 QEMIT:if(send)begin acc<=0;state<=CMD;end
 WOUT:if(send)state<=CMD;
 SQINIT:begin weighted<=acc;denom<=1;state<=SQSTEP;end
 SQSTEP:begin
 if(alu[W])begin weighted<=alu[AW-1:0];denom<=denom_next;end
 else state<=SQEND;
 end
 SQEND:begin denom<=denom<=1?1:denom>>1;weighted<=0;acc<=0;state<=CMD;end
 DINIT:begin negative<=weighted[AW-1];weighted<=weighted[AW-1]?alu[AW-1:0]:weighted;
 acc<={{(W-ZW){1'b0}},denom}<<7;dout<=0;count<=0;state<=DIV;end
 DIV:begin
 if(alu[W])weighted<=alu[AW-1:0];
 dout<={dout[6:0],alu[W]};acc<=$unsigned(acc)>>1;
 if(count==7)state<=SIGN;
 else count<=count+1'b1;
 end
 SIGN:begin if(negative)dout<=dout[7]?8'd128:-dout;else if(dout[7])dout<=127;state<=OUT;end
 OUT:if(send)begin weighted<=0;state<=CMD;end
 default:state<=CMD;
 endcase
 end
endmodule
module tt_um_extended #(parameter NB=10,DB=6,SERIAL=1)(
 input[7:0]ui_in,output[7:0]uo_out,input[7:0]uio_in,output[7:0]uio_out,output[7:0]uio_oe,input ena,clk,rst_n);
 wire ready,valid,kind;
 attention_extended #(.NB(NB),.DB(DB),.SERIAL(SERIAL)) core(clk,rst_n & ena,uio_in[0],uio_in[1],ui_in,uo_out,ready,valid,kind);
 assign uio_out={3'b000,kind,valid,ready,2'b00};assign uio_oe=8'b11111100;
endmodule
