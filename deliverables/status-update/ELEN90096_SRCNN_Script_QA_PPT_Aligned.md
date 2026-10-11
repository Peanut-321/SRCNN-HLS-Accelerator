# ELEN90096 SRCNN Status Update — Two-Presenter Script (EN/中文)

## Split and timing / 分工与时间

Ziye Xiong speaks first. Aero Cao speaks second. Ziye's script is unchanged. Aero's script is simplified below. The timing table gives rehearsal targets, not measured speaking times. Aim for about 10 minutes together, then about 5 minutes of Q&A.
Ziye Xiong 先讲，Aero Cao 后讲。队友讲稿保留原文，你的第 6-10 页改为简单版。表格是排练目标，不是实际测得时长。两人合计目标约 10 分钟，之后约 5 分钟问答。

Every sentence is short on purpose. Read the English aloud. The Chinese is for checking meaning only.
每句话都刻意写短了。上台读英文。中文只用来核对意思。

| Slide | Topic / 内容 | Speaker / 讲者 | Time / 时长 | Ends at / 累计 |
| --- | --- | --- | --- | --- |
| 1 | Title and status / 标题与进度 | Ziye | 0:45 | 0:45 |
| 2 | Algorithm / 算法结构 | Ziye | 0:50 | 1:35 |
| 3 | Workload / 计算量 | Ziye | 0:55 | 2:30 |
| 4 | Architecture / 硬件架构 | Ziye | 1:15 | 3:45 |
| 5 | HLS optimisation / HLS 优化过程 | Ziye | 1:10 | 4:55 |
| 6 | OC4 result / OC4 结果 | Aero | 0:50 | 5:45 |
| 7 | Fixed-point precision / 定点精度 | Aero | 1:00 | 6:45 |
| 8 | Verification / 验证 | Aero | 1:00 | 7:45 |
| 9 | V3 board result / V3 板测结果 | Aero | 1:15 | 9:00 |
| 10 | Status and next steps / 现状与剩余工作 | Aero | 0:50 | 9:50 |

Four lines to never cross / 四条红线：

- Never present an HLS estimate as a board measurement. / 不要把 HLS 估算值说成板上实测。
- Never call 0.750 s kernel time or a CPU speedup. / 不要把 0.750 秒说成 kernel 时间或 CPU 加速比。
- Never say bit-exact means zero error versus float. / 不要把“逐位一致”说成和浮点零误差。
- Never say the 13×17 auto co-sim passed. / 不要说 13×17 的自动 co-sim 通过了。

## Presenter 1 — Ziye Xiong (Slides 1–5, 4:55)

### Slide 1 · Title and status · 0:45

Hi everyone. I'm Ziye Xiong. This is Aero Cao. Our project is an FPGA accelerator for SRCNN. SRCNN is a network for image super-resolution. We run it on the Kria KV260 board.

大家好。我是 Ziye Xiong。这位是 Aero Cao。我们的项目是 SRCNN 的 FPGA 加速器。SRCNN 是一个图像超分辨率网络。我们把它跑在 Kria KV260 板子上。

Here is our status in one line. The HLS design is done. The RTL verification is done. The 200 MHz hardware is done. And both fixed-point versions now pass on the real board. The bar at the bottom shows all five stages complete.

我们的进度可以用一句话说清。HLS 设计完成了。RTL 验证完成了。200 MHz 的硬件也完成了。两个定点版本现在都在真实板子上通过了。底部的进度条显示五个阶段全部完成。

For each part, we answer four questions. What did we build? Why? What is the evidence? What is still missing?

每部分我们都回答四个问题。做了什么？为什么？证据是什么？还缺什么？

### Slide 2 · Algorithm · 0:50

The network is fixed by the course. We cannot change the algorithm. We can only change how it runs. The input has one channel. It is 255 by 255 pixels. It is already upsampled with bicubic.

网络结构由课程固定。我们不能改算法。我们只能改它的运行方式。输入是单通道。大小是 255×255。它已经做过 bicubic 上采样。

Conv1 has 64 filters. Each filter is 9 by 9. ReLU follows. Conv2 is a 1 by 1 convolution. It turns 64 channels into 32. ReLU follows again. Conv3 has a 5 by 5 kernel. It turns 32 channels into one image. It has no activation.

