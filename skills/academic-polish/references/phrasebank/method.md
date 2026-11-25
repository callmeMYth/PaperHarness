# Method 学术句式库（深度学习论文）

> 高频动词（`we + V`）：`use` / `propose` / `introduce` / `define` / `apply` / `train` / `design` / `denote` / `compute` / `obtain` / `formulate` / `construct` / `sample`
> 时态：统一使用**一般现在时**。母语作者显著偏好 `we use` 而非过度重复 `we adopt`。

## 1. 整体框架与章节导览
- *In this section, we present **[Name]**, as illustrated in Figure [REF].*
- *We first formulate the problem in Section [REF], then detail [Module A] and [Module B], and finally describe the training objective.*
- *Our framework consists of two / three key components: (1) ..., (2) ..., and (3) ....*

## 2. 问题定义与符号声明
- *Let [MATH] denote the set of ..., where [MATH] represents [meaning].*
- *Given an input [MATH], our goal is to learn a mapping [MATH] that predicts [MATH].*
- *Without loss of generality, we assume that [condition].*
- *For simplicity, we omit the bias term / layer index where clear from context.*

## 3. 模块设计与公式引出
- *To capture [property], we compute [output] as follows:*
- *Formally, the [operation] can be formulated / expressed as:*
- *where [MATH] denotes ..., [MATH] is a learnable parameter, and [MATH] controls [hyperparameter role].*
- *Specifically / In particular, we feed [input] into [layer] to obtain [intermediate representation].*
- *Note that [important implementation/mathematical property], which ensures [benefit].*
- *In practice, we implement this operation using [standard layer] for computational efficiency.*

## 4. 训练目标与优化
- *We train the network end-to-end by minimizing the combined loss:*
- *where [MATH] balances the contributions of the two terms.*
- *During training, we [training-only operation]; at inference time, we [inference behavior].*
- *The complete training procedure is summarized in Algorithm [REF].*

## 避免中式表达
- ✗ *In this way, we can get better features.* → ✓ *This design yields more discriminative representations.*
- ✗ *We adopt a linear layer to do projection.* → ✓ *We apply a linear projection layer.*
