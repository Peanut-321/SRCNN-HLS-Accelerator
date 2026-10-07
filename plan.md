# ELEN90096 SRCNN Execution Plan v2.2（实际执行记录）

基于 [`spec.md`](./spec.md) v1.0、Canvas Project Overview、Golden starter 与
2026-10-05 已提交 Golden Reference。最后更新：**2026-10-08**。

**文档状态：** 🟢 `[ACTIVE]`。P2.2a 已在 Mac 完成，P2.2b 等正式资产恢复；P0 仍是
外部关键路径。

> 本文档取代旧 `plan.md` v0.1。旧版已包含在
> `results/p2_1-complete-source.tar.gz` 中，可恢复但不再作为执行依据。
> 本文档只复用所附模板的“实际输出、验证证据、计划偏离、状态总览”写法，
> 不继承模板项目的固定尺寸、cycle、资源或 speedup 数据。用户明确提供的既有
> RoCC 项目只可作为有原始证据时的可选背景讨论，不是本 SRCNN 项目的实测结果。

---

## 状态定义

| 标记 | 含义 |
|---|---|
| ✅ `[DONE]` | 该子阶段自己的完成门已全部通过，并有可复核证据 |
| 🟡 `[PARTIAL]` | 已有有效产物，但完整阶段门尚未通过 |
| 👀 `[AWAITING_REVIEW]` | 当前产物已提交，按纪律等待确认后再继续 |
| ⏸️ `[BLOCKED]` | 缺外部资料、工具环境、硬件或必须先做的决策 |
| ⏳ `[TODO]` | 尚未开始 |
| ⏭️ `[DEFERRED]` | MVP 后才允许开展，不代表取消 |

`DONE` 只描述标题所指的子阶段。例如“P2.1 host 骨架 DONE”不等于 HLS
综合、RTL co-sim 或板级部署完成。凡未实际测量的 latency、II、clock、资源、
带宽和功耗一律写 `NOT MEASURED`，不得用估算冒充实测。

---

## 当前项目快照

- **Golden milestone：**课程版 `conv1.cpp/srcnn.cpp/srcnn.h` 已验证、打包并于
  2026-10-05 提交；提交版本冻结。
- **P1 internal Golden：**通用内部回归资产继续保留并冻结，不替代课程版契约。
- **P2.1 dual-target 骨架：**Mac host 范围内已完成、验证并封存。
- **255×255 workload 分析：**精确 MAC、参数、特征图和理论流量已记录，可直接用于
  Status Update；不包含任何伪装成实测的 FPGA 数字。
- **当前允许动作：**在 Mac 上继续 P2.2b；同时已在隔离分支建立 line-buffer host
  原型，作为结构正确性实验，不替代 P0a/csynth gate。P2.1 配置已重基线到课程正式
  `255×255 + replicate-edge + bias-first` 契约。
- **最大进度风险：**P0 工具链/板卡链路仍未贯通，尚无任何真实 HLS、Vivado
  或 KV260 数据。
- **当前 MVP 状态：**未达成。缺 P0、P2.2、P2.3、P3 和至少三行消融数据。

关键依赖关系如下；`S0` 的不同 blocker 不作为一整块含糊的总开关：

```text
Golden submitted [DONE] → P2.1 host [DONE] → P2.2 → P2.3 → P3 → P4
random vectors + host AP types                  ──→ P2.2a [DONE]
official weights/input/output restored locally ──→ P2.2b
P0a HLS/export + P2.2 numeric freeze            ──→ P2.3
P0b bitstream + P0c dummy DMA/overlay    ──→ P3
spec §11 interface/report blockers       ──→ P3 / P4
```

P0 与 Mac 代码线应并行推进；P2.1 先于 P0 完成不表示 P0 可以继续拖延。

---

## S0 — 规格基线与决策冻结 🟡 [PARTIAL — 功能已冻结，部署仍待确认]

为避免与已经定义的“P0 工具链贯通”撞号，规格门禁记为 `S0`，不重新占用 P0。

### 原计划

所有算法、数据、接口和平台参数完全冻结后才开始实现。

### 实际执行

`spec.md` 已升为 v1.0。Canvas Project Overview、Golden starter 与官方参考数据已经
关闭 kernel 功能语义；DMA/clock/资源预算、颜色预处理细节和正式定点阈值继续保持 TBD。

已稳定的内部契约：

| 项目 | 当前执行契约 | 状态 |
|---|---|---|
| 网络 | Conv1 9×9 1→64；Conv2 1×1 64→32；Conv3 5×5 32→1 | 已确认 |
| 运算 | cross-correlation，不翻转 kernel | 已确认 |
| 激活 | Conv1/2 ReLU；Conv3 无 ReLU/clamp | 已确认 |
| P1 内部布局 | activation 为 CHW；weights 为 OIHW；bias 为 O | 内部冻结，不等同最终 DMA 布局 |
| P1 dump | `SRCNN_TENSOR_V1`，见 `docs/tensor-format.md` | 已冻结 |
| float 可复现 | float32、`-ffp-contract=off`、拒绝 fast-math | 已冻结 |
| 课程部署尺寸 | 单帧 `1×255×255`；三层输出同尺寸 | 已确认 |
| 课程边界规则 | stride=1；Conv1/Conv3 replicate-edge radius 4/2；Conv2 radius 0 | 已确认；zero-pad/valid 仅保留作内部回归 |
| 课程浮点顺序 | bias-first MAC；Conv1/2 ReLU；Conv3 无激活/clamp | 官方参考数据与提交版本一致 |
| 预处理 | CNN 前 bicubic，kernel 接收已放大的单通道 `255×255` tensor | 已确认；灰度/Y 的 host 转换仍待确认 |

