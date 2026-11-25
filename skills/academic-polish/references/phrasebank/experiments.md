# Experiments 学术句式库（深度学习论文）

> 高频动词（`we + V`）：`use` / `compare` / `evaluate` / `observe` / `report` / `train` / `set` / `find` / `show` / `follow` / `present` / `test` / `visualize` / `analyze`
> 关键：先给结论再列数据；**避免**整段重复 *As shown in Table X, ... verifies the effectiveness of our proposed method*。

## 1. 实验设置与公平比较
- *We evaluate **[Name]** on [N] standard benchmarks: [A], [B], and [C].*
- *Following [CITE], we use [metric] as our primary evaluation metric and report the average over [N] random seeds.*
- *For a fair comparison, all models are trained with the same [backbone / data split / budget].*
- *We train all models for [N] epochs using AdamW [CITE] with an initial learning rate of [X], a batch size of [Y], and cosine decay.*
- *Further implementation details are provided in Appendix [REF].*

## 2. 主实验结果陈述（多样化表达，少用 *As shown in*）
- *Table [REF] summarizes the main results across all benchmarks.*
- ***[Name]** consistently outperforms all baselines, achieving a [X] percentage-point gain in [metric] over [best baseline].*
- *Notably, our method matches or exceeds [larger model] while using [Y]% fewer parameters / FLOPs.*
- *Relative to [baseline], **[Name]** reduces [error/latency] from [A] to [B].*
- *While [baseline] performs competitively on [easy split], its accuracy drops sharply on [hard split]; in contrast, **[Name]** maintains strong performance.*

## 3. 消融实验
- *To isolate the contribution of each component, we conduct an ablation study on [dataset] (Table [REF]).*
- *Removing [Module A] degrades [metric] by [X] points, confirming its role in [function].*
- *Adding [Module B] on top of [Module A] yields a further gain of [Y], indicating that the two components are complementary.*
- *We analyze the sensitivity to [hyperparameter] in Figure [REF] and find that performance remains stable across [range].*

## 4. 原因分析与定性可视化
- *This improvement can be attributed to [mechanism], which prevents [failure mode].*
- *We conjecture that this gap arises because [explanation].*
- *Figure [REF] visualizes qualitative comparisons on [dataset], showing that **[Name]** produces sharper / more accurate [outputs] than [baseline].*
- *These findings suggest that [broader takeaway].*
