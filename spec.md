# ELEN90096 SRCNN FPGA 加速项目规格说明

文档状态：**课程功能基线已确认；部署接口与实现阈值待确认**  
版本：1.0  
日期：2026-10-05  
目标平台：Kria KV260 / K26 SOM（Zynq UltraScale+ MPSoC）  
实现环境：Vitis HLS + PYNQ + DMA

> 本文档定义功能、接口、验证和测量规则。课程 Project Overview、Golden starter
> 与 2026-10-05 已提交 Golden Reference 已关闭的功能项按正式契约记录；其余项目
> 仍标记为 **TBD（待确认）**，不得在实现中静默假设。

## 1. 资料优先级与项目边界

若资料之间存在冲突，采用以下优先级：

1. Canvas assignment、rubric、starter code、教师书面澄清；
2. Lecture 08 的 SRCNN 项目说明；
3. Lecture 01 的平台和课程概览；
4. SRCNN 原论文或通用实现，仅用于理解，不能自动视为课程规格。

### 1.1 明确属于项目范围

- 建立功能正确的顺序 C/C++ SRCNN Golden Reference；
- 用 Vitis HLS 实现并优化 SRCNN 推理加速器；
- 将加速器部署至 Kria KV260；
- 通过 PYNQ host 程序与 DMA 完成 PS/PL 数据交换；
- 验证正确性，并报告精度、性能、资源和端到端开销。

### 1.2 除非 Canvas 另有要求，否则不属于当前范围

- 训练或重新训练 SRCNN；
- 改变三层网络结构；
- 自行更换超分辨率算法；
- 实时摄像头、视频编解码或多 batch 推理；
- 为了获得更高分数而改变 Golden Reference 的算法语义。

### 1.3 当前课程级证据

- Canvas Project Overview：确认 bicubic 预处理、三层结构、replicate-edge、Set5 与
  最大化 FPS 的目标；
- 课程 `golden.zip` starter：确认 `H=W=255`、单帧 C-array 接口与 float32 类型；
- 官方 Butterfly/Set14 参考输出：确认提交版 replicate-edge 与 bias-first executable order；
- 已提交归档 `submission/ELEN90096_SRCNN_Golden_Reference_2026-10-05.zip`，SHA-256：
  `28568645138c3f006017b5df763174bf9a5bef2d100dcf16a8ab5968ff85b977`。

## 2. 项目目标与成功定义

项目目标是在保持规定数值正确性的前提下，将三层 SRCNN 推理映射为可综合、可部署、可测量的 FPGA 加速器。

项目成功必须同时满足：

- Golden Reference 对规定测试输入产生正确且可复现的结果；
- HLS C simulation、RTL co-simulation（若课程流程要求）和板上输出均满足同一误差标准；
- Vivado/Vitis implementation 完成 timing closure；
- 设计不超过实际平台可用的 DSP、LUT、FF、BRAM/URAM 和接口资源；
- PYNQ 程序可以稳定完成输入、启动、等待和输出读取；
- 所有性能结论都有输入尺寸、数据类型、时钟、测量边界和重复次数作为上下文。

## 3. 网络功能规格

### 3.1 卷积定义

逻辑卷积采用：

\[
Y[o,h,w] = b_o + \sum_c \sum_i \sum_j
W[o,c,i,j]\,X[c,hS+i-P,wS+j-P]
\]

空间输出尺寸为：

\[
H_{out}=\left\lfloor\frac{H_{in}+2P_h-K_h}{S_h}\right\rfloor+1,
\qquad
W_{out}=\left\lfloor\frac{W_{in}+2P_w-K_w}{S_w}\right\rfloor+1
\]

本项目约定上式为 cross-correlation 形式，即实现时不翻转 kernel。边界外索引不读零，
而是 clamp 到最近的合法行/列（replicate-edge）。课程 Golden 的可执行 binary32 顺序为
`accumulator = bias; accumulator += products; activation(accumulator)`；Conv1/2 在完整累加后
做 ReLU，Conv3 不做激活或 clamp。该顺序已由官方参考数据交叉验证，并与 2026-10-05
提交版本一致。