未关闭项目：

| ID | 待确认项 | 当前处理 | 解除条件 |
|---|---|---|---|
| `S0-B1` | 单通道是灰度还是 RGB→YCbCr 的 Y | 不在 core 内静默转换；不阻塞 HLS core | 教师书面答复或 host reference |
| `S0-B2` | ~~输入是否已 bicubic 到目标尺寸~~ | **已关闭：**kernel 输入已 bicubic，固定 `255×255` | Canvas Project Overview + starter |
| `S0-B3` | ~~bias MAC 顺序~~ | **已关闭：**正式采用 bias-first executable contract | 官方参考数据 + 已提交 Golden |
| `S0-B4` | 正式权重、输入范围、校准图像与 HR ground truth | Golden 阶段已用正式资产验证，但这些资产未保存在当前工作树；HR 评价细节仍待确认 | P2.2a 可完成；恢复正式资产后执行 P2.2b |
| `S0-B5` | ~~stride/padding/boundary/batch/core layout~~ | **已关闭：**N=1、255×255、stride 1、replicate-edge、CHW/OIHW/O | Canvas + starter + Golden 验证 |
| `S0-B6` | Conv3 后 crop/round/clamp/反归一化 | 不放入 Conv3 | 明确 host 后处理契约 |
| `S0-B7` | 课程正式误差阈值及 PSNR/SSIM 要求 | oracle 容差与实现容差分离 | rubric/教师确认 |

上表是当前进度关键项的摘要，不是完整 TBD registry。权重/bias 序列化与驻留方式、
I/O dtype/layout/endianness、AXI/control/runtime-size/reset、允许的 HLS 资源，以及 CPU
baseline、co-sim/power、benchmark 和 Canvas 提交要求，仍以 `spec.md §11.1–§11.3`
的完整清单为准；阶段关闭时必须逐项核对，不能只关闭 `S0-B1..B7`。

### 决策与偏离台账

| ID | 日期 | 决策/当前状态 | 来源 | 影响范围与复核条件 |
|---|---|---|---|---|
| `D-001` | 2026-09-10 | P1 dump、oracle 门禁和分层容差冻结 | 用户项目记录 + 仓库证据 | P2/P3 不得暗改；只有 blocker 改变语义时统一重基线 |
| `D-002` | 2026-09-10 | 算术层与结构层物理分离，P2.1 先做 dual-target/no-pragma 骨架 | 用户明确指示 | 已在 P2.1 落地；结构改动不得顺带改变量化策略 |
| `D-003` | 2026-09-10 | 直接实现目标结构，用逐项反向关闭生成消融 | 用户明确指示 | 改变 spec §7.4 的开发顺序；P2.3 前按 spec §12 登记，Final 仍覆盖 §9.5 七类 |
| `D-004` | 2026-09-10 | 原 fallback：若无答复则按 Y + bicubic 推进 | 用户明确给出的 fallback | **部分被 D-006 取代：**bicubic 已确认；灰度/Y 仍只影响 host 预处理 |
| `D-005` | 2026-09-11 | 原 bias-first/bias-after 冲突暂不裁决 | 冻结实现与文字规格冲突 | **已被 D-007 关闭** |
| `D-006` | 2026-10-05 | 课程 core 契约冻结为单帧 `255×255`、bicubic 后输入、stride 1、replicate-edge、CHW/OIHW/O | Canvas Project Overview + Golden starter | P2/P3 正式路径不得继续使用 zero padding 或 runtime 小尺寸冒充部署版本 |
| `D-007` | 2026-10-05 | bias-first 成为 executable float contract | 官方参考数据逐项交叉验证 + 已提交 Golden | 关闭 D-005；无需重做 P1，P2.2 可启动 |
| `D-008` | 2026-10-05 | Golden ZIP 已提交，提交版本冻结 | 用户确认提交 | 后续改动进入 HLS/host 分支，不覆盖提交包 |

### 实际输出

- [`spec.md`](./spec.md) v1.0；
- 冻结 tensor 格式 [`docs/tensor-format.md`](./docs/tensor-format.md)；
- P2.1 的集中占位/TBD 配置
  [`hls/include/srcnn_hls/project_config.hpp`](./hls/include/srcnn_hls/project_config.hpp)。

### S0 完成门

- 会改变正式输出语义、buffer 大小或 host/kernel 接口的项目均获得课程级答案；
- 正式权重、输入和 ground truth 有版本与 checksum；
- kernel 功能语义已经写回 `spec.md`；部署接口与计时边界继续显式关闭；
- 最终 DMA、计时和报告边界得到确认。

---

## P0 — 工具链贯通 ⏸️ [BLOCKED — 最高优先级]

P0 是当前外部关键路径。主力 Mac 无法运行 Vivado/Vitis；需要实验室或队友的
x86_64 Linux/Windows 工具机，P0c 还需要 KV260。

### 实际状态

| 子阶段 | 目标 | 当前状态 | 已有产物 | 缺失证据 |
|---|---|---|---|---|
| P0a | dummy kernel csynth + export IP | ⏸️ BLOCKED | P2.1 Vitis Tcl/Make 入口已备，part/clock fail-closed | 工具版本、确切 part/clock、csynth/export 报告 |
| P0b | Vivado BD + bitstream | ⏳ TODO | 无 | BD、`.bit/.hwh`、implementation/timing report |
| P0c | PYNQ overlay + AXI DMA dummy 收发 | ⏳ TODO | 无 | host 脚本、板上 log、重复加载与收发结果 |

