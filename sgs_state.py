# -*- coding: utf-8 -*-
"""物理引擎与全局状态维护"""
import random
from typing import List, Dict, Optional
from sgs_config import generate_deck

WEAPON_DESC = {
    "诸葛连弩": "【已实装】出牌阶段你可以使用任意数量的【杀】。",
    "古锭刀": "【已实装】当你使用【杀】对没有手牌的目标造成伤害时，伤害+1。优先砍空城敌人！",
    "贯石斧": "【已实装】当你使用的【杀】被【闪】抵消时，你可以弃置两张牌，令此【杀】依然造成伤害。",
    "青釭剑": "你使用【杀】时无视防具。(MVP暂无防具，仅提供距离)",
    "朱雀羽扇": "可视为火杀。(MVP暂无属性伤害，仅提供距离)",
    "雌雄双股剑": "(MVP暂未实装特效，仅提供距离)",
    "青龙偃月刀": "(MVP暂未实装特效，仅提供距离)",
    "丈八蛇矛": "(MVP暂未实装特效，仅提供距离)",
    "寒冰剑": "(MVP暂未实装特效，仅提供距离)",
    "麒麟弓": "(MVP暂未实装特效，仅提供距离)",
    "方天画戟": "(MVP暂未实装特效，仅提供距离)"
}

class PlayerState:
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        # 主公天然多1点体力上限
        self.max_hp = 4 if role == "主公" else 3
        self.hp = self.max_hp
        self.hand_cards: List[Dict] = []
        self.is_alive = True
        self.equip_area: Dict[str, Optional[Dict]] = {
            "weapon": None, "plus_mount": None, "minus_mount": None
        }
        self.judge_area: List[Dict] = []  # 存放乐不思蜀、闪电等
        self.personality_profile: str = "" # 用于持久化存储生成的性格准则
        
    def get_hand_str(self) -> str:
        # 在牌名前面拼上花色和点数
        return ", ".join([f"{c.get('suit', '')}{c['name']}({c['uuid']})" for c in self.hand_cards])
        
    def has_card_id(self, card_id: str) -> bool:
        return any(c['uuid'] == card_id for c in self.hand_cards)
    
    def has_card_name(self, card_name: str) -> bool:
        """判断手牌中是否包含某种名称的牌"""
        return any(c['name'] == card_name for c in self.hand_cards)
    
    def pop_card(self, card_id: str) -> Optional[Dict]:
        for i, c in enumerate(self.hand_cards):
            if c['uuid'] == card_id:
                return self.hand_cards.pop(i)
        return None

class GameEngine:
    def __init__(self, player_names: List[str], roles: List[str]):
        self.deck = generate_deck()
        random.shuffle(self.deck)
        self.discard_pile = []
        self.seat_order = player_names  # [架构师新增]: 记录固定座位表用于算距离
        
        self.players: Dict[str, PlayerState] = {}
        for name, role in zip(player_names, roles):
            self.players[name] = PlayerState(name, role)
            
    def draw_cards(self, player_name: str, count: int) -> List[Dict]:
        """发牌逻辑：牌堆空了则洗弃牌堆"""
        drawn = []
        for _ in range(count):
            if not self.deck:
                self.deck = self.discard_pile
                self.discard_pile = []
                random.shuffle(self.deck)
                if not self.deck: 
                    break
            drawn.append(self.deck.pop(0))
            
        self.players[player_name].hand_cards.extend(drawn)
        return drawn
        
    def validate_and_consume(self, player_name: str, card_id: str, expected_name: str = None) -> bool:
        """强校验：玩家是否拥有该牌，且名称匹配。若合法则从手牌移除进入弃牌堆"""
        player = self.players[player_name]
        card = next((c for c in player.hand_cards if c['uuid'] == card_id), None)
        
        if not card: return False
        if expected_name and card['name'] != expected_name: return False
        
        player.pop_card(card_id)
        self.discard_pile.append(card)
        return True

    def get_public_state(self) -> str:
        """获取全场公开信息"""
        state_strs = []
        for name, p in self.players.items():
            if not p.is_alive: continue
            role_str = p.role if p.role == "主公" else "未知"
            equips = [c["name"] for c in p.equip_area.values() if c]
            equip_str = f"装备:{equips}" if equips else "无装备"
            judges = [c["name"] for c in p.judge_area]
            judge_str = f"判定区:{judges}" if judges else ""
            state_strs.append(f"[{name}] 血:{p.hp}/{p.max_hp}, 手牌:{len(p.hand_cards)}, {equip_str} {judge_str}, 身份:{role_str}")
        return " | ".join(state_strs)
        
    def check_win(self) -> Optional[str]:
        """MVP胜利判定 (天然支持多反贼)"""
        alive_roles = [p.role for p in self.players.values() if p.is_alive]
        
        # 1. 如果主公阵亡
        if "主公" not in alive_roles:
            # 仅剩内奸一人存活，内奸胜
            if "内奸" in alive_roles and len(alive_roles) == 1:
                return "内奸胜利！野心家夺取了天下！"
            # 否则反贼胜（哪怕反贼全死了，只要主公死了且不满足内奸单赢条件，也是反贼赢）
            return "反贼胜利！苍天已死，黄天当立！"
            
        # 2. 如果主公存活，且反贼和内奸全灭
        if "反贼" not in alive_roles and "内奸" not in alive_roles:
            return "主公与忠臣胜利！天下太平！"
            
        return None
    
    def get_distance(self, attacker: str, target: str) -> int:
        """核心算法：计算受马匹影响的动态距离"""
        alive_seats = [name for name in self.seat_order if self.players[name].is_alive]
        if attacker not in alive_seats or target not in alive_seats:
            return 999
            
        idx1 = alive_seats.index(attacker)
        idx2 = alive_seats.index(target)
        n = len(alive_seats)
        raw_dist = min((idx2 - idx1) % n, (idx1 - idx2) % n)
        
        # 加上马匹修正
        if self.players[attacker].equip_area["minus_mount"]: # -1马
            raw_dist -= 1
        if self.players[target].equip_area["plus_mount"]:    # +1马
            raw_dist += 1
            
        return max(1, raw_dist) # 距离最小为1

    def get_valid_kill_targets(self, attacker: str, is_trick: bool = False) -> List[str]:
        """获取合法目标 (is_trick=True 表示顺手牵羊等限制距离1的锦囊)"""
        valid_targets = []
        
        # 确定攻击范围
        attack_range = 1
        if not is_trick:
            weapon = self.players[attacker].equip_area["weapon"]
            if weapon:
                # 武器射程字典
                range_dict = {
                    "诸葛连弩": 1, "青釭剑": 2, "雌雄双股剑": 2, "古锭刀": 2, "寒冰剑": 2,
                    "青龙偃月刀": 3, "丈八蛇矛": 3, "贯石斧": 3,
                    "方天画戟": 4, "朱雀羽扇": 4, "麒麟弓": 5
                }
                attack_range = range_dict.get(weapon["name"], 1)

        for target in self.players:
            if target != attacker and self.players[target].is_alive:
                if self.get_distance(attacker, target) <= attack_range:
                    valid_targets.append(target)
        return valid_targets

    def random_discard_from_target(self, target_name: str) -> Optional[Dict]:
        """[方向二] 过河拆桥物理逻辑：随机弃置目标一张手牌"""
        target_state = self.players[target_name]
        if not target_state.hand_cards:
            return None
            
        # 随机抽取一张牌
        card_idx = random.randint(0, len(target_state.hand_cards) - 1)
        discarded_card = target_state.hand_cards.pop(card_idx)
        self.discard_pile.append(discarded_card)
        return discarded_card