### 3.2 固定网络结构

课程 Golden starter 固定单帧输入为 `H0=W0=255`。三层均为 stride 1，并通过边缘值扩展
保持空间尺寸不变，因此 `H1=H2=H3=255`、`W1=W2=W3=255`。

各层空间尺寸必须按以下表达式计算并由测试验证：

\[
H_1=\left\lfloor\frac{H_0+2P_1-9}{S_1}\right\rfloor+1,\quad
H_2=\left\lfloor\frac{H_1+2P_2-1}{S_2}\right\rfloor+1,\quad
H_3=\left\lfloor\frac{H_2+2P_3-5}{S_3}\right\rfloor+1
\]

宽度 \(W_1,W_2,W_3\) 使用相同公式替换 \(H\)；若水平和垂直参数不同，则分别使用 \(P_h/P_w\) 与 \(S_h/S_w\)。

| 层 | 逻辑输入形状 | Kernel | 逻辑输出形状 | 激活 | 权重数 | Bias 数 | 每个输出空间位置的 MAC 数 |
|---|---|---|---|---|---:|---:|---:|
| Conv1 | `[1, H0, W0]` | `64 × 1 × 9 × 9` | `[64, H1, W1]` | ReLU | 5,184 | 64 | 5,184 |
| Conv2 | `[64, H1, W1]` | `32 × 64 × 1 × 1` | `[32, H2, W2]` | ReLU | 2,048 | 32 | 2,048 |
| Conv3 | `[32, H2, W2]` | `1 × 32 × 5 × 5` | `[1, H3, W3]` | 无 | 800 | 1 | 800 |
| 合计 | — | — | — | — | 8,032 | 97 | 8,032* |

\* 课程正式尺寸与 replicate-edge same padding 下，三层对相同的 65,025 个空间位置求值：

\[
MAC_{total}=\sum_l H_l W_l C_{out,l} C_{in,l} K_{h,l} K_{w,l}
\]

对此网络可展开为：

\[
MAC_{total}=5184H_1W_1+2048H_2W_2+800H_3W_3
\]

在 `255×255` 上，Conv1、Conv2、Conv3 分别执行 337,089,600、133,171,200、
52,020,000 个 MAC，总计 **522,280,800 MAC/frame**。

算法语义为 `bias + 所有 MAC → activation`；为复现课程 binary32 参考输出，可执行顺序
固定为 `accumulator=bias → 按 OIHW 顺序累加 MAC → ReLU`。Conv3 不执行 ReLU、clamp
或其他激活；图像格式转换产生的 clamp/round 属于后处理并单独定义。

### 3.3 层参数状态

| 项目 | Conv1 | Conv2 | Conv3 | 状态 |
|---|---:|---:|---:|---|
| Kernel | 9×9 | 1×1 | 5×5 | 已确认 |
| 输入/输出通道 | 1→64 | 64→32 | 32→1 | 已确认 |
| Activation | ReLU | ReLU | None | 已确认 |
| Stride `(Sh, Sw)` | 1 | 1 | 1 | 已由固定同尺寸输入/输出契约确认 |
| Padding radius | 4 | 0 | 2 | replicate-edge；不是 zero padding |
| Dilation | 1 | 1 | 1 | 已确认 |

内部 P1 保留的 valid/zero-pad 小尺寸向量只能作为索引回归，不属于课程部署语义，
不得用于 HLS/板级正式正确性或性能结论。

## 4. 输入输出数据契约

课程算法输入是已经 bicubic 放大到目标空间尺寸的单通道 feature map。颜色转换如何在
应用侧产生该通道仍待确认，但不改变 HLS kernel 的单通道 tensor 契约。

