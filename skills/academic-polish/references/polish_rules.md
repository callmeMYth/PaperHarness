# 英文润色规则

> 用途：对已有英文稿（作者自写或机翻）进行学术化润色。按 **三层** 依次检查：
> ① 正确性（语法/用词错误） → ② 学术性（语域、精确、简洁） → ③ 可读性（衔接、节奏、逻辑）。

---

## 第一层：正确性
- 主谓一致、冠词、单复数、时态一致（见 `zh2en_rules.md` R10–R13）。
- 常见搭配错误：
  | ✗ | ✓ |
  |---|---|
  | based on … to … | based on … , we … |
  | according to the experiment results | according to the experimental results |
  | compared with … , our method is better | compared with …, our method achieves better … |
  | the reason is because | the reason is that |
  | in the other hand | on the other hand |
  | so-called（无贬义场景） | 删除或换 *referred to as* |
  | discuss about / emphasize on | discuss / emphasize |
  | lead to improve | lead to improvements / improve |
  | contribute to improve | contribute to improving |
  | experiments are conducted to verify the effectiveness | 可保留，但更好：*we conduct experiments to verify …* |
- Respectively 用法：仅当两组一一对应时使用，放句末。

## 第二层：学术性

### P1 精确
- 模糊词具体化：*some, many, a lot, good, better* → 给出数据或范围。
- *significant* 仅用于统计显著；否则用 *substantial / notable / considerable*。
- *novel* 每篇论文最多用 1–2 次；避免 *very novel*。

### P2 简洁（删 20% 原则）
| 冗长 | 简洁 |
|---|---|
| in order to | to |
| due to the fact that | because |
| a large number of | many（非正式稿可保留） |
| has the ability to | can |
| it is obvious that | 删除 |
| in the case of | for / in |
| at the same time | simultaneously / meanwhile |
| make use of | use / exploit |
| with the help of | with / using / via |
| is able to effectively improve | effectively improves |

### P3 语域
- 避免缩写（*don't, it's, can't*）、问句式开头、感叹语、*etc.* 收尾的列举（改为 *such as A, B, and C*）。
- 避免 *we can see that, as we all know, nowadays, in recent years*（引言首句尤其忌讳 *In recent years, deep learning has developed rapidly*）。

### P4 去「AI 腔」/ 过度修饰
润色后的文本**不能**读起来像 LLM 生成。以下词语在深度学习论文中出现频率异常时要替换或删除：
*delve into, intricate, pivotal, paramount, underscore, showcase, leverage（过度）, harness, realm, landscape, tapestry, holistic, seamless, groundbreaking, cutting-edge, meticulous, a testament to, it is crucial to note that, notably（过度）*
- 规则：每段 ≤1 个修饰性副词（*notably, remarkably, significantly*）。
- 优先用具体动词 + 数据，而非形容词堆砌。

## 第三层：可读性

### P5 句长节奏
- 平均 18–25 词，长短交替；单句 >40 词必拆。
- 避免连续 3 句以相同结构开头（如都以 *The* / *We* 开头）。

### P6 衔接
- 句间用 **主题链**（上一句的尾 = 下一句的头）或指代（*This design / Such a strategy*）建立联系，而非堆连接词。
- *This* 后应接名词（*This limitation…*），避免裸 *This*。

### P7 平行结构
列举时语法形式一致：✗ *to extract features, fusing them, and the classification* → ✓ *to extract, fuse, and classify features*。

### P8 术语一致
同一概念全文同一名称（不要 *module / block / unit* 混用）；缩写首次出现给全称：*multi-head self-attention (MHSA)*。

---

## 润色力度（默认：中度）
| 力度 | 范围 |
|---|---|
| 轻度 | 只改正确性错误 + 明显中式表达 |
| **中度（默认）** | 三层全部，允许句子重组、合并/拆分 |
| 深度 | 在中度基础上调整段落逻辑与句序（见 `paragraph_logic.md`），并在理由中说明 |

用户要求"适度调整逻辑"时使用 **深度**，但：不新增论点、不删除事实、不改变结论强度。