Conv1 有 64 个卷积核。每个是 9×9。后面接 ReLU。Conv2 是 1×1 卷积。它把 64 通道变成 32 通道。后面也接 ReLU。Conv3 是 5×5 卷积。它把 32 通道变回一张图。它没有激活函数。

All layers use stride 1. We use cross-correlation. So the kernels are not flipped. Borders use replicate-edge padding. So the output is also 255 by 255.

所有层的 stride 都是 1。我们用的是 cross-correlation。所以卷积核不翻转。边界用 replicate-edge padding。所以输出也是 255×255。

### Slide 3 · Workload · 0:55

Now let's count the work. One frame needs about 522 million MACs. MAC means multiply-accumulate. Conv1 alone needs 337 million. That is about 65 percent. So Conv1 is our first target.

现在来算计算量。一帧需要大约 5.22 亿次 MAC。MAC 就是乘加运算。光 Conv1 就有 3.37 亿次。大约占 65%。所以 Conv1 是我们的第一个优化目标。

This workload fits hardware well. The convolutions are regular. Each input pixel is reused many times. The 64 output channels are independent. So they can run in parallel. The three layers can also form a pipeline.

这个负载很适合硬件。卷积很规则。每个输入像素会被重复使用很多次。64 个输出通道互相独立。所以它们可以并行。三层也可以做成流水线。

There are also challenges. The middle feature maps are large. Conv3 adds 800 terms for each output. So the accumulator must be wide. DDR and DMA traffic can become a bottleneck. And fixed-point precision must be proven.

但也有挑战。中间特征图很大。Conv3 每个输出要累加 800 项。所以累加器要够宽。DDR 和 DMA 传输可能成为瓶颈。定点精度也必须拿证据证明。

### Slide 4 · Architecture · 1:15

This is our final architecture. The left side is the PS. Its DDR holds three buffers. One is the model. One is the input frame. One is the output frame.

这是我们的最终架构。左边是 PS。它的 DDR 里有三个 buffer。一个放模型。一个放输入帧。一个放输出帧。

First, a block called load_runtime_model reads the model from DDR. The model has 8,129 words. That is 32,516 bytes. It is read once per run. Each layer then keeps its own weights on chip.

首先，load_runtime_model 模块从 DDR 读取模型。模型有 8,129 个字。也就是 32,516 字节。每次运行只读一次。之后每一层把自己的权重放在片上。

Next, the image streams in through AXI DMA. It is 65,025 words of 32 bits. Conv1 has four output-channel lanes. Conv1 feeds Conv2 through a FIFO. Conv2 feeds Conv3 through another FIFO. The result streams out through DMA. The output is also 65,025 words.

接着，图像通过 AXI DMA 流进来。一共 65,025 个 32 位字。Conv1 有四条输出通道 lane。Conv1 通过 FIFO 送给 Conv2。Conv2 再通过 FIFO 送给 Conv3。结果通过 DMA 流出去。输出也是 65,025 个字。

The key idea is the pixel-major stream. Each pixel travels with all its channel values. We never build a full feature map. So the Conv1 and Conv2 maps are never written to DDR. Together they would be about 24 MiB. DDR only holds the model, the input and the output.

关键思想是按像素传输的数据流。每个像素带着它所有通道的值一起走。我们从不生成完整的特征图。所以 Conv1 和 Conv2 的特征图不会写回 DDR。它们加起来大约有 24 MiB。DDR 里只有模型、输入和输出。

### Slide 5 · HLS optimisation · 1:10

We reached this design in several steps. After each step, we checked against the Golden. Step one was natural loops. This was our functional baseline. Step two added line buffers.

我们分几步得到这个设计。每一步之后，都和 Golden 对比。第一步是普通循环。这是功能基线。第二步加入了行缓存。

Our first line buffer used circular row banks. A runtime selector picked the bank. This selector made wide multiplexers. The multiplexers hurt timing. So we used fixed-delay banks. Each bank has one fixed role. The selector is gone.

第一版行缓存用的是循环行 bank。运行时由一个选择器挑 bank。这个选择器产生了很宽的多路选择器。多路选择器拖累了时序。所以我们改用固定延迟的 bank。每个 bank 的角色固定。选择器就没有了。

Then we specialised the code for replicate padding only. This happens at compile time. It brought back 5 ns HLS timing.