| 项目 | 当前规格 | 确认来源/备注 |
|---|---|---|
| Batch size | `N=1` | 单图 SRCNN；starter 无 batch 维 |
| 输入通道数 | 1 | HLS kernel 接收单通道；灰度或 Y 的 host 颜色转换仍 TBD |
| 输入高度、宽度 | 固定 `255×255` | 课程 Golden starter 的 `H/W` |
| 输入 tensor 逻辑布局 | `[1][255][255]`（CHW/C-array 顺序） | Golden 函数签名；DMA beat packing 仍 TBD |
| Golden 输入元素类型 | `float32` | starter `ftmap_t=float` |
| Golden 输入数值范围 | `[0,1]` | 官方测试工具把 8-bit 像素归一化后送入 Golden |
| 色彩空间 | 单通道；具体为灰度还是 Y 仍 TBD | 不在 HLS core 内静默执行 RGB/YCbCr 转换 |
| 上采样预处理 | CNN 前先做 bicubic；kernel 输入已是 `255×255` 目标尺寸 | Canvas Project Overview；是否计入端到端时间必须显式说明 |
| 输出 tensor 逻辑布局 | `[1][255][255]` | 与 Golden 函数签名一致；DMA beat packing 仍 TBD |
| Golden 输出元素类型 | `float32` | HLS deployment dtype 由 P2.2 冻结 |
| 输出后处理 | TBD：crop、round、saturate、clamp、反归一化 | 不得偷偷并入 Conv3 |
| 部署尺寸 | 固定 `255×255` | 小尺寸仅用于内部测试，不作为部署接口 |
| DMA 数据宽度和对齐 | TBD | 由 overlay、AXI 接口和 PYNQ buffer 要求确定 |

### 4.1 权重和 bias 格式

逻辑权重统一定义为 OIHW：

```text
W[output_channel][input_channel][kernel_row][kernel_col]
bias[output_channel]
```

若权重文件使用连续 OIHW 存储，则逻辑扁平偏移定义为：

```text
weight_offset = (((o * C_in + c) * K_h + kernel_row) * K_w + kernel_col)
bias_offset   = o
```

如果课程提供的文件采用其他排列，loader 必须执行显式转换，HLS 内部优化后的 banking/packing 也必须能够追溯回上述逻辑索引。

| 参数 | 逻辑形状 | 元素数量 | 外部文件格式 | HLS 内部格式 |
|---|---|---:|---|---|
| Conv1 weights | `[64,1,9,9]` | 5,184 | TBD | 可为并行访问重排/分区后的副本，但必须可逆追溯至 OIHW |
| Conv1 bias | `[64]` | 64 | TBD | TBD |
| Conv2 weights | `[32,64,1,1]` | 2,048 | TBD | 同上 |
| Conv2 bias | `[32]` | 32 | TBD | TBD |
| Conv3 weights | `[1,32,5,5]` | 800 | TBD | 同上 |
| Conv3 bias | `[1]` | 1 | TBD | TBD |

进入 P2.2/P3 前仍需记录或确认：

- 已用于课程 Golden 的官方权重文件名、模型版本及 checksum；
- 文本、二进制、NumPy 或其他序列化格式；
- 外部排列是否与逻辑 OIHW 相同；
- 权重是否编译进 bitstream，或由 PS 在运行时加载；
- bias 的数据类型、scale，以及定点量化时是否与累加器处于同一 scale；
- kernel row/column 是否需要翻转。

## 5. 数值精度规格

### 5.1 推荐验证路径

1. Golden Reference 使用课程 starter 规定的 `float32`；
2. 无优化 HLS 先保持与 Golden 相同的浮点语义；
3. 浮点 HLS 正确后，再独立评估定点化；
4. 固定输入、权重、预处理和网络语义，只改变数值格式；
5. 记录每层输入、累加器和输出的观测动态范围。

### 5.2 定点规格必须显式记录

- 输入、权重、bias、乘积、累加器、中间 feature map、最终输出各自的总位宽和整数位宽；
- signed/unsigned；
- rounding mode；
- overflow/saturation mode；
- 不同层之间是否重新量化；
- 量化 scale 和 zero-point（如适用）；
- 最坏情况累加增长与实测动态范围；
- 饱和事件计数。

### 5.3 误差标准

课程 rubric 的容差为最高优先级，目前为 **TBD**。在确认前可使用下列内部工程门禁，但不得把它们冒充课程要求：

