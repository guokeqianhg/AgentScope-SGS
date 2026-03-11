import uuid
import random # 确保顶部导入了 random
from typing import List, Dict

ROLES_SETUP = ["主公", "忠臣", "反贼", "反贼", "内奸"]

def generate_deck() -> List[Dict]:
    """根据标准版生成 100 张带有独立 UUID、花色、点数的牌库"""
    deck = []
    SUITS = ["♠黑桃", "♥红桃", "♣梅花", "♦方块"]
    
    def add_cards(name: str, ctype: str, count: int):
        for _ in range(count):
            deck.append({
                "uuid": str(uuid.uuid4())[:8],
                "name": name,
                "type": ctype,
                "suit": random.choice(SUITS),           # [架构师新增]: 随机花色
                "number": random.randint(1, 13)         # [架构师新增]: 随机点数(1-13)
            })
            
    # 1. 基本牌 (53张)
    add_cards("杀", "basic", 30)
    add_cards("闪", "basic", 15)
    add_cards("桃", "basic", 8)
    
    # 2. 锦囊牌 (35张)
    add_cards("过河拆桥", "trick", 6)
    add_cards("顺手牵羊", "trick", 5)
    add_cards("无中生有", "trick", 4)
    add_cards("南蛮入侵", "trick", 3)
    add_cards("决斗", "trick", 3)
    add_cards("乐不思蜀", "trick", 3)
    add_cards("无懈可击", "trick", 3)
    add_cards("闪电", "trick", 2)
    add_cards("五谷丰登", "trick", 2)
    add_cards("借刀杀人", "trick", 2)
    add_cards("万箭齐发", "trick", 1)
    add_cards("桃园结义", "trick", 1)
    
    # 3. 武器牌 (12张)
    add_cards("青釭剑", "equip", 1)
    add_cards("雌雄双股剑", "equip", 1)
    add_cards("青龙偃月刀", "equip", 1)
    add_cards("丈八蛇矛", "equip", 1)
    add_cards("古锭刀", "equip", 1)
    add_cards("寒冰剑", "equip", 1)
    add_cards("麒麟弓", "equip", 1)
    add_cards("诸葛连弩", "equip", 2)
    add_cards("贯石斧", "equip", 1)
    add_cards("方天画戟", "equip", 1)
    add_cards("-1马", "equip", 3)  # [修复]: 补齐标准版3匹减一马
    add_cards("+1马", "equip", 3)  # [修复]: 补齐标准版3匹加一马
    
    return deck