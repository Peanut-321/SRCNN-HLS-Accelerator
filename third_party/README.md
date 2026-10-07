# Third-party host-simulation dependency

`HLS_arbitrary_Precision_Types/` is the Xilinx open-source host-simulation
implementation of `ap_int`/`ap_fixed`, checked out at commit:

```text
200a9aecaadf471592558540dc5a88256cbf880f
```

It is used only for native Mac/Linux fixed-point tests. Vitis HLS synthesis must
use the `ap_fixed.h` supplied by the selected Vitis installation. The upstream
repository is <https://github.com/Xilinx/HLS_arbitrary_Precision_Types>.