- 浮点实现：逐层和最终输出同时报告 `max_abs_error`、`MAE`、`RMSE`、`relative_L2`、`max_relative_error` 和超阈值元素数；元素级通过条件为 `abs(dut-ref) <= atol + rtol*abs(ref)`；建议初始门禁 `atol=1e-5, rtol=1e-4`，若累加顺序导致合理差异则必须基于证据调整；
- 定点实现：除上述数值误差外，还报告 FPGA 输出相对 float Golden 的 PSNR，必要时报告 SSIM；最终阈值 TBD；
- 图像质量：若提供 HR ground truth，SRCNN 输出对 HR 的 PSNR/SSIM 与“FPGA 对 Golden 的实现误差”必须分开，不能混为一个指标；
- 容差必须在查看待测结果前冻结，禁止为了让失败结果通过而事后放宽。

## 6. Golden Reference 规格

Golden Reference 是顺序、清晰、可重复的 C/C++ 算法真值，不用于展示性能。
课程提交版本已于 2026-10-05 作为 ZIP 提交，包含 `conv1.cpp`、`srcnn.cpp`、`srcnn.h`；
该提交版本冻结，不在 P2/P3 中直接修改。

### 6.1 必需能力

- 对每层独立运行并导出中间 tensor；
- 执行完整三层 SRCNN；
- 检查输入、权重和 bias 的形状与元素数量；
- 明确应用 bias 和 ReLU 的位置；
- 使用固定随机种子；
- 可保存输入、每层输出和最终输出，供 HLS testbench 与板级测试复用；
- 对非法尺寸、短文件或布局不匹配给出明确错误；
- 记录模型文件 checksum 和运行配置。

### 6.2 测试用例清单

| 测试 | 目的 | 通过标准 |
|---|---|---|
| 全零输入、全零权重、全零 bias | 验证初始化、无未定义值 | 所有层输出为零 |
| 全零输入、非零 bias | 验证 bias 只加一次及 ReLU 顺序 | 每通道结果等于相应 bias 经激活后的值 |
| 全一输入、全一权重 | 验证 MAC 数、通道归约和边界 | 内部位置与手算结果一致；边界按已确认 padding 规则一致 |
| 单个非零像素（impulse） | 验证 kernel 方向、padding 和空间索引 | 非零响应的位置和数值与手算一致 |
| 单个非零权重 | 验证 OIHW、通道映射和 kernel row/col | 仅预期通道/位置产生响应 |
| 含正负值的输入/权重/bias | 验证 ReLU 和 signed arithmetic | Conv1/2 负值在 bias 后被置零；Conv3 负值保留 |
| 可手算的小尺寸单层用例 | 提供独立于同一实现代码的 oracle | 每个输出元素逐项一致 |
| 固定种子随机测试 | 覆盖普通数据和累加顺序 | 逐层及端到端满足冻结容差 |
| 边、角和最小合法尺寸 | 验证所有边界分支 | 无越界，形状及数值正确 |
| 非 tile 整除尺寸（进入 tiling 后） | 验证尾块和 halo | 与未分块 Golden 一致，无重复或遗漏像素 |
| 代表性真实图像与正式权重 | 验证真实工作负载 | 数值误差和图像质量满足冻结标准 |

13×13 valid 的手算用例仍保留为内部索引/oracle 回归，但课程正式路径固定为
255×255、stride 1、replicate-edge same padding；正式 HLS 和板级比较必须采用后者。

### 6.3 验证层级

同一组测试向量应依次用于：

```text
独立手算/外部 oracle
        ↓
Golden Reference
        ↓
HLS C simulation
        ↓
RTL co-simulation（若采用）
        ↓
KV260 板上输出
```

任何一级失败都应先定位到具体层、通道和坐标，不应直接进入下一优化阶段。

## 7. 硬件平台与资源约束

### 7.1 K26 PL 物理上限

以下为 AMD K26 SOM Data Sheet DS987 的器件总资源，不等于本项目 overlay 的可用资源：

