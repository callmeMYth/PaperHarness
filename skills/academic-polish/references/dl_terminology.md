# 深度学习中英术语表

> 用途：翻译时锁定术语，保证全文统一。**用户提供的术语表优先于本表。**
> 标注：★ = 常见误译。缩写首次出现写全称 + (缩写)。

## 基础与训练
| 中文 | English | 备注 |
|---|---|---|
| 深度学习 | deep learning | 不加冠词 |
| 神经网络 | neural network | |
| 卷积神经网络 | convolutional neural network (CNN) | |
| 循环神经网络 | recurrent neural network (RNN) | |
| 长短期记忆网络 | long short-term memory (LSTM) | |
| 图神经网络 | graph neural network (GNN) | |
| 前馈网络 | feed-forward network (FFN) | |
| 多层感知机 | multilayer perceptron (MLP) | |
| 激活函数 | activation function | |
| 损失函数 | loss function / objective | |
| 交叉熵损失 | cross-entropy loss | |
| 反向传播 | backpropagation | 一个词 |
| 梯度下降 | gradient descent | |
| 随机梯度下降 | stochastic gradient descent (SGD) | |
| 学习率 | learning rate | |
| 学习率衰减 / 预热 | learning rate decay / warm-up | |
| 批大小 ★ | batch size | 非 "batch number" |
| 迭代 / 轮次 ★ | iteration / epoch | "轮"通常指 epoch |
| 过拟合 / 欠拟合 | overfitting / underfitting | |
| 正则化 | regularization | |
| 权重衰减 | weight decay | |
| 丢弃法 | dropout | |
| 批归一化 / 层归一化 | batch normalization (BN) / layer normalization (LN) | |
| 残差连接 ★ | residual connection / skip connection | 非 "remnant connection" |
| 超参数 | hyperparameter | 一个词 |
| 收敛 | converge / convergence | |
| 端到端 | end-to-end | 作定语带连字符 |
| 预训练 / 微调 | pre-training / fine-tuning | 动词 pre-train / fine-tune |
| 从头训练 | train from scratch | |
| 冻结参数 | freeze parameters | |
| 参数量 ★ | number of parameters / parameter count (#Params) | 非 "parameter quantity" |
| 计算量 ★ | computational cost / FLOPs | 非 "calculation amount" |
| 推理速度 | inference speed / throughput / latency | 区分吞吐与延迟 |
| 显存 ★ | GPU memory | 非 "video memory" |
| 消融实验 ★ | ablation study | 非 "melting experiment" |
| 基线 | baseline | |
| 最先进的 ★ | state-of-the-art (SOTA) | 作定语带连字符；勿写 "most advanced" |
| 泛化能力 | generalization ability / generalizability | |
| 鲁棒性 | robustness | |
| 可解释性 | interpretability / explainability | |
| 即插即用 | plug-and-play | |
| 轻量级 | lightweight | |

## 架构与机制
| 中文 | English | 备注 |
|---|---|---|
| 注意力机制 | attention mechanism | |
| 自注意力 | self-attention | |
| 多头注意力 | multi-head attention (MHA) | |
| 交叉注意力 | cross-attention | |
| 位置编码 | positional encoding / position embedding | |
| 编码器 / 解码器 | encoder / decoder | |
| 主干网络 ★ | backbone | 非 "main network" |
| 颈部 / 检测头 | neck / (detection) head | |
| 特征图 | feature map | |
| 感受野 | receptive field | |
| 下采样 / 上采样 | downsampling / upsampling | |
| 池化 | pooling | |
| 空洞卷积 ★ | dilated convolution / atrous convolution | |
| 深度可分离卷积 | depthwise separable convolution | |
| 特征金字塔 | feature pyramid network (FPN) | |
| 多尺度特征融合 | multi-scale feature fusion | |
| 跳跃连接 | skip connection | |
| 门控机制 | gating mechanism | |
| 嵌入 | embedding | |
| 令牌 / 词元 | token | 不翻译 |
| 隐空间 / 潜在空间 | latent space | |
| 瓶颈层 | bottleneck | |
| 混合专家 | mixture of experts (MoE) | |
| 扩散模型 | diffusion model | |
| 生成对抗网络 | generative adversarial network (GAN) | |
| 变分自编码器 | variational autoencoder (VAE) | |
| 大语言模型 | large language model (LLM) | |
| 视觉-语言模型 | vision-language model (VLM) | |
| 提示学习 | prompt learning / prompt tuning | |
| 参数高效微调 | parameter-efficient fine-tuning (PEFT) | |
| 低秩适配 | low-rank adaptation (LoRA) | |
| 知识蒸馏 | knowledge distillation | |
| 教师/学生模型 | teacher / student model | |
| 剪枝 / 量化 | pruning / quantization | |

## 学习范式
| 中文 | English |
|---|---|
| 监督 / 无监督 / 半监督 / 自监督学习 | supervised / unsupervised / semi-supervised / self-supervised learning |
| 弱监督 | weakly supervised learning |
| 对比学习 | contrastive learning |
| 迁移学习 | transfer learning |
| 领域自适应 / 领域泛化 | domain adaptation / domain generalization |
| 少样本 / 零样本学习 | few-shot / zero-shot learning |
| 增量学习 / 持续学习 | incremental learning / continual learning |
| 强化学习 | reinforcement learning (RL) |
| 联邦学习 | federated learning |
| 元学习 | meta-learning |
| 多任务学习 | multi-task learning |
| 多模态学习 | multimodal learning |
| 主动学习 | active learning |
| 伪标签 | pseudo-label |
| 数据增强 | data augmentation |
| 标注 | annotation / label |
| 长尾分布 | long-tailed distribution |
| 类别不平衡 | class imbalance |

## 任务
| 中文 | English |
|---|---|
| 图像分类 | image classification |
| 目标检测 | object detection |
| 语义 / 实例 / 全景分割 | semantic / instance / panoptic segmentation |
| 目标跟踪 | object tracking |
| 姿态估计 | pose estimation |
| 超分辨率 | super-resolution |
| 图像去噪 / 去雾 / 去雨 | image denoising / dehazing / deraining |
| 图像修复 | image inpainting / restoration（区分） |
| 深度估计 | depth estimation |
| 三维重建 | 3D reconstruction |
| 点云 | point cloud |
| 行人重识别 | person re-identification (ReID) |
| 遥感图像 | remote sensing imagery |
| 医学图像分割 | medical image segmentation |
| 变化检测 | change detection |
| 显著性检测 | salient object detection |
| 异常检测 | anomaly detection |
| 命名实体识别 | named entity recognition (NER) |
| 情感分析 | sentiment analysis |
| 机器翻译 | machine translation |
| 文本生成 | text generation |
| 问答 | question answering (QA) |
| 时间序列预测 | time series forecasting |
| 推荐系统 | recommender system |

## 评估
| 中文 | English | 备注 |
|---|---|---|
| 准确率 / 精确率 / 召回率 ★ | accuracy / precision / recall | 准确率≠精确率 |
| F1 分数 | F1 score | |
| 平均精度均值 | mean average precision (mAP) | |
| 交并比 | intersection over union (IoU) | |
| 均方误差 | mean squared error (MSE) | |
| 峰值信噪比 / 结构相似性 | PSNR / SSIM | |
| 提升了 X 个百分点 ★ | improves by X percentage points (pp) / X% absolute | 区分相对提升 |
| 显著优于 | substantially / significantly outperforms | significantly 仅限统计检验 |
| 训练集 / 验证集 / 测试集 | training / validation / test set | 非 "train set"（亦可接受但前者更正式） |
| 基准数据集 | benchmark dataset | |
| 定性 / 定量分析 | qualitative / quantitative analysis | |
| 可视化 | visualization | |