### 计划产出

- 约 20 行的 `out[i] = in[i] + 1` dummy kernel；
- 确认的 Vitis/Vivado/PYNQ/KV260 镜像版本组合；
- 可复用 Vivado BD 和 PYNQ DMA host 骨架；
- exact part、target clock、actual clock；
- base overlay/AXI/DMA 占用后的 kernel 实际 DSP/LUT/FF/BRAM/URAM 预算；
- DMA width、packing、alignment、cache、TKEEP/TLAST、reset、timeout 契约；
- dummy 的板上逐元素一致性与可重复 overlay reload 记录。

### 完成标准

- P0a：csynth 与 export IP 成功，保存版本、command、report 和失败记录；
- P0b：bitstream 生成且 post-implementation timing closure，无阻塞性 DRC；
- P0c：板上 DMA 收发逐元素一致，可重复加载 overlay 而无需重启板子；
- 资源预算来自实际 overlay report，不使用 K26 器件总量
  `1248 DSP / 117120 LUT / 144 BRAM` 代替；
- DDR 只记录实测有效带宽，不能把约 19.2 GB/s 理论峰值当成结果。

### 近期动作

本周必须问清并记录：实验室机器预约方式、Vitis/Vivado 版本、KV260 借用政策、
PYNQ 镜像、队友可用时段和是否允许保存完整工程/报告。代码线走在计划前面，
工具链线仍接近零，不能等到 P2.3 才处理。

### 主要风险

- 免费版本覆盖器件，但缺少兼容 x86 工具环境；
- `.bit/.hwh` 或 platform 版本不匹配；
- dummy C-sim 正确但 DMA 因 TLAST/length/cache 首传即 hang；
- 没有保存完整报告，回到 Mac 后无法分析 II 或端口冲突；
- 为赶时间跳过 dummy，导致 SRCNN 数值和系统集成错误混在一起。

---

## P1 — Golden Reference ✅ [DONE — 课程提交 + 内部回归冻结]

### 实际实现

| 能力 | 实际产物 |
|---|---|
| 三层顺序 float32 SRCNN、单层/完整推理 | `src/srcnn.cpp`、`include/srcnn/srcnn.hpp` |
| CHW/OIHW/O loader 与形状/元素数校验 | `src/tensor_io.cpp`、`include/srcnn/tensor_io.hpp` |
| 短读、多读、layout、checksum 错误拒绝 | loader + unit tests |
| 统一 input/conv1/conv2/conv3/output dump | `docs/tensor-format.md` |
| 独立标准库 oracle | `tools/cross_validate_golden.py` |
| 向量生成与运行工具 | `tools/srcnn_vector_gen.cpp`、`tools/srcnn_run.cpp` |

### 测试和验证结果

- 14/14 单元测试通过；覆盖手算、impulse、sparse OIHW、signed/ReLU、中心/边/角、
  最小尺寸与 13×13 valid 端到端用例；
- 普通构建和 ASan/UBSan 构建通过；
- 独立 Python oracle 不 import/调用 C++，按 `spec.md §3.1` 重新实现索引与公式；
- parser 会重算 FNV-1a，证明读到的 float32 与 dump 逐位一致；
- `-ffp-contract=off` 下 O0 与 O3 逐位一致；CMake 拒绝 fast-math；
- 工具链 fingerprint 写入 vector manifest。

冻结的五套向量：

| 向量 | padding / 尺寸 | seed | 用途 |
|---|---|---:|---|
| `fixed_seed` | same / 13×17 | 1592594996 | 基础固定随机回归 |
| `fixed_seed_valid` | valid / 13×17 | 1592594996 | 与 same 共输入/权重的边界对照 |
| `cosim_33x29` | same / 33×29 | 20260910 | 非方形、非 2 的幂 HLS stimulus |
| `cosim_33x29_valid` | valid / 33×29 | 20260910 | valid 边界与尾部对照 |
| `naive_15x13` | same / 15×13 | 987654321 | naive/消融微型向量 |

oracle float32 容差已按层冻结：

| 层 | `atol` | `rtol` | 原因 |
|---|---:|---:|---|
| Conv1 | `2e-5` | `1e-4` | 81 项累加噪声底约 10×裕量 |
| Conv2 | `1e-4` | `1e-4` | 64 项累加且输入来自 Conv1 |
| Conv3 | `2e-3` | `1e-4` | 800 项累加，噪声结构性更大 |

`TOL_IMPL_VS_GOLDEN` 仍是 P2.2 占位，绝不复用 oracle 容差。

### 实际输出与证据

- P1 frozen inventory：`results/p1-frozen-before-p2_1.sha256`，76/76 项通过；
- 五套 `vectors/**`、逐层 dumps、run manifests 和 model tensors；
- 所有 P1 文件在 P2.1 后复核未变。
- 课程提交源码：`submission/golden_reference_src/{conv1.cpp,srcnn.cpp,srcnn.h}`；
- 提交 ZIP：`submission/ELEN90096_SRCNN_Golden_Reference_2026-10-05.zip`；
- 官方 Butterfly Conv1 MSE `3.23504e-15`，端到端 MSE `2.90284e-14`；
- 2026-10-05 用户确认已在 Canvas 提交。

### 计划偏离与遗留门

早期文字规格中的“MAC 完成后加 bias”与冻结实现的 `sum=bias; sum+=products` 在数学上
等价，但 binary32 低位可能不同。官方参考输出验证提交版 bias-first 顺序，因此该冲突
已在 `spec.md` v1.0 正式关闭。内部 valid/zero-pad 小尺寸向量继续作为索引回归，
但课程 HLS/板级正式路径只采用 `255×255 + replicate-edge`。

