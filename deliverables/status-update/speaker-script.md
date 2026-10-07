# ELEN90096 SRCNN Status Update 讲稿

目标时长：9分30秒至10分钟。方括号中的成员名需要替换。

## Slide 1 — 标题（[成员A]，约30秒）

大家好，我们的项目是在 Kria KV260 上用 Vitis HLS 加速 SRCNN 图像超分辨率推理，
PS 端使用 PYNQ 和 AXI DMA。今天主要汇报固定算法的计算特征、我们的硬件方案、已经
完成的正确性和定点验证，以及从现在到最终报告的关键路径。

## Slide 2 — 算法结构（[成员A]，约1分10秒）

网络结构由课程固定，不能修改。输入是一张已经经过 bicubic 上采样的 255×255 单通道
图像。Conv1 使用 64 个 9×9 卷积核并接 ReLU；Conv2 用 1×1 卷积把 64 通道降到
32 通道并接 ReLU；Conv3 用 5×5 卷积恢复成单通道，而且没有 ReLU 或 clamp。

三层都使用 stride 1，Conv1 和 Conv3 采用 replicate-edge padding，所以空间尺寸始终
是 255×255。我们的实现采用 cross-correlation，不翻转卷积核；激活按 CHW 排列，
权重按 OIHW 排列。为了与课程参考数据逐位一致，可执行浮点顺序采用 bias-first，之后
完成 MAC，最后在 Conv1 和 Conv2 上执行 ReLU。

## Slide 3 — 计算负载（[成员B]，约1分15秒）

我们按正式尺寸计算得到每帧一共需要 522,280,800 次 MAC。Conv1 占 64.54%，所以它是
主要计算瓶颈；Conv3 虽然总 MAC 较少，但每个输出要归约 800 项，因此对 accumulator
位宽最敏感。

模型本身只有 8,129 个权重和 bias 参数，适合保存在片上。真正的内存压力来自中间
特征图：Conv1 和 Conv2 在 32 位数据下合计约 23.81 MiB。如果两张中间图都落到 DDR，
理论最低数据流量约为 50.49 MB/帧；如果三层融合，只让网络输入和最终输出跨 DDR，
理论算术强度可由约 10.34 提高到约 945 MAC/byte。这说明层间 streaming 对本项目很重要。

## Slide 4 — 目标硬件结构（[成员B]，约1分30秒）

目标数据路径从 PYNQ buffer 经 AXI DMA 进入 PL。Conv1 使用 8 行 line buffer，Conv2
直接做 1×1 通道归约，Conv3 使用 4 行乘 32 通道的 line buffer，最后通过 AXI Stream
输出，并正确产生 TLAST。

我们把算术层和结构层分开：位宽、舍入和饱和规则由集中配置决定；loop order、端口、
partition 和展开度属于结构层。第一次 csynth 后，我们会先看 schedule、dependency 和
memory-port report，再决定展开因子，避免仅凭 RTL 经验猜 HLS 的 II。

图中的结构是计划方案，不是已经综合的硬件。目前 II、clock、DSP、BRAM 和 LUT 都没有
测量，我们没有用估算值替代工具报告。

## Slide 5 — Golden Reference（[成员C]，约1分20秒）

Golden Reference 已于 10 月 5 日提交并冻结。C++ 实现通过 14 个单元测试，覆盖手算
用例、impulse、稀疏 OIHW、正负输入、ReLU、边角和最小尺寸等情况。

为了避免实现和参考共享同一个错误，我们另外写了纯 Python oracle，直接按课程卷积
公式计算，不复用 C++ 的索引和布局代码。所有 tensor 文件都有 FNV-1a checksum，
loader 会拒绝形状、布局、短读和多读错误。

浮点方面，我们锁定 `-ffp-contract=off` 并拒绝 fast-math。在当前工具链上 O0 与 O3
逐位一致。后续 HLS 开发没有改动已提交 ZIP，它的 SHA256 仍保持不变。

