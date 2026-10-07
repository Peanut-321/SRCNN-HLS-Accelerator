# SRCNN workload analysis — official 255×255 frame

Date: 2026-10-06  
Scope: algorithmic counts only; **not measured FPGA performance**

Assumptions follow the frozen course contract: batch 1, stride 1,
replicate-edge same padding, CHW activations, OIHW weights. All three layers
therefore retain 255×255 spatial dimensions.

## Exact operation and parameter counts

| Layer | Output elements | MACs/output | MACs/frame | Weights | Biases |
|---|---:|---:|---:|---:|---:|
| Conv1, 9×9, 1→64 | 4,161,600 | 81 | 337,089,600 | 5,184 | 64 |
| Conv2, 1×1, 64→32 | 2,080,800 | 64 | 133,171,200 | 2,048 | 32 |
| Conv3, 5×5, 32→1 | 65,025 | 800 | 52,020,000 | 800 | 1 |
| **Total** | 6,307,425 | — | **522,280,800** | **8,032** | **97** |

One MAC is counted as one multiply-accumulate operation. If a report uses the
common convention of two scalar operations per MAC, this is 1,044,561,600
multiply/add operations per frame. The convention must be stated beside every
GOPS figure.

Work distribution by MAC count:

- Conv1: 64.54%
- Conv2: 25.50%
- Conv3: 9.96%

Conv1 is therefore the primary compute target, while Conv3 has the deepest
reduction (800 terms) and the strongest accumulator/precision pressure.

## Storage and traffic implications

At 32 bits per value:

| Tensor/data | Elements | Bytes | MiB |
|---|---:|---:|---:|
| Input | 65,025 | 260,100 | 0.2481 |
| Conv1 activation | 4,161,600 | 16,646,400 | 15.8752 |
| Conv2 activation | 2,080,800 | 8,323,200 | 7.9376 |
| Output | 65,025 | 260,100 | 0.2481 |
| All weights + biases | 8,129 | 32,516 | 0.0310 |

The parameters are small enough to keep on chip in principle. The intermediate
feature maps are not: Conv1 plus Conv2 alone occupy about 23.81 MiB at 32 bits.
They must not be described as full-frame BRAM buffers without implementation
evidence.

Two idealized lower-level traffic cases show the value of fusion:

- If both intermediates spill once to DDR and are read once by the next layer,
  the frame moves at least **50,491,916 bytes**, including one read of all
  parameters. This is only about **10.34 MAC/byte** before protocol overhead.
- If all three layers are fused and streamed so only the network input,
  parameters and final output cross DDR, the lower bound is **552,716 bytes**,
  or about **945 MAC/byte**. Real traffic will be higher because of burst,
  alignment, control and any repeated parameter loads.

These are analytical bounds, not measured AXI bandwidth or runtime.

## Sliding-window state

Ignoring window registers, FIFOs, banking duplication and implementation
overhead, a K-row streaming architecture needs approximately `K-1` previous
rows per spatial convolution:

- Conv1: `8 × 255 × 1 = 2,040` values
- Conv2: no row buffer for 1×1
- Conv3: `4 × 255 × 32 = 32,640` values
- Total line-buffer payload: **34,680 values = 138,720 bytes at 32 bits**

This payload is far smaller than full intermediate frames, but HLS array
partitioning can replicate memories and increase BRAM/LUTRAM usage. Only the
post-implementation utilization report may be quoted as the actual resource
cost.

## Hardware-acceleration argument

The workload is amenable to FPGA acceleration because its loop bounds and
memory access patterns are static, each output is a regular dot product, and
there is abundant spatial/channel MAC parallelism. Weights are reused across
all 65,025 pixel positions and neighboring convolution windows reuse input
rows. The main constraints are therefore not control complexity but:

1. supplying enough operands per cycle without array-port conflicts;
2. balancing Conv1/Conv2/Conv3 rates under dataflow;
3. retaining sufficient accumulator precision, especially for Conv3;
4. avoiding DDR materialization of the large intermediate maps;
5. fitting line-buffer banking and MAC parallelism inside the overlay's actual
   DSP/BRAM/LUT budget.

Any claimed II, latency, throughput, resource usage or bandwidth remains
`NOT MEASURED` until Vitis/Vivado or board evidence exists.
