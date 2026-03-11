# -*- coding: utf-8 -*-
"""大模型输出的结构化约束契约"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal

class ActionModel(BaseModel):
    """出牌阶段的行动模型"""
    action_type: Literal["play_card", "end_phase"] = Field(
        description="选择 'play_card' 出牌，或选择 'end_phase' 结束当前出牌阶段"
    )
    card_id: Optional[str] = Field(
        description="如果你选择出牌，请填写手牌中该牌的 uuid。否则填 null", 
        default=None
    )
    target: Optional[str] = Field(
        description="如果牌需要目标（如【杀】），填写目标玩家的名称。否则填 null",
        default=None
    )

    secondary_target: Optional[str] = Field(
        description="仅在使用【借刀杀人】时填写，代表你希望借刀去击杀的第二目标。其他牌填 null",
        default=None
    )
    reasoning: str = Field(description="内部思维链：简述你基于当前身份、局势做出该决策的理由")

class DodgeModel(BaseModel):
    """回合外响应【杀】的模型"""
    play_dodge: bool = Field(description="是否决定打出【闪】响应【杀】。手中必须有闪才能选true。")
    card_id: Optional[str] = Field(
        description="如果你决定出【闪】，提供手牌中该【闪】的 uuid，否则填 null",
        default=None
    )
    reasoning: str = Field(description="简述为何出闪或不出闪的理由")

class DiscardModel(BaseModel):
    """弃牌阶段模型"""
    discard_card_ids: List[str] = Field(
        description="请提供你要弃置的卡牌 uuid 列表。数量必须与系统要求的弃牌数一致。"
    )
    reasoning: str = Field(description="弃牌理由")

class IdentityInference(BaseModel):
    """单个玩家的身份推演"""
    player_name: str = Field(description="被推测的玩家姓名")
    suspected_role: str = Field(description="你推测他最可能的身份（主公/忠臣/反贼/内奸）")
    confidence: int = Field(description="你的确信度(1-100)")
    reasoning: str = Field(description="基于本轮他打谁/救谁的推测理由")

class ReflectionModel(BaseModel):
    """回合结束时的全局反思模型"""
    inferences: List[IdentityInference] = Field(
        description="对场上除你之外所有存活玩家的身份推演列表"
    )
    next_round_strategy: str = Field(
        description="基于以上推演，你下一轮的核心宏观策略是什么？"
    )

class AOEResponseModel(BaseModel):
    """响应AOE锦囊（如南蛮入侵、万箭齐发）的模型"""
    play_card: bool = Field(description="是否决定打出系统要求的牌（杀/闪）")
    card_id: Optional[str] = Field(default=None, description="你要打出的卡牌 uuid，不打出填 null")
    reasoning: str = Field(description="简单说明理由")

class NullificationResponseModel(BaseModel):
    """响应无懈可击的模型"""
    play_card: bool = Field(description="是否决定打出【无懈可击】")
    card_id: Optional[str] = Field(default=None, description="你要打出的【无懈可击】的 uuid，不打出填 null")
    reasoning: str = Field(description="简述你打出无懈可击是为了保护谁，或者破坏谁的行动")

class GuanShiFuResponseModel(BaseModel):
    """响应【贯石斧】技能的模型"""
    use_skill: bool = Field(description="是否决定发动贯石斧技能（弃置两张牌强行命中）")
    discard_card_ids: List[str] = Field(
        default_factory=list, 
        description="如果你决定发动，请提供你要弃置的两张手牌的 uuid 列表（例如: [\"uuid1\", \"uuid2\"]）。不发动则填空列表 []"
    )
    reasoning: str = Field(description="简述你是否发动贯石斧强杀的理由")

class SimpleTraitModel(BaseModel):
    """极简的玩家打牌风格模型"""
    style_name: str = Field(description="风格标签（如：'莽夫'、'苟王'、'记仇'、'算计'）")
    action_rule: str = Field(description="一句非常具体、接地气的打牌习惯描述（绝对不要反智）。例如：'只要有杀必定打出，从不留牌防守' 或 '优先攻击上个回合伤害过自己的人'")