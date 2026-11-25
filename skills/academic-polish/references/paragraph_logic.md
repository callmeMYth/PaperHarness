# 段落逻辑调整指南

> 中文段落常见「铺垫在前、观点在后」「多线并行」「逻辑靠语序」；英文期刊段落要求「观点先行、一段一主题、逻辑显式」。
> 调整原则：**只重排和显化，不新增论点，不删除事实**。每次调整都要在对照表里写明理由。

## 1. 英文学术段落标准结构
1. **主题句**（Topic sentence）：段首直接给出本段核心观点。
2. **支撑**（Support）：证据、解释、数据、引用。
3. **收束 / 过渡**（Wrap-up / Transition）：小结本段或引出下一段。

## 2. 常见中文段落问题 → 调整方法
| 问题 | 识别信号 | 调整 |
|---|---|---|
| 观点后置 | 段尾才出现"因此/综上/本文" | 把结论句提到段首作主题句，原铺垫作支撑 |
| 一段多主题 | 段中出现"此外"引出全新话题 | 拆成两段，或把次要话题压缩为一句 |
| 逻辑跳跃 | 前后句之间缺因果/转折 | 补充连接词或过渡短语（不补事实） |
| 重复论述 | 同一意思换说法出现两次 | 合并，保留信息量更大的一句 |
| 背景过长 | 引言前 3 句都是宏观背景 | 压缩为 1 句，尽快进入具体问题 |

## 3. 各章节的段落模板

### Abstract（单段，5–7 句）
背景(1) → 问题/现有不足(1) → 本文方法(1–2) → 关键设计(1) → 实验结果(含数据)(1) → 意义/代码(可选)

### Introduction（经典 CARS 模型）
1. 领域与任务的重要性（1 段，简短）
2. 现有方法及其局限（1–2 段，**局限要具体**）
3. 本文动机与核心思想（1 段）
4. 贡献列表：*Our main contributions are summarized as follows:* + 3 条 bullet（动词开头，平行结构）

### Related Work
按主题分小段，每段：类别概述 → 代表工作 → **与本文的区别**（段末必须点明）

### Method
概述（整体框架 + 引用图）→ 各模块（动机 → 设计 → 公式 → 作用）→ 训练目标

### Experiments
设置（数据集、指标、实现细节）→ 主结果（与 SOTA 比较，先结论后数据）→ 消融 → 可视化/分析

### Conclusion
总结方法(1) → 主要发现(1–2) → 局限与未来工作(1)；不引入新结果。

## 4. 示例
**原中文段落**（观点后置）：
> 现有方法大多采用固定大小的卷积核提取特征。然而，遥感图像中目标尺度变化很大。固定感受野难以同时兼顾大目标和小目标。因此，如何自适应地建模多尺度信息是一个关键问题。

**调整后英文**（主题句前置 + 逻辑显化）：
> Adaptively modeling multi-scale information is a key challenge in remote sensing image analysis. Most existing methods extract features with fixed-size convolutional kernels, yet objects in remote sensing images vary greatly in scale. As a result, a fixed receptive field can hardly accommodate both large and small objects simultaneously.

**理由**：将段尾结论提为主题句；用 *yet* 显化转折，用 *As a result* 显化因果。
