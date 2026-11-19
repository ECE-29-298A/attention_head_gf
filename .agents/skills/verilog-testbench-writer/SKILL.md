---
name: verilog-testbench-writer
description: Specialized skill for authoring robust, self-checking Verilog/SystemVerilog testbenches. Enforces explicit timescales, parametric clocks, self-checking assertions ($fatal), edge-case stimulus generation, and watchdog timeout guards to prevent infinite simulator hangs.
---

# Verilog Testbench Writer Skill

This skill guides coding agents in generating production-grade, self-checking testbenches for Verilog and SystemVerilog modules. Visual inspection of waveforms is unacceptable for automated agents; testbenches MUST programmatically verify expected outputs against inputs.

---

## 1. Testbench Architecture Requirements

Every generated testbench MUST adhere to this 5-part architecture:

1. **Explicit Timescale**:
   Always specify `` `timescale 1ns/1ps `` at the very top of the file to guarantee uniform timing semantics across simulator tools (`iverilog`, `verilator`, ModelSim).

2. **Parametric Clock Generation**:
   Define clock periods via parameters (`localparam CLK_PERIOD = 10;`) so frequencies can be adjusted globally.

3. **Deterministic Reset Sequence**:
   Assert reset for at least 2 full clock cycles before releasing it on a negative clock edge to prevent setup/hold race conditions with the DUT clock.

4. **Self-Checking Assertions (`$fatal` on Mismatch)**:
   - Check every output against the known golden model.
   - Use `$display("PASS: ...")` for milestone verification.
   - On error, print informative details (expected vs. actual, simulation time) and call `$fatal(1, "Detailed error message")`.

5. **Watchdog Timeout Guard**:
   Always include a watchdog process that terminates the simulation if the DUT hangs or fails to reach its completion state within a bounded number of cycles.

6. **Clean Simulator Exit**:
   Conclude successful runs with `$display("ALL TESTS PASSED")` followed by `$finish(0)`.

---

## 2. Standard Self-Checking Testbench Template

```verilog
`timescale 1ns/1ps

module my_module_tb;
    // 1. Clock and Timing Parameters
    localparam CLK_PERIOD = 10; // 100 MHz
    localparam TIMEOUT_CYCLES = 1000;

    // 2. DUT Signals
    reg        clk;
    reg        rst_n;
    reg        enable;
    reg  [7:0] in_data;
    wire [7:0] out_data;
    wire       ready;

    // 3. DUT Instantiation
    my_module dut (
        .clk      (clk),
        .rst_n    (rst_n),
        .enable   (enable),
        .in_data  (in_data),
        .out_data (out_data),
        .ready    (ready)
    );

    // 4. Parametric Clock Generation
    initial clk = 0;
    always #(CLK_PERIOD / 2) clk = ~clk;

    // 5. Watchdog Timeout Process (Prevents Agent Hangs)
    initial begin
        #(TIMEOUT_CYCLES * CLK_PERIOD);
        $fatal(1, "WATCHDOG_TIMEOUT: Simulation exceeded maximum allowed cycles (%0d)", TIMEOUT_CYCLES);
    end

    // 6. Verification Task Helper
    task check_output(input [7:0] expected, input [7:0] actual, input [127:0] test_name);
        begin
            if (expected !== actual) begin
                $fatal(1, "FAIL [%s] at %0t ps: Expected %h, Got %h", test_name, $time, expected, actual);
            end else begin
                $display("PASS [%s] at %0t ps: Output match (%h)", test_name, $time, actual);
            end
        end
    endtask

    // 7. Main Stimulus Sequence
    initial begin
        // Signal Initialization
        rst_n   = 0;
        enable  = 0;
        in_data = 8'h00;

        // Reset Pulse (2.5 clock cycles)
        #(CLK_PERIOD * 2.5);
        rst_n = 1;
        $display("[INFO] Reset deasserted at %0t ps", $time);

        // Test Case 1: Initial state check
        @(posedge clk);
        check_output(8'h00, out_data, "Initial Reset State");

        // Test Case 2: Apply stimulus
        @(posedge clk);
        enable  = 1;
        in_data = 8'h42;

        @(posedge clk);
        enable  = 0;

        // Wait for DUT ready
        wait(ready == 1'b1);
        check_output(8'h42, out_data, "Data Processing Test");

        // All tests completed successfully
        #(CLK_PERIOD * 5);
        $display("=================================================");
        $display("ALL TESTS PASSED: DUT verified successfully.");
        $display("=================================================");
        $finish(0);
    end
endmodule
```

---

## 3. Checklist for Generated Testbenches
- [ ] Is `` `timescale `` present?
- [ ] Is clock generated cleanly using a parameter?
- [ ] Is reset held active across multiple clock edges?
- [ ] Does it use self-checking assertions rather than manual waveform inspection?
- [ ] Does it call `$fatal` on assertion failure?
- [ ] Is there a watchdog timeout preventing infinite execution?
- [ ] Does it finish cleanly with `$finish(0)`?
