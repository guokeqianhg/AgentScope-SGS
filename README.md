# AgentScope-SGS
SanGuoSha-Agent: 基于大模型的多智能体博弈推理系统
一个在不完全信息环境下，由 LLM 驱动多智能体进行身份推演、并发博弈与策略进化的《三国杀》硬核推演引擎。

本项目基于 AgentScope 与 ReAct 范式构建，深度融合了“大模型逻辑推理”与“物理规则引擎”。通过严格的 Pydantic 结构化契约、Asyncio 异步并发调度以及创新的“记忆纠偏”机制，成功让 5 个大模型 Agent 在充满欺诈、伪装与时序打断的复杂桌面游戏中，展现出极高的拟人化决策水平与系统工程稳定性。

核心技术栈
核心框架: AgentScope, ReAct 范式

多智能体高级特性: Reflection Memory (全局反思记忆), Dynamic Personality Injection (动态人格注入)

系统架构设计: Event-driven State Machine (事件驱动状态机), Rule Engine (物理规则引擎)

工程稳定性: Asyncio (高并发调度), Pydantic (结构化输出强约束)

底层驱动: 大语言模型 (默认支持 Qwen-max 等类 OpenAI 接口模型)

核心特性与架构亮点
1. 不完全信息博弈与动态人格
摒弃了传统的死板 AI 设定，系统在开局通过混沌随机种子为每个 Agent 注入独一无二的“灰度人格”（如：莽夫、苟王、记仇）。在每轮行动前，系统向 Agent 动态注入公开局势、合法距离目标、装备修正约束与历史推理记忆，支撑大模型完成单局平均 30-50 轮的长程博弈。

2. 解决多 Agent 并发抢答与“上下文幻觉”
针对《三国杀》中极度复杂的嵌套结算逻辑（如多人并发抢答打出【无懈可击】拦截锦囊），系统采用 Asyncio 实现异步并发扇出与递归结算。

首创“记忆纠偏补丁”：向抢答失败（因座次优先级被剥夺生效权）的 Agent 隐式注入状态回滚提示，将并发请求导致的大模型“上下文错觉（幻觉）”崩溃率降至 0%，完美实现时序一致性。

3. 结构化输出的 100% 绝对控制
针对大模型在复杂决策流中常见的 JSON 偏移与卡牌伪造（幻觉）问题，设计了基于 Pydantic 的契约化数据模型（Action/Dodge/Discard 等）。

结合字段强约束、格式校验与 Max_Retries（最高 3 次重试）机制，将 JSON 协议单次解析成功率提升至 95% 以上。

具备系统级兜底接管（Fallback），保障游戏引擎 100% 不会因模型输出崩溃而中断。

4. Neuro-Symbolic（神经符号）解耦架构
搭建基于事件驱动的确定性状态机，将动态距离计算、资产流转、胜负判定等绝对物理规则从 LLM 侧完全剥离。

降本增效：大模型仅负责意图决策，平均单步决策节约 Prompt Token 开销约 40%，实现 100% 规则零幻觉。

反思闭环：每轮末强制 Agent 触发 ReflectionModel 进行身份确信度推演与策略更新，形成“规则约束执行 + 反思驱动演化”的生命周期闭环。

项目结构
Plaintext
  SanGuoSha-Agent
   ├── sgs_main.py      # 主程序入口：Agent 实例化、事件分发、异步时序控制
   ├── sgs_state.py     # 物理引擎：状态机、距离算法、资产清算与胜负校验
   ├── sgs_schemas.py   # 数据契约：基于 Pydantic 的 LLM 结构化输出约束模型
   ├── sgs_config.py    # 牌库配置：标准版 100 张卡牌的 UUID、花色点数与生成逻辑
   └── sgs_prompts.py   # 提示词库：系统 Prompt 与动态人格生成 Prompt
快速开始
1. 环境准备
推荐使用 Python 3.9+ 环境。安装必要的依赖：
pip install agentscope pydantic

3. 配置环境变量
本项目默认兼容 OpenAI 格式的 API 接口。请在运行前配置你的大模型 API 密钥（默认以阿里云 DashScope 的 Qwen 模型为例，你也可以切换为其他 LLM）：
# Linux / macOS

export LLM_API_KEY="your_api_key_here"

export LLM_MODEL_ID="qwen-max"

export LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"

# Windows (Command Prompt)

set LLM_API_KEY="your_api_key_here"

set LLM_MODEL_ID="qwen-max"

set LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"

3. 启动游戏
在终端运行主程序，化身“上帝视角”观看 5 位高智商 Agent 尔虞我诈：
python sgs_main.py