---

## P2 — HLS 实现 🟡 [PARTIAL]

### P2.1 — dual-target 骨架 ✅ [DONE — host verification]

#### 实际实现

| 文件 | 作用 |
|---|---|
| `hls/include/srcnn_hls/project_config.hpp` | 网络拓扑、TBD/占位值、动态范围、override 单一入口 |
| `hls/include/srcnn_hls/numeric_config.hpp` | float/fixed 切换、raw-code 上界和逐层 accumulator 推导 |
| `hls/include/srcnn_hls/arithmetic.hpp` | MAC、bias 兼容顺序、ReLU、narrowing |
| `hls/include/srcnn_hls/srcnn_hls.hpp` | host diagnostic 与 synthesizable top 契约 |
| `hls/src/srcnn_hls.cpp` | 自然循环 `o→oh→ow→i→kh→kw` |
| `tests/test_hls_float_vectors.cpp` | 五向量逐位门禁、范围检查、gap 输出 |
| `tests/test_hls_fixed_smoke.cpp` | fixed 类型/宽度回归、zero 与 sparse smoke |

结构层与算术层已经物理分开。HLS library 强制 C++14；核心不使用动态内存、递归、
不定界循环或异常。当前 `hls/` 下 **0 条 `#pragma HLS`**，包括接口 pragma 也未添加。

#### 当前结构占位配置

| 项目 | 当前值 | 含义 |
|---|---:|---|
| deployment `H0/W0` | `255/255` | 已按课程正式输入尺寸重基线 |
| host/部署尺寸上限 | `255×255` | 小尺寸向量仍合法；课程部署只采用 255×255 |
| Conv1/2/3 UNROLL | `1/1/1` | 未被 pragma 使用，不能解释为综合后的并行度 |
| line-buffer rows | `8/0/4` | 仅按 `K-1` 记录未来形状，尚未实现 line buffer |
| tile | `255×255` | 当前仅记录完整部署帧；P2.3 是否流式/分块仍待 csynth |

#### 当前占位数值配置

`data_t = ap_fixed<32,24,AP_RND_CONV,AP_SAT>`，即 8 位小数。该配置只保证当前
安全链路和手算向量可表示，不是性能选择。

| 层 | N | MAC bound | bias-inclusive bound | derived `ACC_I` | `ACC_W` | override |
|---|---:|---:|---:|---:|---:|---|
| Conv1 | 81 | 81 | 82 | 8 | 24 | off |
| Conv2 | 64 | 5,248 | 5,249 | 14 | 30 | off |
| Conv3 | 800 | 4,199,200 | 4,199,201 | 24 | 40 | off |

推导使用量化后的 raw code，把 bias 和 signed `ap_fixed` 正端点少 1 LSB 都纳入，
避免恰好为二次幂时少一位。accumulator 保留完整乘积小数位；显式 override 默认关闭。

#### 验证结果

- 五套向量的 diagnostic path 与 `srcnn_hls_top` 分别使用独立 buffer；top buffer
  预填 NaN，Conv1/2/3/final 全部逐元素 bitwise PASS；
- 输入、权重、bias 和中间输出先验证未超过配置范围，再报告 worst-case；
- fixed 路径锁定 `width/iwidth/qmode/omode`，覆盖 exact-power、bias、zero、override
  宽度回归以及可手算 sparse 非零路径；
- Release 下 float/fixed host gates 与 fixed C++14 compile 通过；ASan/UBSan 下通过的
  范围是 P1 unit tests 和五向量 float gate，不含 fixed smoke；
- P1 frozen checksum、P2.1 source checksum 和可恢复 tar snapshot 均通过。

当前五向量占位 gap：

| 层 | observed preactivation `abs_max` | safe bound / observed |
|---|---:|---:|
| Conv1 | 13.45200 | 6.095749× |
| Conv2 | 44.20818 | 118.7337× |
| Conv3 | 341.9849 | 12,278.91× |

这些数字来自随机权重，只证明流程有效；不能用于 OPT-D 收紧位宽。

#### 实际输出

- 设计说明：`docs/p2_1-dual-target.md`；
- 验证记录：`results/p2_1-host.md`；
- source identity：`results/p2_1-source.sha256`；
- 完整可恢复快照：`results/p2_1-complete-source.tar.gz` 及相邻 checksum；
- Mac/CMake 入口、host fixed 入口和 fail-closed Vitis Tcl/Make 入口。

#### 尚未完成（不属于 P2.1 host DONE）

| 指标 | 状态 |
|---|---|
| Vitis C-sim / csynth / export IP | NOT RUN |
| RTL co-sim | NOT RUN |
| latency / II / schedule | NOT MEASURED |
| DSP / LUT / FF / BRAM / URAM | NOT MEASURED |
| target/actual clock | NOT CONFIRMED / NOT MEASURED |
| implementation timing closure | NOT RUN |

---

### P2.2 — 定点误差 harness 🟡 [PARTIAL — P2.2a DONE]

P2.1 host 骨架已确认。2026-10-06 已在 Mac 完成 P2.2a：实现独立 fixed-vs-float
harness、逐层指标、源量化/层间窄化饱和计数，并跑通全部五套冻结随机向量。
课程版 Golden ZIP 未修改。正式 weights/课程图像当前不在工作树，因此 P2.2b 尚未运行。

