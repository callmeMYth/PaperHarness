# 英译中去翻译腔与学术化规范（深度学习论文）

> 用途：把英文顶会/顶刊论文翻译为**流畅、地道、可读性高**的中文学术表达，用于论文精读、文献综述或完整中文导出。
> 核心原则：**理解英文句义与逻辑后，按中文语序与表达习惯重组**；宁可断成两个干净短句，绝不堆出 80 字的“……的……的……”翻译腔长句。

---

## 一、六大“翻译腔”高频病症与解法

### E1 拆解超长后置定语（最高频）
英文喜欢用 `which / that / of / with / -ing / -ed` 在名词后连续嵌套 2–3 层修饰；中文不能全塞进“……的”前面。
- **解法**：把后置定语**后置成独立分句**或**顺译成流水句**。

| 英文原句 | ✗ 翻译腔 | ✓ 地道中文 |
|---|---|---|
| We propose a lightweight module that adaptively fuses multi-scale features extracted from different stages of the backbone. | 我们提出了一种自适应地融合从主干网络不同阶段提取的多尺度特征的轻量级模块。 | 我们提出了一种轻量级模块，能够自适应地融合主干网络各阶段提取的多尺度特征。 |

### E2 消除生硬“被”字句
英文方法/实验部分大量使用被动语态，中文学术表达应转为**主动无主句**，或用“采用 / 利用 / 通过 / 经由 / 设为 / 得到”替代“被”。
- ✗ *The input image is resized to 224×224 and is fed into the encoder.* → “输入图像被缩放到 224×224，然后被送入编码器。”
- ✓ “将输入图像缩放至 224×224 后送入编码器。”
- ✗ *All models are trained for 100 epochs.* → ✓ “所有模型均训练 100 个轮次（epoch）。”

### E3 抽象名词结构还原为动词
英文偏好名词化（*the introduction of X leads to an improvement in Y*），中文偏好动词驱动。
- ✗ “残差连接的引入导致了优化难度的降低。”
- ✓ “引入残差连接有效降低了优化难度。”
- ✗ “该方法对计算开销实现了显著的减少。” → ✓ “该方法大幅降低了计算开销。”

### E4 调整状语与条件/因果语序
英文常把结论放前、条件/原因/目的放后（*Y happens because X / when Z*）；中文习惯**先因后果、先条件后结论、先背景后主体**。
- *Performance degrades sharply when the domain gap is large.*
  - ✗ 性能急剧下降，当领域差异很大时。
  - ✓ 当领域差异较大时，模型性能会急剧下降。
- *To reduce memory overhead, we compute attention within local windows.*
  - ✓ 为降低显存开销，我们在局部窗口内计算注意力。

### E5 代词还原与指代清晰化
英文大量用 *it / they / this / such / the former / the latter*；中文连续出现“它 / 它们 / 这”会非常拗口且模糊。
- **解法**：把 *it / they* 还原成具体名词（“该模型”“这类方法”），或直接省略重复主语。
- ✗ *Although it achieves high accuracy, it requires large memory, which limits its deployment.*
- ✓ “尽管该模型准确率较高，但显存占用大，限制了实际部署。”

### E6 谨慎处理英文连接词与程度副词
| 英文 | ✗ 生硬直译 | ✓ 自然中文 |
|---|---|---|
| *However,* | 然而，（每句必写） | 视语境交替用“然而”“但”“不过”“相比之下” |
| *Furthermore / Moreover* | 此外、而且（机械堆砌） | “进一步地”“此外”“同时”，语义紧接时可省略 |
| *Specifically / In particular* | 具体地、特别地 | “具体而言”“尤其是”“其中” |
| *While A, B* | 当 A 时，B（误译转折为时间！） | “尽管 A，但 B” / “A 虽……，但 B……” |
| *significantly* | 显著地（无统计检验时偏夸张） | “大幅 / 明显”（仅在有统计显著检验时译“显著”） |
| *respectively* | 分别地（放句尾极生硬） | 提前至对应项前，或“依次为……” |
| *in terms of* | 在……方面而言 | “在……上” / “就……而言” |
| *suffer from* | 遭受……的痛苦 | “存在……问题” / “受限于……” |
| *leverage / exploit* | 杠杆利用 / 剥削利用 | “利用 / 借助 / 充分挖掘” |
| *trivial / non-trivial* | 平凡的 / 非平凡的 | “简单的 / 并非易事、不可忽视的” |
| *vanilla* | 香草的 | “标准 / 原始 / 基础版” |
| *ground truth* | 地面真相 | “真实标签 / 真值（ground truth）” |
| *backbone* | 脊骨 / 骨干 | “主干网络（backbone）” |

---

## 二、专业术语与格式保留规范

1. **首次出现标注英文**：关键深度学习术语首次出现时用「中文（English, ACR）」格式，如“视觉变换器（Vision Transformer, ViT）”，后续统一使用中文或公认缩写（如 ViT、CNN、LLM、mAP、FLOPs）。
2. **约定俗成不硬译**：`Transformer`、`Token`、`Prompt`、`LoRA`、`ResNet`、`AdamW`、`ImageNet`、`Softmax`、`Dropout`、`FLOPs`、`mAP`、`IoU`、`PSNR/SSIM` 保持英文，不要强行意译成“变形金刚”“令牌”“丢弃法”。
3. **锁定公式与引用**：
   - 所有行内 `$...$`、行间 `$$...$$` 数学公式、变量符号原样保留，**不得篡改下标或变量名**。
   - 引用标记 `[1]`、`(Author et al., 2023)`、`\cite{}` 以及图表编号 `Figure 1` / `Table 2` 统一转为“图 1”“表 2”并保持原编号一致。
4. **整篇术语一致**：长论文翻译前先运行 `scripts/glossary.py extract` 锁定全局术语表，分批翻译完后用 `scripts/glossary.py check` 校对。

---

## 三、完整导出标准（`en2zh` 模式）

1. 按原论文完整章节结构翻译（标题、摘要、引言、相关工作、方法、实验、结论与局限性，不跳过核心段落；参考文献列表保持原文不翻）。
2. 译文使用中文全角标点（，。；：（）），**中英文/数字/行内公式之间保留规范空格**，便于阅读与排版。
3. 完成后调用 `scripts/paper_io.py export` 生成：
   - `<paper>_zh.md`（纯中文完整论文 Markdown）
   - `<paper>_bilingual.md`（中英逐段对照 Markdown，适合精读核对）
   - `<paper>_zh.html` 与 `<paper>_bilingual.html`（内置 MathJax 公式渲染与论文排版样式，浏览器打开 `Ctrl+P` 即可直接导出干净的中文/双语 PDF）。