然后我们把代码专门化，只支持 replicate padding。这在编译期完成。它让 HLS 重新达到 5 ns 时序。

Only then did we add parallelism. First we computed two output channels per pass. Then we computed four. Last, we built a canonical DATAFLOW structure. Streams connect the layers.

这之后我们才加并行。先是每轮算两个输出通道。再是四个。最后我们搭了规范的 DATAFLOW 结构。层与层之间用 stream 连接。

One idea did not help. We changed the write-back address logic. It gave no gain. We kept it as a negative result.

有一个尝试没有效果。我们改了写回地址逻辑。它没有带来收益。我们把它作为负结果保留下来。

**Handover / 交接：** "Timing is now under control. Aero will show what OC4 gives us, and how we got it onto the board."
“时序问题已经解决。下面由 Aero 介绍 OC4 带来了什么，以及我们怎么把它跑上板。”

## Presenter 2 - Aero Cao (Slides 6-10, target about 4:55)

只读下面英文。中文用于理解；“提示”不用读。表格和图上的精确数字不需要逐个念。
格式读法：Q24.8 = Q twenty-four point eight；Q20.12 = Q twenty point twelve。

### Slide 6 · OC4 result · target 0:50

Thanks, Ziye. This slide shows why we added parallelism. The baseline processes one output channel at a time. OC4 processes four together. We still calculate every output channel. We do not change the network.

谢谢 Ziye。这页说明为什么我们增加并行。基线每次处理一个输出通道。OC4 同时处理四个。我们仍然计算全部输出通道，没有改变网络。

In this earlier HLS comparison, the total estimated latency falls by more than half. The chart shows the exact values. This improvement costs more hardware.

在这次较早的 HLS 对比中，整体估算延迟下降了一半以上。精确数字在图上。这个改善需要更多硬件资源。

So we need a balance between speed and resources. These are HLS estimates. I will show the physical board results later.

因此需要在速度和资源之间取舍。这里是 HLS 估算，后面我会展示实物板测结果。

提示：指上方延迟图和资源表即可。不读大周期数、百分比或 LUT 数量。这是历史 HLS checkpoint，不是最终 V3 的帧时间。

### Slide 7 · Fixed-point precision · target 1:00

Next is image quality. We first used Q24.8. It passes the hardware checks, but it loses too much quality compared with float.

接下来是图像质量。我们首先使用 Q24.8。它通过了硬件检查，但与浮点相比，质量损失太大。

The reason is limited fractional precision. Some small weights become zero. So we tried more fractional bits in our offline study.

原因是小数精度有限，一些小权重变成了零。因此，我们在离线实验中尝试了更多小数位。

Q20.12 stays much closer to the float result on the supplied test images. It passes our quality criteria. The chart shows this clearly.

在提供的测试图像上，Q20.12 更接近浮点结果，通过了我们设定的质量标准。图表清楚展示了这一点。

Both formats still use the same word size. We choose Q20.12 for better quality. We keep the model data and bitstream for each format separate.

两种格式的数据字宽仍然相同。我们优先选择 Q20.12，是因为质量更好。每种格式的模型数据和 bitstream 都分开使用。

提示：不用念 PSNR 小数或变零权重数量。质量标准是团队工程标准，不是老师规定的阈值；这是提供图像子集的离线结果。

### Slide 8 · Verification · target 1:00

How do we check correctness? We start with an independent reference. Then we check the software and hardware results.

我们怎样检查正确性？首先建立独立参考，然后检查软件和硬件结果。

The automatic co-simulation passed small cases, but it stalled on a larger case. We do not count that run as a pass.

自动联合仿真通过了小案例，但在较大案例上卡住。我们没有把这次运行算作通过。

We also use an independent RTL testbench. At a newer source version, it passes two full frames without a reset between them. Every output matches the reference.

我们也使用独立的 RTL 测试平台。在较新的源码版本上，它连续通过两张完整帧，中间不复位。所有输出都匹配参考结果。

That source version is separate from the deployed V3 version. The board tests check V3 independently. I will show those results next.

这个源码版本和已经部署的 V3 版本不同。板测独立检查了 V3。接下来我会展示这些结果。

提示：不用念图像尺寸或总输出数。不要把较新 RTL 和 V3 板测说成同一源码版本。自动仿真卡住的根因仍未解决。