P2.2 分为两个门：`P2.2a` 是既有随机资产上的 harness 机制回归；`P2.2b` 是正式
weights、`[0,1]` 输入、课程图像和实现判据下的 deployment numeric freeze。只有两者都通过，
P2.2 才能整体标为 `[DONE]`；`P2.2a` 单独通过最多只能把本阶段推进到 `[PARTIAL]`。

#### 计划产出

- 五套向量的 fixed-point vs float Golden 逐层比较；
- 每层 max-abs、max-relative、MAE、RMSE、relative-L2 和误差分布；
- FPGA 实现相对 float Golden 的 PSNR；必要时 SSIM；
- saturation/overflow 事件、零点翻转、违规数、最差 `(c,h,w)` 和坐标直方图；
- 操作数声明范围与实际 `abs_max` 校验；
- 用观察到的误差形态填充并冻结 `TOL_IMPL_VS_GOLDEN`；
- 正式权重、课程输入和 float Golden 的 manifest、checksum 与原始结果。

#### P2.2a 实际证据（2026-10-06）

- 新增 `tests/test_hls_fixed_vectors.cpp`，覆盖五套向量并输出 max-abs、max-relative、
  MAE、RMSE、relative-L2、`R=1` PSNR、zero flips、最差 CHW 坐标；
- 新增源量化和每层 `data_t` narrowing 饱和计数；五套向量全部为 0；
- relative-L2 范围：Conv1 `0.25499%–0.27560%`、Conv2 `0.28420%–0.35468%`、
  Conv3 `0.27088%–0.62282%`；
- 最大观测 pre-activation：Conv1 `13.4417`、Conv2 `44.1651`、Conv3 `341.645`；
- 新增 replicate-edge 单元测试：1×1 全一输入、9×9 全一 Conv1 在 replicate-edge
  下角点为 `81`，zero-pad 下为 `1`，非法 padding selector 被拒绝；
- Xilinx host AP types 固定到 commit
  `200a9aecaadf471592558540dc5a88256cbf880f`；
- `ctest -L fixed`：2/2 通过；完整解释见 `results/p2_2a-fixed-random.md`。

`R=1` PSNR 对这些输出幅值可超过 300 的随机权重只作为回归字段，不是图像质量结论。
P2.2b 恢复正式资产后才能冻结 deployment 位宽和 `TOL_IMPL_VS_GOLDEN`。

#### 完成标准

- 判据在看最终候选结果前按证据校准，禁止为了让某版本通过而放宽；
- 所有五套向量逐层运行，失败分类完整；
- 随机权重结果明确标为 placeholder，不用于宣称真实图像质量；
- bias 顺序与 float reference 唯一且明确；
- harness 与数值策略分离，P2.3 改循环/端口不需要重新设计误差统计；
- 使用正式 weights、`[0,1]` 输入和课程图像完成 `P2.2b`，再冻结部署用
  `data_t/acc_t`；若课程未给出硬阈值，工程阈值必须在比较最终候选前基于图像质量目标冻结。

#### 主要风险

- 把 oracle float 容差当成 fixed 容差；
- 只看 raw max error，不看 PSNR、分布、零点翻转和饱和；
- `AP_SAT` 被误认为自动提供事件计数；实际需要更宽 shadow value 在 narrowing 前比较；
- 官方权重替换后忘记同步动态范围配置；
- 随机权重下很好看的结果被误写成正式结论。

---

### P2.3 — 目标 HLS 结构实现 🟡 [PARTIAL — line-buffer host 原型通过，csynth 仍阻塞]

按用户 2026-09-10 的明确决策，不以 naive → pipeline → unroll → line buffer 的
顺序逐级开发，而是直接实现 MVP 目标结构，再逐项反向关闭 pragma/模块生成消融版本。
这改变 `spec.md §7.4` 规定的开发顺序，但不减少 `spec.md §9.5` 要求的最终对照类别；
进入 P2.3 前必须按 `spec.md §12` 把这项偏离写入规格变更记录。P2.1 的自然循环、
零 pragma 版本应先在 P0a 工具上独立 csynth 并冻结，形成真实 naive baseline，
而不是从目标版反推一个伪 baseline。

#### 2026-10-08 Mac 结构检查点

在独立分支 `optimize/line-buffer` 中新增 `srcnn_hls_line_buffer_top`，同时完整保留
`srcnn_hls_top` natural baseline。Conv1/Conv3 使用 circular row banks 与横向滑动
window；Conv2 使用直接 1×1 channel reduction。算术 helper、`data_t/acc_t`、bias-first
顺序和层间 narrowing 均未改变，且尚未添加 `PIPELINE/UNROLL/ARRAY_PARTITION`。

新增 float/fixed 双模式等价测试，覆盖 replicate-edge、zero-same、valid、1×1 与
33×29 非方形输入。首次测试发现 row-bank/channel 维度顺序错误并产生越界；修正为
`[row-bank][channel][column]` 后 Release 全套 7/7、ASan/UBSan 4/4 通过。详细证据见
`results/p2_3-line-buffer-host.md`。

此检查点只证明结构语义与内存安全，不证明综合可行性或性能；P2.3 仍不能标为 DONE。
下一步必须在 Vitis 中先保存 natural baseline，再综合 line-buffer top，读取 schedule、
memory-port、latency、II 与资源报告后才决定 pragma 和 banking。

#### 目标实现