## Slide 6 — Mac 定点验证（[成员C]，约1分20秒）

由于 Mac 不能运行 Vitis，我们先完成可以独立验证的算术层。当前安全基线是 Q24.8，
accumulator 位宽根据每层的 MAC 数和声明范围自动推导，而不是手填三个数字。

五套冻结向量的 fixed-vs-float 回归全部通过，输入量化和三层 narrowing 的 saturation
事件全部为零。图中显示每层最差 relative-L2，Conv1 为 0.28%，Conv2 为 0.35%，Conv3
为 0.62%。这些结果证明 harness 和定点数据路径工作正常。

但这五套数据使用随机权重，输出幅值可能超过 300。因此 R=1 的 PSNR 只能作为回归字段，
不能解释为图像质量。恢复正式权重和课程图像后，我们才会冻结部署位宽与正式 PSNR/SSIM
门槛。

## Slide 7 — 当前状态（[成员A]，约1分10秒）

P1 和 P2.1 已完成，P2.2 完成了随机向量的 P2.2a，正式资产下的 P2.2b 还没有完成。
最大的外部风险仍是 P0：我们需要 x86 Vitis 完成 csynth 和 export IP，再使用 Vivado
生成 bitstream，并争取 KV260 板卡时间完成 DMA 测试。

所以目前所有 latency、II、throughput、资源、clock 和 timing closure 都明确标为
未测量。这个边界很重要，因为 Mac host runtime 不能代表 FPGA 性能，HLS estimated
clock 也不能代表 post-implementation timing。

## Slide 8 — 剩余工作（[成员B]，约45秒）

短期先贯通 dummy kernel 工具链，并恢复正式模型资产完成 P2.2b。随后直接实现目标
line-buffer、PIPELINE、适度 UNROLL 和 DATAFLOW 结构，再根据报告调整。得到 bitstream
后，我们会分别测 kernel-only 和 end-to-end，并记录 warm-up、重复次数和统计量。

最终报告至少保留三行可复核消融，并同时报告资源、timing、speedup 和误差。我们的保底
目标是一个确实上板、数据完整、限制分析诚实的中等优化设计，而不是一个只在代码中看起来
高度优化但没有板级证据的版本。谢谢，接下来进入问答。

## Q&A 准备

### 为什么选择定点而不是 float？

定点通常能降低 DSP、存储和带宽成本，但我们不会只凭经验选择位宽。当前 Q24.8 是安全
基线；最终位宽要在正式权重和课程图像下同时满足 saturation、逐层误差和 PSNR/SSIM 门槛。

### 为什么现在没有 II、资源或 speedup？

主力机器是 Mac，Vitis/Vivado 只支持 Linux/Windows x86_64。目前的结果只来自 native
host 仿真。II、资源和 timing 必须来自指定 part 和 clock 下的真实 csynth/implementation。

### 为什么不把 Conv1、Conv2 中间图放进 BRAM？

两张中间图在 32 位下约为 23.81 MiB，远超当前设计可合理使用的片上 RAM。line buffer
只保留卷积窗口所需的历史行，最低 payload 是 34,680 个值，更适合流式结构。

### 如何保证 HLS 版本没有改变算法？

我们保留冻结 float Golden，逐层比较 Conv1、Conv2 和 Conv3；同时固定 padding、bias
顺序、CHW/OIHW 布局和 cross-correlation 语义。任何版本没有通过逐层门禁都不会进入
下一阶段。

### 为什么 Conv3 的误差最大？

Conv3 每个输出累加 800 项，远多于 Conv1 的 81 项和 Conv2 的 64 项，量化误差会在更深
的归约中累积。因此 accumulator 位宽和 Conv3 输出误差需要单独检查。

### 如何定义 speedup？

只比较相同边界。kernel-only speedup 使用相同卷积计算边界；end-to-end speedup 包含
DMA、cache 和必要的 host 工作。不会用 CPU end-to-end 时间除以 FPGA kernel-only 时间。