### Slide 9 · V3 board result · target 1:15

This is our main new result. Both formats now work on the real board. Both V3 designs meet the requested clock timing. Their resource use is similar.

这是我们主要的新成果。两种格式现在都已在实物板上运行。两个 V3 设计都满足要求的时钟约束，资源使用也相近。

The earlier build had a reset connection problem. It kept the AXI hardware in reset. We fixed that connection in V3.

较早版本的复位连接有问题，让 AXI 硬件一直处于复位状态。我们在 V3 修正了这个连接。

Each format passes fourteen frames. We test repeats, a changed input and model, restoration, and overlay reload. Every output matches its fixed-point reference.

每种格式通过十四帧。我们测试了重复运行、改变输入和模型、恢复以及重新加载 overlay。全部输出都匹配对应定点参考。

The median measured time is about zero point seven five seconds. It includes model loading and DMA. Matching the fixed-point reference does not mean zero error against float.

测量时间的中位数约为 0.75 秒，包含模型加载和 DMA。匹配定点参考不等于对浮点零误差。

提示：只有这里保留十四帧和 0.75 秒。指着 PASS 记录和表格停顿；不用念 WNS 小数、资源数量或 65,025。测量排除缓冲区分配和输出比较，不是纯 kernel 时间。

### Slide 10 · Status and next steps · target 0:50

Our core implementation works on the board in both formats. The next step is performance evaluation and broader testing.

两种格式的核心实现都已经在板上运行。下一步是性能评估和更广泛测试。

First, we need a fair CPU comparison with the same input, model and timing boundary. Then we can report a speedup.

首先需要用相同输入、模型和计时边界做公平的 CPU 对比，之后才能报告加速比。

We also need to find where the time goes, test more images, and finish the report.

我们还需要分析时间花在哪里，测试更多图像，并完成最终报告。

The two formats have almost the same measured time. Q20.12 gives better quality in our offline study. Thank you. We are happy to take questions.

两种格式的实测时间几乎相同。离线实验中，Q20.12 的质量更好。谢谢大家，欢迎提问。

提示：结束时突出“核心实现已成功”，不说项目全都没有完成，也不承诺未经测量的加速倍数。

## Q&A / 与最终 PPT 逐页对应的问答

本版根据你提供的最终 10 页 PPT 重新整理，不是通用题库。讲稿正文保留不变。每题的英文是可以直接说的短答案；中文和“追问提醒”不用读。

分工：第 1–5 页由 Ziye 主答，第 6–10 页由 Aero 主答。难题可请队友补充。先练标有“优先准备”的题，不需要背完所有备用解释。若老师提问超出已测范围，明确说尚未验证。

### 第 1–2 页：项目与网络 / 建议 Ziye 主答

#### Q1. What does your project do?

中文问题：你们项目做什么？

**You can say:** We run an image super-resolution network on an FPGA. Our input is already enlarged. The network improves image detail.

**中文意思：** 我们把图像超分辨率网络放到 FPGA 上运行。输入已经放大，网络负责改善图像细节。

追问提醒（不用背）：不是 FPGA 从小图直接完成放大；bicubic 预处理不在这三层卷积里。

#### Q2. Why do you use three convolution layers?

中文问题：三层各做什么？

**You can say:** The first layer extracts features. The second changes these features. The last layer produces the output image.

**中文意思：** 第一层提取特征，第二层转换特征，最后一层生成输出图像。

追问提醒（不用背）：第 2 页：第一、二层有 ReLU，第三层没有。

#### Q3. What does the one-by-one layer do?

中文问题：中间 1×1 卷积有什么用？

**You can say:** It mixes information across channels at each pixel. It does not combine nearby pixels.

**中文意思：** 它在每个像素处混合不同通道的信息，不混合周围像素。

追问提醒（不用背）：不要说 1×1 没有计算：它仍需要对输入通道做乘加。

#### Q4. Why does the output keep the same size?

中文问题：为什么输出尺寸不变？

**You can say:** We use stride one and repeat the edge pixels for padding. This keeps the image size the same.

**中文意思：** 步长为一，边缘用最近的边缘像素补齐，因此尺寸不变。

追问提醒（不用背）：第 2 页使用 replicate-edge，不是 zero padding；实现为 cross-correlation，卷积核不翻转。

