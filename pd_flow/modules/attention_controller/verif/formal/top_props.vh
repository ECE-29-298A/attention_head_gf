// fv_top (SPEC.md section 2.3 and 7): properties of the TT wrapper project.v around the golden
// controller. run_all.sh inserts `include "top_props.vh" before the endmodule of a COPY of
// snapshot/project.v (read with -formal; the controller and submodules without -formal).
// No assumptions: every pin is free at every step.
`ifdef FORMAL
    reg f_pv = 1'b0;
    always @(posedge clk) f_pv <= 1'b1;
    always @* begin
`ifndef SANITY_TOP
        // fixed pins: RAM chip selects high and driven, IO1..IO3 inputs, SCK and CS# driven
        tp_pins: assert (uio_oe[7:6] == 2'b11 && uio_oe[5:4] == 2'b00 && uio_oe[3] == 1'b1 && uio_oe[2] == 1'b0
                         && uio_oe[0] == 1'b1 && uio_out[7:6] == 2'b11 && uio_out[5:4] == 2'b00
                         && uio_out[2] == 1'b0 && uo_out[7:2] == 6'd0
                         && uio_oe[1] == spi_mosi_oe && uio_out[0] == spi_cs_n && uio_out[3] == spi_sck
                         && uio_out[1] == spi_mosi && uo_out[1] == drdy && uo_out[0] == miso);
`endif
    end
    always @(posedge clk) if (f_pv) begin
`ifndef SANITY_TOP
        // ena = 0 or rst_n = 0 at an edge holds the core in reset: idle, flash released,
        // SCK low, IO0 released, DRDY low in the next clock
        if ($past(!rst_n || !ena)) tp_reset: assert (core_idle && uio_out[0] && !uio_out[3] && !uio_oe[1] && !uo_out[1]);
        // the controller's last/score_shift/cont (config_chain) are held from the accepted start
        // until the core is idle again: this discharges the controller's held-input condition
        if ($past(!core_idle) || $past(core_idle && cs_rise)) tp_held: assert (config_chain == $past(config_chain));
        // start (= out_ready) is a CS# rise; the chain never shifts at a start edge
        if ($past(cs_rise)) tp_noshift: assert (config_chain == $past(config_chain));
`endif
`ifdef SANITY_TOP
        if (1'b1) n_top: assert (config_chain == $past(config_chain));   // wrong: shifts while idle
`endif
    end
`endif
