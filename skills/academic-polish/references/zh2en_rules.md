# 中译英改写规则（深度学习论文）

> 用途：把中文学术表达转换为英文期刊/顶会认可的表达。每条规则给出「中式写法 → 地道写法」。
> 原则：**先理解中文的逻辑关系，再用英文的句法重建**，不要逐词对译。

---

## 一、句子结构

### R1 拆分流水句（最高频问题）
中文习惯用逗号串联多个分句，英文必须明确主次关系。
- 一句话只承载 **1 个核心信息 + 至多 1–2 个从属信息**；英文句子以 15–30 词为宜。
- 逗号连接的独立分句 → 句号断开，或用从句/分词/介词短语降级。

| 中文 | ✗ 直译 | ✓ 改写 |
|---|---|---|
| 该方法计算量大，难以部署在移动端，限制了其实际应用。 | This method has large computation, it is hard to deploy on mobile devices, which limits its practical application. | The high computational cost of this method hinders its deployment on mobile devices, limiting its practical applicability. |

### R2 补出主语，避免无主句
中文常省略主语（"通过实验发现……"），英文必须有主语。
- 首选 **we**（顶会主流，主动语态更清晰）；描述客观事实时用事物作主语。
- ✗ *Through experiments, it is found that…* → ✓ *Our experiments show that…* / *We find that…*

### R3 信息结构：已知 → 新信息
句首放上文已提及或读者熟悉的信息，句尾放新信息/重点（end-focus）。
- ✗ *A novel attention module that captures long-range dependencies is proposed in this paper.*
- ✓ *In this paper, we propose a novel attention module that captures long-range dependencies.*

### R4 避免头重脚轻
主语过长时，改为 it/there 结构，或把修饰成分后置。
- ✗ *How to effectively fuse multi-scale features extracted from different layers remains challenging.*
- ✓ *It remains challenging to effectively fuse multi-scale features extracted from different layers.*  或  *Effectively fusing multi-scale features from different layers remains an open challenge.*

### R5 中文"的"字长定语 → 英文后置修饰
中文定语在前，英文长修饰语应后置（介词短语、分词、关系从句）。
- 基于注意力机制的多尺度特征融合模块 → *a multi-scale feature fusion module based on attention* → 更佳：*an attention-based multi-scale feature fusion module*（≤3 个前置修饰词时可前置复合）

---

## 二、词汇与搭配

### R6 动词名词化要适度
学术英语偏好一定程度的名词化，但不可堆砌 "the + 名词 + of" 链。
- ✗ *We make an improvement of the performance.* → ✓ *We improve the performance.*
- ✓ 恰当名词化：*The introduction of residual connections facilitates optimization.*

### R7 替换空泛动词与口语化词
| 中式/口语 | 学术替换 |
|---|---|
| make, do, get | achieve, perform, obtain, yield |
| use | employ, adopt, leverage, utilize（勿滥用 utilize） |
| show（重复过多时） | demonstrate, indicate, reveal, suggest |
| big / very big | substantial, considerable, significant（仅统计显著时用 significant） |
| a lot of / lots of | numerous, a large number of, extensive |
| very good / very well | remarkable, strong, favorable |
| solve the problem | address / tackle / alleviate / mitigate the issue（按程度选） |
| besides | in addition, moreover, furthermore |
| so | therefore, thus, consequently |
| but（句首） | however, nevertheless |

### R8 中文高频套话的处理
| 中文 | ✗ 直译 | ✓ 地道 |
|---|---|---|
| 随着……的快速发展 | With the rapid development of… | 尽量删除；或 *Recent advances in X have…* |
| 越来越多的关注 | more and more attention | *increasing / growing attention* |
| 起着重要作用 | plays an important role | *is central to / is critical for*（可用但勿重复） |
| 取得了很好的效果 | achieves good effect | *achieves strong / state-of-the-art performance* |
| 具有重要意义 | has important significance | *is of great importance* 或直接说明具体意义 |
| 本文提出了一种……的方法 | This paper proposes a … method | *We propose X, a … that …*（命名 + 同位语） |
| 实验结果表明 | Experimental results show that | 可用；变体：*Extensive experiments on A and B demonstrate that…* |
| 有效地解决了 | effectively solves | *effectively alleviates / mitigates*（避免绝对化） |
| 进一步地 | further more | *Furthermore,* / *Moreover,* |
| 综上所述 | In summary of above | *In summary,* / *Overall,* |

### R9 冗余与重复
中文常用同义叠加（"研究和探讨"、"分析和研究"），英文只保留一个。
- 删除 *in this paper we* 的重复出现；删除 *it is worth noting that*、*it should be pointed out that* 的过度使用。
- 删冗余修饰：*completely eliminate → eliminate*, *future prospects → prospects*, *basic fundamentals → fundamentals*。

---

## 三、语法要点

### R10 冠词
- 首次提及可数单数名词用 *a/an*，再次提及或唯一所指用 *the*。
- 方法/模型名不加冠词（*ResNet*, *BERT*），但 *the proposed method*、*the Transformer architecture* 加。
- 学科/抽象概念泛指不加冠词：*deep learning*, *attention*（指机制本身时）。

### R11 时态
| 内容 | 时态 |
|---|---|
| 通用事实、方法描述、本文贡献 | 一般现在时（*We propose… The module consists of…*） |
| 实验过程（做了什么） | 一般过去时 或 现在时皆可，**全文统一** |
| 实验结论、表格数据描述 | 一般现在时（*Table 2 shows… Our method outperforms…*） |
| 他人工作 | 一般现在时 / 现在完成时（*Recent studies have shown…*） |

### R12 单复数与可数性
不可数：*research, work（研究工作）, information, knowledge, equipment, feedback*。
- ✗ *researches, works (指研究), informations* → ✓ *studies, prior work, information*

### R13 比较与程度
- 比较必须同类对象：✗ *Our accuracy is higher than ResNet.* → ✓ *Our method achieves higher accuracy than ResNet.*
- 数字增幅：*improves accuracy by 2.3%*（绝对提升写 *2.3 percentage points* 或 *2.3% absolute*）。

### R14 连接词与逻辑显化
中文常靠语序表达逻辑（意合），英文需显式连接词（形合）。翻译前先标出每对分句的关系：因果 / 转折 / 递进 / 条件 / 目的 / 让步，然后选择：
- 因果：*because, since, as a result, therefore, thereby, owing to*
- 转折：*however, whereas, while, in contrast, despite*
- 目的：*to, in order to, so that*
- 递进：*moreover, furthermore, in addition, beyond this*
- 让步：*although, even though, despite*

---

## 四、学术语气

### R15 适度 hedging（避免绝对化）
- 中文"证明了"→ 视证据强度：*demonstrate*（实验充分） / *suggest, indicate*（间接证据） / *may, could, is likely to*（推测）。
- 避免 *prove*（除非数学证明）、*always, never, perfectly, completely solve*。

### R16 主动语态优先，被动语态有节制
- 贡献与动作用主动（*We design…*），客观流程/与人无关时用被动（*The images are resized to 224×224.*）。
- 避免一段内连续 3 句以上被动。

### R17 避免主观与情绪化词
✗ *amazing, perfect, obviously, undoubtedly, huge* → 用数据或客观描述代替。