### 第 3 页：为什么适合加速 / 建议 Ziye 主答

#### Q5. Why is this algorithm suitable for an FPGA?

中文问题：为什么适合 FPGA？

**You can say:** The calculations are regular. We can reuse nearby pixels, process channels in parallel, and overlap the layers.

**中文意思：** 计算很规则。可以复用附近像素、并行处理通道，并让不同层重叠运行。

追问提醒（不用背）：优势是可设计的数据复用和并行结构，不代表已经证明比 CPU 快。

#### Q6. Why did you optimise the first layer first?

中文问题：为什么先优化第一层？

**You can say:** It takes the largest share of the work. Improving this layer was a useful first step.

**中文意思：** 第一层占最多计算量，因此先优化它很有价值。

追问提醒（不用背）：第 3 页 Conv1 约占总 MAC 的三分之二；精确值在 PPT 上，不必主动背。

### 第 4 页：Streaming 架构 / 建议 Ziye 主答

#### Q7. Why not store full intermediate feature maps?

中文问题：为什么不保存完整中间特征图？

**You can say:** They are too large for our on-chip memory. We use line buffers and streams to avoid writing each full intermediate map to DDR.

**中文意思：** 完整特征图太大，片上存不下。我们用行缓存和数据流，避免把每一层完整中间结果写回 DDR。

追问提醒（不用背）：PPT 的 feature maps never touch DDR 指中间特征图；原始输入、最终输出和模型传输仍涉及 DDR。

#### Q8. How do data move through the system?

中文问题：数据怎么流动？

**You can say:** DMA sends the input from DDR. The layers pass results through FIFOs. DMA then writes the final output back to DDR.

**中文意思：** DMA 从 DDR 送入输入；层之间通过 FIFO 传递结果；DMA 把最终输出写回 DDR。

追问提醒（不用背）：模型走 memory-mapped 装载路径并存入片上权重缓存，不要说所有模型数据都走同一个 AXI-Stream。

#### Q9. What are line buffers and sliding windows?

中文问题：行缓存和滑动窗口是什么？

**You can say:** A line buffer keeps recent image rows. A sliding window keeps the small group of pixels needed for the current convolution.

**中文意思：** 行缓存保存最近几行。滑动窗口保留当前卷积需要的一小块像素。

追问提醒（不用背）：目的：像素到达后局部复用，不保存完整的多通道中间图。

#### Q10. What does DATAFLOW do here?

中文问题：DATAFLOW 在这里做什么？

**You can say:** It lets different stages work at the same time. FIFOs connect them. The slowest stage still limits the overall rate.

**中文意思：** 它让不同阶段同时工作，用 FIFO 连接；整体速度仍受最慢阶段限制。

追问提醒（不用背）：有流水线不等于没有瓶颈，也不等于所有层每拍处理一整张图。

### 第 5 页：设计过程与失败尝试 / 建议 Ziye 主答

#### Q11. Why did you fix timing before adding more parallelism?

中文问题：为什么先修时序再加并行？

**You can say:** More parallel work is useful only if the design meets timing. We first simplified the buffer logic, then increased parallelism.

**中文意思：** 并行增加后仍需满足时序才有用。我们先简化缓存逻辑，再增加并行度。

追问提醒（不用背）：第 5 页 circular-row selector 会产生宽选择逻辑；fixed delay banks 减少运行时选择。

#### Q12. Did every optimisation help?

中文问题：每次优化都有收益吗？

**You can say:** No. An early address-only write-back change did not help. We kept changes only when the measured reports showed a benefit.

**中文意思：** 没有。早期只改写回地址的尝试没有收益。我们依据报告决定是否保留优化。

追问提醒（不用背）：只说 PPT 上这次早期尝试；不能扩展成所有 write-back 优化都没用。

### 第 6 页：OC4 与 HLS 结果 / 建议 Aero 主答

#### Q13. What does OC4 mean?

中文问题：OC4 是什么？

**You can say:** It calculates four output channels in parallel. It still computes all output channels, so we do not change the network.

**中文意思：** 它并行计算四个输出通道，但仍计算全部输出通道，不改变网络。

追问提醒（不用背）：优先准备。不是把网络从 64 通道减成 4 通道。

#### Q14. Does this prove that your FPGA is twice as fast as a CPU?

