# 华人作者 vs 英语母语作者：3,000 篇顶会语料实证高频偏差对照

> 来源：基于本插件 **2,987 篇**成功清洗的顶会/顶刊论文（华人地区 500 篇 vs 英语母语地区 2,500 篇含 1,400 篇 2022 年前零 LLM 污染基准，合计 **3,674 万词**）的 log-odds 统计与句首连接词频率对比。
> 用途：润色与中译英时重点排查这些**虽合语法、但显著偏中式模板或高频重复**的表达，使其更贴近英语母语研究者的真实写作习惯。

---

## 1. 句首连接词：过度使用 vs 母语偏好（每千句频次）

| 连接词 | 华人组 (500 篇) | 母语组 (2,500 篇) | 比值 (中/英) | 润色建议 |
|---|---|---|---|---|
| **Besides,** | 6.95 | 1.75 | **3.97×** | 偏口语；改为 `In addition,` / `Furthermore,` / `Moreover,` |
| **In this way,** | 1.80 | 0.51 | **3.54×** | 尽量删去或改用分词 `thereby + -ing` / `which enables...` |
| **Meanwhile,** | 2.78 | 0.94 | **2.96×** | 仅表示“同时发生”时用；表递进改 `In addition,` / `Additionally,` |
| **Consequently,** | 2.44 | 1.20 | **2.04×** | 交替使用 `Thus,` / `Hence,` / `As a result,` 或因果从句 |
| **Specifically,** | 15.31 | 7.82 | **1.96×** | 勿每段必用；交替使用 `In particular,` 或直接展开细节 |
| **To address ...** | 4.72 | 2.46 | **1.92×** | 交替使用 `To overcome ...` / `To mitigate ...` / `To bridge this gap,` |
| **Therefore,** | 11.20 | 5.89 | **1.90×** | 交替使用 `Thus,` / `Hence,` 或直接用 `so that / thereby` 连接 |
| **Notably,** | 2.94 | 1.73 | **1.70×** | 克制使用（每段 ≤ 1 个修饰副词），避免叠加出“AI 腔” |
| **To this end,** | 2.34 | 1.56 | **1.50×** | 交替使用 `To achieve this,` / `Motivated by this,` |
| **While ...**（母语强偏好） | 5.49 | **11.22** | **0.49×** | **多用** `While X ..., Y ...` 合并转折/对比句，减少机械 `However,` |
| **In particular,**（母语偏好） | 2.54 | **4.38** | **0.58×** | 用 `In particular,` 替代部分 `Specifically,` |
| **Instead,**（母语偏好） | 2.38 | **3.15** | **0.76×** | 在否定旧方案后用 `Instead, we ...` 引出新设计，干净利落 |

---

## 2. 高频词汇与短语偏好差异

| 华人组显著偏高（z-score） | 问题特征 | 母语组更自然的写法 |
|---|---|---|
| `effectiveness` / `the effectiveness of` (z=+14.9) | 实验段套话重复率极高 | `we show that our ...`、`our results show`、直接陈述指标提升 |
| `as shown in Fig.` / `shown in Fig.` (z=+13.8) | 每句开头机械重复 | `Figure X shows ...`、`We visualize ... in Figure X`、`(...; see Figure X)` |
| `proposed` / `the proposed` (z=+13.4) | 通篇重复 *the proposed method* | 命名后直接用方法名，或交替使用 `our approach / framework / model` |
| `adopt` / `we adopt` (z=+12.2) | “采用”直译，偏书面僵硬 | `we use` / `using`（母语组高频首选）、`we employ` |
| `compared with` (z=+12.1) | 过度集中于单一比较句式 | 交替使用 `relative to`、`over`、`outperforms X by ...`、`unlike` |
| `experimental results` / `the experimental results` | 动辄以此作主语 | `Our results show ...`、`Table X shows ...`、`We find that ...` |
| `respectively` | 容易滥用或对应不清 | 仅在两两组严格一一对应时使用；否则直接拆开写清 |
| `superiority` | 语气略显夸张 | `stronger performance`、`gains over baselines`、`outperforms ... by ...` |
| `according to` | “根据”直译泛化 | 视语境换 `following [CITE]`、`based on`、`given`、`under` |
| `mainly` | “主要”直译 | `primarily`、`largely`、`mostly` |
| `existing methods` 重复 | 综述段表达单一 | 交替使用 `prior work`、`previous studies`、`the literature` |

---

## 3. 使用原则
- 以上华人组高频词**本身并不算语法错误**，只是连续或高频出现会暴露“中式模板感”。
- 润色目标：**一段之内不重复套话**，用 `While ...`、`In particular,`、`Instead,`、`we show that`、`we use`、`prior work` 等母语高频结构自然穿插。