- 正式资产下重跑 P2.2 后，采用通过 deployment numeric gate 的定点类型；
- Conv1 9×9 与 Conv3 5×5 line buffer/sliding window；
- Conv2 1×1 通道归约数据供给；
- 适度 `PIPELINE`；
- 按 P0a 实际 DSP/端口预算选择一组主 UNROLL，最多试两组；
- 必要的 `ARRAY_PARTITION`/banking 与局部 weight buffer；
- 针对固定 `255×255`（非 2 的幂、可能不整除 tile）决定 whole-frame streaming、tiling、halo 和尾块；
- 保留逐层输出或等价 debug 路径，确保能定位首个错误层。

三层并行空间不同：

| 层 | 主要并行维度 | 主要风险 |
|---|---|---|
| Conv1 | 64 输出通道 + 81 kernel MAC | 输入通道只有 1；adder tree 与 weight 端口 |
| Conv2 | 64 输入通道归约 + 32 输出通道 | 最容易吃满 DSP；partition/端口决定 II |
| Conv3 | 32 输入通道 + 25 kernel MAC | 输出通道只有 1；长归约和单层瓶颈 |

#### HLS 调试纪律

任何实际 II 高于目标时，先读取 schedule viewer、dependency 和 memory-port report，
确认是 loop-carried dependency、数组端口、operator latency 还是 routing 压力，再改代码；
不得只靠 RTL 直觉猜 pragma。

#### 完成标准

- C-sim 逐层满足 P2.2 冻结判据；
- `cosim_33x29` 完成目标版 RTL co-sim；`naive_15x13` 只用于 naive/消融版本的快速
  correctness/co-sim smoke，不用于性能或 speedup 横向比较；
- csynth 报告完整记录 latency、II、clock、DSP/LUT/FF/BRAM/URAM；
- 实际并行因子有 DSP 和 memory-port 计算依据；
- 不超过 P0a kernel 工程预算；
- 在目标版之前先保存 P2.1 natural/no-pragma 的独立 baseline 报告；
- MVP 至少保存目标版和三个逐项反向消融版本；Final Report 仍覆盖 `spec.md §9.5`
  的七类对照，失败项保留失败原因；
- 所有用于 latency、throughput、资源和 speedup 的横向版本使用同一正式输入尺寸、
  权重、dtype、clock constraint 与测量边界；
- 第一次 csynth 后允许改结构，但算术策略不随结构修改漂移。

#### 主要风险

- 完整中间 feature map 无法全部驻留 BRAM，必须 streaming 或 tiling；
- 看起来可 pipeline 的循环因端口冲突达不到目标 II；
- 展开过大导致 DSP 超限或 timing/routing 崩溃；
- line-buffer warm-up/flush、replicate-edge、tile halo 或尾块 off-by-one；
- FIFO 深度拍脑袋，C-sim 通过但 co-sim/板上死锁；
- 在没有 x86 报告的 Mac 上提前“优化”结构，形成无法验证的复杂代码。

---

## P3 — KV260 板级部署与测量 ⏳ [TODO]

### 计划执行

- 复用 P0 BD 模板，把 dummy IP 替换为 SRCNN kernel；
- 生成并绑定匹配的 `.bit/.hwh`；
- PYNQ host 完成 overlay load、物理连续 buffer、packing、DMA send/recv、
  cache flush/invalidate、start/wait/timeout；
- 板上 smoke、五向量/正式向量正确性、重复运行和连续多帧稳定性；
- 一次性批处理保存逐层/最终 dump、字节数、TLAST、timeout 和所有计时数据；
- 实测 DMA 有效带宽；
- 保存 post-implementation utilization、WNS/TNS、actual clock 和 DRC。

### 计时边界

必须分别报告：

1. host 预处理；
2. PS→PL DMA；
3. kernel-only（仅在有可靠 start/done 或 cycle counter 时）；
4. PL→PS DMA；
5. host 后处理；
6. device-path；
7. 完整 end-to-end。

若 `transfer/wait` 同时覆盖 DMA 与 streaming kernel，只能标为 `DMA + kernel` 或
`device-path latency`，不得命名为 kernel-only。

### 完成标准

- 板上输出通过冻结的逐层/最终判据；
- `.bit/.hwh` 和 source identity 一致；
- 多次 overlay reload、重复帧和连续帧无 hang 或残留状态；
- post-implementation timing closure；
- 所有时间有 warm-up、重复次数 `N`、mean/median/std，必要时 p95；
- 计时和传输原始 log 可追溯；
- 至少产生 kernel-only（若可测）和 end-to-end/device-path 两种诚实结果。

### 主要风险

- 物理连续性、cache coherence、alignment、word packing、TKEEP/TLAST 任一错误导致 hang；
- 第一次板测失败时没有 batch diagnostics，错过有限板卡时间；
- host 与 PL 对 CHW/packing 理解不同；
- 用 Linux wall-clock 单次最优值代替稳定统计；
- HLS estimated clock 被误写成板上 actual clock。

P3 已错过原 2026-10-05 内部目标，现为 Final Report 的最高风险路径。以实际工具/板卡
可用性尽快推进，但不能通过编造结果或跳过 dummy 链路“追日期”。

---

## P4 — 基准、Status Update 与 Final Report 🟡 [PARTIAL]

2026-10-06 已完成 Status Update 的 8 页可编辑 PPTX、逐页讲稿备注和 Canvas
提交用 PDF。内容覆盖算法、硬件适用性、目标架构、Golden/P2.2a 实测进展、证据边界、
风险和剩余任务；所有尚无工具/板卡证据的指标明确标为 `NOT MEASURED`。团队姓名、
实际讲述分工和后续获得的 csynth 结果仍需在提交前更新。

### 计划产出