中文问题：这里能证明比 CPU 快一倍吗？

**You can say:** No. This slide compares two HLS designs. It shows estimated cycle savings, not a measured CPU speedup.

**中文意思：** 不能。这页比较两种 HLS 设计，显示估算周期减少，不是 CPU 实测加速比。

追问提醒（不用背）：优先准备。历史非 streaming checkpoint；top 减少约一半，Conv1 减少更多。不要把这个表当最终板测延迟。

#### Q15. Why not use more parallel channels?

中文问题：为什么不继续提高并行度？

**You can say:** More parallelism needs more hardware and memory access. We chose four as a practical balance. We have not shown an eight-channel board result.

**中文意思：** 更多并行需要更多资源和存储访问。四路是当前折中，我们没有八路板测结果。

追问提醒（不用背）：不能声称 OC4 已证明是全局最优。

#### Q16. Does II one mean one image per cycle?

中文问题：II=1 是每拍一张图吗？

**You can say:** No. It describes the start rate of a particular loop. A complete image still needs many loop iterations.

**中文意思：** 不是。它描述某个循环启动新迭代的速率，整张图仍要很多次循环。

追问提醒（不用背）：第 6 页是历史 checkpoint 的 tap loop，不能推广到全系统吞吐率。

### 第 7 页：定点精度 / 建议 Aero 主答

#### Q17. Why choose Q20.12?

中文问题：为什么选 Q20.12？

**You can say:** It keeps image quality close to floating point in our tests. It is the lowest fractional precision we tested that passed our quality checks.

**中文意思：** 在我们的测试里，它的图像质量接近浮点；它是测试过的、通过质量检查的最低小数精度。

追问提醒（不用背）：优先准备。是最低 tested，不是数学上绝对最低；Q22.10 平均值接近，但有单图超过允许差值。

#### Q18. Why did Q24.8 pass the board test but lose image quality?

中文问题：Q24.8 板测通过，为什么质量差？

**You can say:** The board matches its fixed-point reference correctly. But this format loses small weights during quantisation, which hurts image quality.

**中文意思：** 板子正确匹配自己的定点参考，但这个格式量化后丢掉很多小权重，因此图像质量下降。

追问提醒（不用背）：优先准备。实现正确和量化质量是两件事。

#### Q19. Does bit-exact mean no error compared with floating point?

中文问题：逐位一致是不是相对浮点零误差？

**You can say:** No. It means the board output exactly matches its own fixed-point reference. Floating-point quality is checked separately.

**中文意思：** 不是。板上输出与自己的定点参考完全一致，浮点质量另做比较。

追问提醒（不用背）：优先准备。不要把板测 Golden 和浮点输出混用。

#### Q20. What do the two PSNR numbers mean?

中文问题：这页两个 PSNR 指标有什么区别？

**You can say:** One compares image quality against the true image. The other compares fixed-point output with floating-point output. They answer different questions.

**中文意思：** 一个用真实图像比较重建质量；另一个直接比较定点输出和浮点输出，回答不同问题。

追问提醒（不用背）：备用数字：0.004187 dB 是测试集内重建 PSNR 最大绝对差；60.621 dB 是定点对浮点输出的最低 PSNR，不是相对真实图像的重建 PSNR。

#### Q21. Do more fractional bits reduce DMA traffic?

中文问题：更多小数位会减少 DMA 数据量吗？

**You can say:** No. Both formats still use the same word size. We change numerical precision, not the number of bytes per word.

**中文意思：** 不会。两种格式字长相同，改变的是数值精度，不是每个字的字节数。

追问提醒（不用背）：两种格式均为 32-bit words。也不要混用两种格式的模型和 bitstream。

### 第 8 页：验证证据与范围 / 建议 Aero 主答

#### Q22. Did all automatic co-simulation tests pass?

中文问题：所有自动 co-sim 都通过了吗？

**You can say:** No. The larger automatic test stalled. We do not call it a pass. We have separate independent RTL tests and physical board tests.

**中文意思：** 没有。较大的自动测试停住了，不能算通过。我们另外有独立 RTL 和实物板测证据。

追问提醒（不用背）：优先准备。13×17 自动 co-sim stalled；不要说已经彻底查明或修好自动 harness 根因。

