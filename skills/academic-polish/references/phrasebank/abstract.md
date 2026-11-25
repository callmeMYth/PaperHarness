# Abstract 学术句式库（深度学习论文）

> 高频动词（`we + V`）：`propose` / `introduce` / `present` / `show` / `demonstrate` / `design` / `provide` / `find` / `develop` / `evaluate` / `establish`
> 节奏：5–7 句单段，紧凑、不拖泥带水；**避免**以 *In recent years, ... has developed rapidly* 开篇。

## 1. 背景与任务定位（1 句）
- *Recent advances in [X] have enabled strong performance on [task], yet ...*
- *While [existing paradigm] has achieved remarkable progress in [task], [specific bottleneck] remains challenging.*
- *[Task] is a fundamental problem in [domain], requiring models to [core capability].*

## 2. 现有方法局限（1 句）
- *However, most existing methods rely on [assumption/cost], which limits their applicability to [scenario].*
- *Despite their success, current approaches struggle to [limitation] due to [root cause].*
- *Existing solutions either [trade-off A] or [trade-off B], leaving [gap] unresolved.*

## 3. 提出本文方法（1–2 句）
- *In this paper / work, we propose / introduce **[Name]**, a [concise description] that [key mechanism].*
- *To address this limitation / bridge this gap, we present **[Name]**, a simple yet effective framework for [task].*
- *Specifically / In particular, we design [component A] to [goal A], and [component B] to [goal B].*
- *Unlike prior methods that [old way], our approach [key difference] without requiring [extra cost].*

## 4. 实验结果与性能（1 句，尽量给具体数字）
- *Extensive experiments on [N] benchmarks demonstrate that **[Name]** consistently outperforms state-of-the-art methods, achieving [metric gain] on [dataset].*
- *We show that our approach improves [metric] by [X] percentage points over strong baselines while reducing [cost] by [Y]%.*
- *Empirical results across [tasks] show that **[Name]** generalizes well to [unseen setting].*

## 5. 代码与开源（可选，1 句）
- *Our code and pre-trained models are publicly available at `URL`.*
- *Code is available at `URL`.*

## 避免套话
- ✗ *With the rapid development of deep learning...* → 直接切入具体任务与瓶颈。
- ✗ *The experimental results verify the effectiveness and superiority of our proposed method.* → 用具体数据 + *We show that our method outperforms ... by X%.*