- 与 FPGA 使用相同输入、权重、算法语义、精度边界和预/后处理的 CPU baseline；
- kernel-only、device-path、end-to-end 三类时间与各自同边界 speedup；
- 单帧 latency 与连续 `N` 帧实际 throughput；
- MVP 至少有目标版加三个可复核消融版本；Final Report 的表覆盖 `spec.md §9.5`
  所列 naive、numeric、PIPELINE、UNROLL+PARTITION、line buffer/tiling、DATAFLOW 和
  final board 七类，失败优化也作为一行保留；
- post-implementation 绝对资源、可用预算、百分比、WNS/TNS；
- FPGA-vs-float 实现误差，与 HR ground truth 的算法 PSNR/SSIM 分开；
- architecture/dataflow/timing 图、原始 CSV/log/report；
- Status Update 口头材料；
- Final Report、HLS 源码、PYNQ host 和 rubric 要求的 overlay/复现材料。

### 测量纪律

- `speedup = CPU 时间 / FPGA 时间`，只比较相同工作边界；
- 禁止 CPU end-to-end 对 FPGA kernel-only；
- throughput 使用连续多帧完成率，不用单帧 latency 的倒数；
- GOPS/MAC/s 必须声明一个 MAC 计为 1 还是 2 operations；
- 资源必须注明 post-synthesis 或 post-implementation；
- 功耗无法可靠测量就写 `NOT MEASURED`；
- 每个关键数字都能从保存的原始文件复算。

### Status Update 完成门（2026-10-12）

- 10 分钟 slides + 5 分钟 Q&A，所有成员在前 10 分钟内承担有技术内容的讲述；
- slides 覆盖算法概述、硬件加速适用性分析、带图表/数据的当前进展、剩余任务与
  anticipated results；演讲后仅以 PDF 上传；
- 个人 3 分：表达清楚，视觉材料确实增强口头说明；
- 团队 Solution Design 5 分：方案与项目约束明确相连，有结构化计算、分析、仿真或
  实验支撑，并清楚说明实现和测试程序；
- 团队 Discussion/Justification 2 分：把理论、仿真与实验串联，主动说明局限、风险
  和剩余工作；
- 任何 latency/II/clock/resource/FPS 必须标明 `MEASURED` 或 `PREDICTED`；截至汇报仍
  未获得的数据写 `NOT MEASURED`，不得用估算冒充工具或板级结果。

### 课程里程碑

| 里程碑 | 日期* | 权重 | 当前 readiness | 尚缺 |
|---|---|---:|---|---|
| Golden Reference | 2026-10-05 | 5% | ✅ 已提交 | 保留 submission receipt；提交包冻结 |
| Status Update（10 分钟汇报 + 5 分钟 Q&A） | 2026-10-12 23:59 PDF 截止 | 10% | 🟡 deck 与 PDF 已生成 | 填团队姓名/分工；若 P0a 及时完成则加入 csynth 数据 |
| Final Report | 2026-10-19 | 25% | ⏳ 未就绪 | 板级闭环、完整指标、报告与提交包 |

\* 日期来自 lecture/当前项目记录，最终以 Canvas 为准。Status Update 权重高于
Golden，应作为独立里程碑准备，不能等最终报告时顺便整理。

---

## MVP 完成门

任何 OPT 项在以下条件全部满足前不得启动：

- P1 Golden 全回归通过并保持冻结；
- HLS 定点版本包含 `PIPELINE + line buffer + 适度 UNROLL`；
- HLS 每层与 Golden 通过冻结判据；
- KV260 板上正确运行；
- kernel-only（若硬件可分离）与 end-to-end/device-path 计时完整；
- post-implementation utilization、actual clock 和 timing closure 完整；
- 消融表至少三行；
- 局限性和未测项目诚实记录。

判断原则不变：一个上板、数据完整、分析诚实的中等优化设计，优先于一个没有板级
闭环的高度优化 HLS 设计。

---

## OPT 清单 ⏭️ [DEFERRED — MVP 后按序]

### 优先级 1

- **OPT-B（可选背景讨论，不是 SRCNN 消融项）：**比较手写 RoCC 紧耦合与 HLS/AXI
  松耦合的开发范式。只有能提供既有项目的原始报告、工具/平台、算法规模、精度和
  测量边界时，才可引用其开发时间、资源或 speedup；不可与本项目作无同边界的数值
  优劣比较，也不可把它计入 SRCNN 的七类消融。
- **OPT-C：**跨层 DATAFLOW。必须处理 FIFO 深度、生产/消费率、frame boundary、
  static state reset；失败实验与原因保留。

### 优先级 2

- **OPT-D：**定点位宽 sweep；正式权重下比较逐层误差、资源与 latency。
- **OPT-E：**UNROLL 因子 sweep；在实际 kernel 预算约 30%/60%/85% 三档形成曲线。
- **OPT-F：**tiling 与非整除尾块；只有 BRAM/streaming 需求证明必要时才展开。

### 优先级 3

- **OPT-G：**HR ground truth 图像质量；与 FPGA-vs-float 实现误差分开。
- **OPT-H：**功耗/能效；不能可靠测量则写 `NOT MEASURED`。
- **OPT-I：**连续多帧 streaming。
- **OPT-J：**URAM；仅在 BRAM 被证明为瓶颈时。
- **OPT-K：**全尺寸 RTL co-sim；默认只做 C-sim 和板测。

---

## 工作纪律

1. 每完成一个阶段停下等待确认，不自动进入下一阶段。
2. 任一版本未通过与 Golden 的逐层比较，不进入下一步。
3. 容差变更必须区分“无论是否出现违规都认为原容差错误”的校准，和只为让当前
   版本通过的迁就；后者禁止。