#### Q23. Are the full-frame RTL test and the V3 board test the same version?

中文问题：全帧 RTL 和 V3 板测是同一版本吗？

**You can say:** No. The full-frame RTL result is from a newer source version. The board results are from the deployed V3 packages. We report them separately.

**中文意思：** 不是。全帧 RTL 是较新源码版本；板测是已部署的 V3 包，我们分开报告。

追问提醒（不用背）：优先准备。第 8 页底部用语容易让人误解；讲稿和答题必须明确版本区别。

#### Q24. Why did you deliberately use a wrong reference?

中文问题：为什么故意用错误参考？

**You can say:** We wanted to check the checker itself. It rejected the wrong output, so it was not simply reporting a pass every time.

**中文意思：** 我们想验证检查器本身。错误参考被拒绝，说明不是无论结果怎样都显示通过。

追问提醒（不用背）：这证明本次负控制能发现错误，不证明所有可能错误都必定被发现。

### 第 9 页：最终实物结果 / 建议 Aero 主答

#### Q25. What exactly passed on the board?

中文问题：板上到底通过了什么？

**You can say:** Both formats passed repeated runs, changed input and model, restore, and overlay reload. Every output word matched its fixed-point reference.

**中文意思：** 两种格式都通过重复运行、改变输入和模型、恢复以及重载；全部输出字与各自定点参考一致。

追问提醒（不用背）：优先准备。每种格式 14 次输出，不是 14 张互不相同的图片；包括 warmup、10 repeat、changed、restored、reload。

#### Q26. What was wrong with the earlier hardware?

中文问题：之前硬件哪里错了？

**You can say:** An active-low reset was tied low. This kept the control path in reset. The V3 design corrected the connection.

**中文意思：** 一个低有效复位信号被接成低电平，控制路径一直处于复位。V3 修正了这个连接。

追问提醒（不用背）：优先准备。只解释已确认的复位连接问题，不把此前全部网络断线或文件校验问题都归结为它。

#### Q27. What does the board time include?

中文问题：板测时间包含什么？

**You can say:** It is the host-side transfer window, including model DMA. It is not pure kernel time, and it is not a CPU comparison.

**中文意思：** 它是主机侧传输时间窗口，包含模型 DMA；不是纯 kernel 时间，也不是 CPU 对比。

追问提醒（不用背）：优先准备。约 three quarters of a second；逆数只能叫 transfer-window FPS，不能叫已证明持续推理吞吐率。

#### Q28. Why is it still slow at two hundred megahertz?

中文问题：200 MHz 为什么仍需要这么久？

**You can say:** Clock speed alone does not tell us the frame time. We still need to measure the separate stages before naming the main bottleneck.

**中文意思：** 单看时钟频率无法得到整帧时间。需要分段测量才能确定主要瓶颈。

追问提醒（不用背）：不能断言全部时间由 DDR、Python 或某一层造成；也不能拿第 6 页历史周期表直接预测这次板测。

#### Q29. Why are the two formats almost equally fast?

中文问题：两种精度为什么速度几乎相同？

**You can say:** They use the same basic architecture and data word size. Our measured transfer times are very close. The main difference here is image quality.

**中文意思：** 基本架构和数据字长相同，实测传输时间很接近；这里主要差别是图像质量。

追问提醒（不用背）：PPT 写 same，口头说 almost the same。不要说结果精确相等或一定能代表所有输入。

### 第 10 页：进度与下一步 / 建议 Aero 主答

#### Q30. Is your project finished?

中文问题：项目完成了吗？

**You can say:** The hardware works for our tested cases. We still need a fair CPU comparison, timing breakdown, broader board tests, and the final report.

**中文意思：** 硬件在已测情况中能工作；仍需公平 CPU 对比、分段计时、更广的板测以及最终报告。

追问提醒（不用背）：优先准备。肯定已完成的实物验证，不等于承诺所有输入都正确或已证明性能提升。

#### Q31. How will you make the CPU comparison fair?

中文问题：如何公平比较 CPU？

**You can say:** We will use the same input, model, and output checks. We will state the timing boundaries clearly and compare equivalent work.

**中文意思：** 使用相同输入、模型和输出检查，说明计时边界，并比较等价工作。

追问提醒（不用背）：如 FPGA 数据搬运计入，就不能拿 CPU 不同边界的纯计算时间直接得出加速比。预处理包含与否也需一致说明。