| 资源 | 器件总量 | 项目使用规则 |
|---|---:|---|
| CLB LUT | 117,120 | synthesis 与 implementation 均不得超出；必须报告绝对数与百分比 |
| CLB FF | 234,240 | 同上 |
| DSP slice | 1,248 | 完全展开 Conv1/Conv2 会超出，必须部分复用/展开 |
| 36 Kb Block RAM | 144 块（约 5.1 Mb） | 平台和 AXI/DMA 会占用一部分；以实际 utilization report 的 available 数为准 |
| UltraRAM | 64 块（每块 288 Kb） | 是否允许/是否由 HLS 推断为 TBD |
| Distributed RAM | 约 3.5 Mb | 计入 LUT 资源和实现压力 |
| 外部 DDR4 | 4 GB、64-bit、2400 Mb/s | 理论峰值约 19.2 GB/s；不能当作可实现 DMA 带宽 |

参考：[AMD K26 SOM DS987 — Programmable Logic](https://docs.amd.com/r/en-US/ds987-k26-som/Programmable-Logic) 和 [Functional Overview](https://docs.amd.com/r/en-US/ds987-k26-som/Functional-Overview-and-Block-Diagram)。

### 7.2 工程资源预算

物理总量不是安全预算。项目开始实现前必须从实际 KV260 platform/overlay 报告中确认：

- 平台静态逻辑、AXI interconnect、DMA 和控制接口已占用多少资源；
- HLS kernel 可使用的 DSP、LUT、FF、BRAM、URAM 上限；
- 目标 clock period/frequency；
- 是否要求保留布线和 timing 裕量。

初始工程门禁建议把 kernel + 必要互连控制在实际可用资源的 80%–85% 内，但该比例只是风险控制建议，不是课程要求。若无法 timing closure，即使资源低于 100% 也视为失败。

### 7.3 DDR 和 DMA 带宽假设

- 19.2 GB/s 仅是 `64 bit × 2400 MT/s` 的 DDR 接口理论峰值；
- 项目性能模型不得假设持续达到理论峰值；
- 实际有效带宽 `BW_effective` 为 TBD，必须由目标 overlay 上的 PYNQ/DMA microbenchmark 测量；
- AXI 端口自身的理论上限为 `BW_AXI = (W_AXI/8) × f_AXI`，其中端口位宽 `W_AXI` 和频率 `f_AXI` 均从实际 platform 获取；
- 设计可用带宽上限应按 `min(DDR_peak, BW_AXI, measured_sustainable_bandwidth)` 建模；
- 至少测量 PS→PL、PL→PS 和双向/完整 round-trip；
- 记录 buffer size、AXI width、burst、对齐、cache 同步、重复次数及并发争用；
- 报告有效带宽利用率 `BW_effective / 19.2 GB/s`，但不得把低利用率简单归因于 DDR 本体。

### 7.4 初始硬件结构约束

- Conv1 和 Conv3 应评估 line buffer/sliding window，避免从 DDR 重复读取相同邻域；
- Conv2 为 1×1、64→32 的通道归约，重点评估通道并行度与存储端口；
- 大型中间 feature map 不应默认整体放入 BRAM，必须比较 DDR 中间存储、tiling 和跨层 streaming；
- 在 float32 下，Conv1/Conv2 完整中间 feature map 分别约为 15.9 MiB/7.9 MiB，
  明显超过 K26 的 BRAM 总容量；正式设计必须避免将两者整体映射到 BRAM；
- `UNROLL` 因子必须与 `ARRAY_PARTITION` 或实际存储端口匹配；
- `DATAFLOW` 中每个 stage 的生产/消费率、FIFO 宽度和深度必须有依据；
- 每次只引入一类主要优化，并保留可回退、可测量的上一版本。

## 8. PS/PL 与 DMA 接口规格

当前目标边界为：

```text
PYNQ host / PS memory
        ⇅ DMA
AXI interface
        ⇅
SRCNN HLS accelerator in PL
```

下列接口项目为 TBD：

- AXI4-Stream 还是 AXI4 memory-mapped 主接口；
- 控制接口寄存器及启动/完成协议；
- stream 数据宽度、每 beat 打包的元素数量、`TKEEP/TLAST` 规则；
- 输入、输出、权重是单独 DMA transaction 还是权重常驻 PL；
- 固定 `255×255` 帧在 DMA 中的长度、beat packing 和 frame boundary；
- buffer 字节数、alignment 和 cache flush/invalidate 责任；
- 多帧连续执行时内部静态状态的 reset 规则；
- timeout 与 DMA hang 的诊断和恢复方式。

## 9. Final Report 量化指标

所有指标必须同时注明：实现版本、输入尺寸、数据类型、工具版本、目标/实际时钟、测试数据集、重复次数、统计方式和测量边界。

### 9.1 正确性与图像质量

| 指标 | 比较对象 | 范围 |
|---|---|---|
| 最大绝对误差 | HLS/板上输出 vs Golden | 每层、最终输出 |
| 最大相对误差 | 同上 | 每层、最终输出 |
| MAE / RMSE | 同上 | 每层、最终输出 |
| Relative L2 error | 同上 | 每层、最终输出 |
| 不匹配元素数量/比例 | 同上 | 适用于 bit-exact 或给定容差 |
| PSNR | FPGA 输出 vs float Golden | 实现误差 |
| PSNR/SSIM | SRCNN 输出 vs HR ground truth | 算法图像质量；若课程提供 HR 数据 |
| 饱和/溢出事件数 | 定点实现内部 | 各层和累加器 |

### 9.2 Kernel-only 性能

Kernel-only 的边界必须排除 host 预处理、PYNQ buffer 分配和 PS↔PL DMA；具体计时方法需与 overlay 支持能力一致。优先使用硬件 cycle counter、性能监视器或严格包围 kernel start/done 的计时。若 PYNQ `transfer/wait` 同时覆盖 DMA 与 streaming kernel，只能称为 `DMA + kernel` 或 device-path latency，不能标为 kernel-only。

- HLS 估计 latency：cycles，以及 min/max/average（如报告提供）；
- 板上 kernel execution time：ms/frame；
- steady-state initiation interval 和 pipeline depth；
- throughput：frames/s、pixels/s；
- MAC throughput：MAC/s；若使用 GOPS，必须说明 `1 MAC = 1 op` 还是 `2 ops`；
- achieved clock frequency 和 timing slack；
- 相对无优化 HLS、上一优化版本的 speedup；
- 相对 CPU baseline 的 kernel-only speedup，前提是双方计算边界相同。

### 9.3 End-to-end 性能

End-to-end 至少包含：

```text
已准备好的输入 buffer
→ host/PS 预处理（若属于系统路径）
→ PS→PL DMA
→ accelerator
→ PL→PS DMA
→ 必要的后处理
→ 可由应用读取的输出
```

应报告：

- PS→PL DMA 时间；
- kernel 时间；
- PL→PS DMA 时间；
- host 预处理和后处理时间；
- 总 latency（ms/frame）；
- 稳态 throughput（frames/s、pixels/s）；
- end-to-end speedup；
- DMA/传输占总时间比例；
- 单帧与连续多帧结果；
- warm-up 次数、正式重复次数 `N`、mean、median、standard deviation，必要时 p95。

严禁用 kernel-only FPGA 时间与包含文件 I/O/预处理的 CPU 时间直接计算 speedup。

### 9.4 资源、带宽与功耗

- LUT、FF、DSP、BRAM、URAM：绝对数量和平台可用量百分比；
- post-synthesis 与 post-implementation 数据来源必须注明，最终结论优先使用 post-implementation；
- WNS/TNS 或等价 timing closure 信息；
- 权重、line buffer、FIFO、中间 tile 各自的片上存储开销；
- 每帧理论和实测 DDR bytes；
- PS→PL、PL→PS 有效带宽及理论峰值利用率；
- 算术强度 `MAC / DDR byte`；
- 若可可靠获取，报告功耗、能量/帧或能效；若不可获取，明确写为“未测量”，不得编造。

### 9.5 优化消融表

至少保留并比较：

1. 无优化 HLS；
2. 数值格式优化；
3. `PIPELINE`；
4. `UNROLL + ARRAY_PARTITION`；
5. line buffer/tiling；
6. `DATAFLOW`；
7. 最终板级版本。

每行至少包含：正确性结果、clock、latency、throughput、LUT/FF/DSP/BRAM/URAM 和备注。若某优化失败，也应记录失败原因，而不是删除实验。

## 10. 里程碑交付规格

| 里程碑 | 最低交付内容 | 完成门禁 |
|---|---|---|
| Golden Reference | 顺序 C/C++；`conv1.cpp`、`srcnn.cpp` 及所需 header | 2026-10-05 已提交；官方 Butterfly Conv1 MSE `3.23504e-15`，端到端 MSE `2.90284e-14` |
| Status Update | 架构图、数据布局、精度选择、优化计划、当前正确性/性能/资源结果、风险和剩余工作 | 至少有可信的 HLS baseline；所有数字注明版本和测量边界 |
| Final Report | 完整报告、HLS 代码、PYNQ host 代码、bitstream/overlay 相关产物（若 rubric 要求）、复现说明和原始结果 | 板级正确、稳定、timing closure；量化指标完整且可追溯 |

## 11. 待确认项总表

### 11.1 已关闭的课程功能项

- [x] 固定单帧输入与输出：`1×255×255`；
- [x] CNN 输入已先经 bicubic 放大；
- [x] 三层 stride 1，Conv1/Conv3 使用 replicate-edge，Conv2 无空间 padding；
- [x] Golden tensor/weights/bias 的 C-array 逻辑布局为 CHW/OIHW/O；
- [x] Golden dtype 为 float32，官方测试输入归一化到 `[0,1]`；
- [x] executable accumulation order 为 bias-first；Conv1/2 ReLU，Conv3 无激活/clamp；
- [x] 正式课程 weights 与参考输出已用于提交前交叉验证；
- [x] Golden Reference 已于 2026-10-05 提交。

仍待确认但不再阻塞 Golden/HLS core 功能：

- [ ] 单通道在完整应用中是灰度还是 RGB→YCbCr 的 Y；
- [ ] HR ground truth 的最终裁剪、保存和图像质量评价细节；
- [ ] HLS/板级定点实现相对 float Golden 的正式阈值。

### 11.2 阻塞 HLS/板级接口

- [ ] Vitis/Vivado/PYNQ 版本及目标 platform；
- [ ] kernel 顶层接口类型和 DMA 数据宽度；
- [ ] 目标 clock；
- [ ] 平台静态逻辑占用和 kernel 实际资源预算；
- [ ] 权重常驻还是运行时加载；
- [ ] 允许使用 float、`ap_fixed`、URAM 和多 compute unit 的范围；
- [ ] DMA buffer alignment、cache 管理和 `TLAST` 规则；
- [ ] 板上有效 DDR/DMA 带宽测量值。

### 11.3 阻塞最终报告

- [ ] CPU baseline 的平台、线程数、编译优化级别和计时边界；
- [ ] 是否要求 RTL co-simulation、power 或能效；
- [ ] 图像质量指标及阈值；
- [ ] 正式 benchmark 图片尺寸、数量和重复次数；
- [ ] Canvas rubric 的报告格式、页数和提交文件清单。

## 12. 变更控制

- 本规格确认后，任何影响算法语义、数据布局、精度或计时边界的改变都必须更新本文档；
- 每个实验版本必须记录配置、git commit（若项目使用 Git）、随机种子、权重 checksum 和工具版本；
- 正确性阈值一旦冻结，不得为了使某个候选设计通过而事后调整；
- 课程功能基线已经确认，允许进入 P2.2 定点误差验证；P2.3 的并行度、接口和资源
  决策仍须等待首轮 csynth/平台报告。

### 12.1 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 0.1 | 2026-09-10 | 建立草案，未知课程项目显式标为 TBD |
| 1.0 | 2026-10-05 | 根据 Canvas Project Overview、Golden starter、官方参考数据和已提交 Golden，冻结 `255×255`、bicubic 输入、replicate-edge、float32、CHW/OIHW 与 bias-first 可执行契约；部署接口/阈值继续保持 TBD |