4. 从第一个 HLS 报告开始记录 latency、II、clock、LUT/FF/DSP/BRAM、正确性；
   没有报告时明确写 `NOT MEASURED`。
5. 每个通过门禁的版本独立保存，不覆盖前一版本；source identity、配置、工具版本、
   seed、weights checksum 和原始结果一起保存。
6. 位宽、展开因子、FIFO 深度和 tile 尺寸必须附推导或工具证据。
7. 失败实验保留并记录症状、根因、修改和回归结果。
8. 既有随机权重产生的动态范围、gap 和量化误差都是 placeholder；P2.2 必须用已经到位的正式权重重测。
9. HLS 的 II 异常先看 schedule/dependency/port report；板级 DMA 异常先看 length、
   packing、TLAST、cache、timeout 和 reset 记录。
10. 算术层和结构层保持物理分离；调整循环/端口/line buffer 不应顺手改数值策略。

---

## 完成状态总览

```text
S0     🟡 PARTIAL  — spec v1.0 已冻结课程 core；DMA/clock/资源预算/颜色后处理仍待确认
P0a    ⏸️ BLOCKED — 等待 x86 Vitis、part、clock；尚无 csynth/export
P0b    ⏳ TODO    — 尚无 Vivado BD/bitstream
P0c    ⏳ TODO    — 尚无 KV260 overlay/DMA dummy 板测
P1     ✅ DONE    — 课程 Golden 已验证并提交；内部回归资产继续冻结
P2.1   ✅ DONE    — dual-target host 骨架、bitwise gate、fixed smoke 完成
P2.2   🟡 PARTIAL — P2.2a 五向量 harness/饱和统计完成；P2.2b 等正式资产恢复到本机
P2.3   🟡 PARTIAL — line-buffer host 等价/安全通过；csynth、pragma 与正式数值 gate 未完成
P3     ⏳ TODO    — PYNQ/DMA/bitstream/板级正确性与计时未开始
P4     🟡 PARTIAL — Status Update deck/PDF 已生成；baseline、消融、Final Report 未完成
OPT    ⏭️ DEFERRED— MVP 前禁止启动
```

---

## 实际 vs 旧 plan v0.1 差异

| 维度 | 旧计划 | 当前实际/决策 | 原因与影响 |
|---|---|---|---|
| 文档性质 | 全前瞻草案，声称尚未写代码 | living execution record | P1、P2.1 已有可审计产物 |
| 工具链顺序 | 先 HLS baseline 再逐步优化 | P2.1 host 先完成，P0 仍并行最高优先 | Mac 可验证算术，不能替代 x86/板卡 |
| HLS 演进 | naive→PIPELINE→UNROLL→line buffer→DATAFLOW | natural baseline 单独 csynth；随后直接实现 MVP 目标并反向生成消融 | 用户 2026-09-10 决策；进入 P2.3 前按 spec §12 同步，最终仍交七类对照 |
| 定点位宽 | 多组 sweep | 默认 worst-case 自动推导；OPT-D 才 sweep | 当前先保证安全，正式权重后再收紧 |
| UNROLL | 完整设计空间探索 | 预算计算后选一组，最多两组 | 板卡/工具时间有限 |
| line buffer | 多方案比较 | 直接采用 sliding window | 架构方向已知 |
| 数值/结构 | 同一阶段逐步修改 | 物理分离 | csynth 后改结构不重新设计算术 |
| padding/stride | 等课程完全冻结 | 课程正式契约为 stride 1、replicate-edge、255×255；内部 same/valid 仅作回归 | P2/P3 正式结果不得使用旧 zero-pad 语义 |
| bias 顺序 | 文字规定 MAC 后加 bias | 官方输出确认 bias-first executable contract | 冲突已关闭，P2.2 可启动 |
| 版本保存 | 建议使用稳定标签 | SHA256 inventories + 完整 tar snapshot | 当前目录不是 Git 仓库 |
| 性能数据 | 从第一 HLS 版开始记录 | 暂无 Vitis 数据，全部标 NOT MEASURED | 避免把 host 时间/估算写成硬件结果 |

---

## 当前停止点与下一允许动作

Golden 已提交，课程 core 契约与 bias 顺序已关闭。接下来按以下顺序并行推进：

1. **Mac 主线：完成 P2.2b。**P2.2a 已完成；把 Golden 阶段使用的正式 weights、
   `[0,1]` 课程输入和官方输出恢复到本机后，接入现有 harness，冻结动态范围、
   overflow、逐层误差和图像域 PSNR/SSIM 约定。
2. **P0 外部关键路径：立即落实 x86 Vitis。**确认工具版本、part、clock 和板卡时段；
   先做 dummy P0a，再保存 natural SRCNN baseline 的 csynth/schedule/resource 报告。
3. **Status Update：从 2026-10-06 起同步收集证据。**优先准备 workload 计算、架构图、
   Golden MSE、定点误差和首份 csynth；其中 255×255 workload 计算已完成于
   `results/workload-analysis-255x255.md`，未测指标必须标 `NOT MEASURED`。
4. **P0a 与 P2.2 通过后继续 P2.3 综合优化。**Mac line-buffer 原型已通过等价门；后续
   `PIPELINE/UNROLL/ARRAY_PARTITION` 必须由 schedule、dependency 与 memory-port 报告
   驱动，不在 Mac 上凭直觉宣称 II 或资源结果。

已提交 Golden 和冻结 oracle 不再修改；P2.2/P2.3 的新代码必须以它们为只读参考。