### 课上内容的相关追问 / 备用，不作为主线

只在老师把第 3–4 页架构与课上概念联系起来时使用。设计细节由 Ziye 补充。

#### B1. What is the difference between tiling and streaming?

中文问题：tiling 和 streaming 有什么区别？

**You can say:** Tiling splits work into small blocks for data reuse. Streaming passes data through stages as it arrives. Our design uses streaming with local reuse.

**中文意思：** Tiling 把工作分成小块来复用数据；streaming 让到达的数据逐级处理。我们的方案是带局部复用的 streaming。

提醒：两者可以结合，不是互斥；不要声称实现了课件里完整的多维 tile 调度。

#### B2. Why use streaming instead of full tiled convolution?

中文问题：为什么采用 streaming 而不是完整 tiled convolution？

**You can say:** Our line buffers reuse nearby pixels without storing full intermediate maps. This fits our fixed network and image size.

**中文意思：** 行缓存可以复用附近像素，不保存完整中间特征图；适合我们当前固定网络和图像尺寸。

#### B3. What is the difference between pipelining and unrolling?

中文问题：pipeline 和 unroll 有什么区别？

**You can say:** Pipelining overlaps different iterations. Unrolling creates parallel work within a loop. Both need enough memory access and hardware resources.

**中文意思：** 流水线让不同迭代重叠；展开使循环内的工作并行。两者都需要足够的存储访问能力和硬件资源。

对应第 5–6 页。不要把 II=1 等同于无限并行。

#### B4. Why not use a GPU?

中文问题：为什么不用 GPU？

**You can say:** We focus on an FPGA implementation for this project. It lets us build a custom data path. We have not measured a GPU comparison.

**中文意思：** 本项目重点是 FPGA 实现，可以设计专用数据通路；我们没有测 GPU 对比。

对应第 3–4 页。不要无测量就声称 FPGA 更快或更省电。

### 不懂问题或需要队友补充时

- **Could you please repeat the question more slowly?** / 请您把问题说慢一点好吗？
- **Do you mean image quality, or hardware correctness?** / 您指图像质量还是硬件实现正确性？
- **I can explain the board result. Ziye can add the design details.** / 我可以解释板测结果，Ziye 可以补充设计细节。
- **We have not measured that yet, so we cannot claim it.** / 我们还没测，所以不能作这个结论。

### Aero 的最短准备清单

先掌握这些意思，不用背很多数字：

1. 第 6 页：OC4 是四路并行，不是减少网络通道；HLS 表不是 CPU 加速比。
2. 第 7 页：实现正确和图像质量不同；Q20.12 精度更好，bit-exact 对的是各自定点参考。
3. 第 8 页：自动 co-sim 停住不算 PASS；新版 RTL 与 V3 板测分开报告。
4. 第 9 页：复位连接已修正；两种格式测试通过；约四分之三秒是传输窗口，不是纯计算时间。
5. 第 10 页：硬件已在测试范围内运行成功；公平 CPU 对比和更广验证还没完成。

### 最终 PPT 的两处口头澄清（PPT 文件未改）

- 第 8 页底部 “the RTL is covered by our testbench and by the board run” 不宜理解成所有结果来自同一版本。讲稿已澄清，答题按 Q23 分别报告新版源码 RTL 和已部署 V3 板测。
- 第 10 页 “Both formats take the same board time” 应读成 **almost the same board time**，不是精确相等。

### 本版核对依据

- 最终 PPT：G:/xwechat_files/wxid_17eii0mikg2p22_696c/msg/file/2026-10/ELEN90096_SRCNN_Status_Update(2).pptx。逐页提取文字并检查 PowerPoint 导出的全部 10 页图像。
- 原稿：C:/Users/aeroc/Desktop/文件/EE/2026S2/90096/Project/ELEN90096_SRCNN_Script_EN_ZH_Aero_Easy.md。问答之前的正文原样保留。
- 实物与硬件版本：results/aero-local-dual-build.md。
- 新版 RTL 范围：origin/optimize/official-q20-12 分支的 results/p3-q20-12-full-frame-rtl.md。
- 精度筛选定义：同分支 results/p3-official-precision-study.md；阈值是项目工程筛选标准，不是声称老师强制要求。

