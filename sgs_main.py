# -*- coding: utf-8 -*-
"""三国杀主事件引擎与入口"""
import asyncio
import os
import random
from agentscope.agent import ReActAgent
from agentscope.model import OpenAIChatModel
from agentscope.message import Msg
from agentscope.formatter import DashScopeMultiAgentFormatter

from sgs_config import ROLES_SETUP
from sgs_schemas import ActionModel, DodgeModel, DiscardModel, ReflectionModel, AOEResponseModel, NullificationResponseModel, GuanShiFuResponseModel, SimpleTraitModel
from sgs_state import GameEngine, WEAPON_DESC
from sgs_prompts import get_system_prompt, get_simple_trait_prompt

# 5名首发武将
NAMES = ["刘备", "曹操", "孙权", "诸葛亮", "貂蝉"]

class SGSGame:
    def __init__(self):
        # 随机分配身份
        random.shuffle(ROLES_SETUP)
        self.engine = GameEngine(NAMES, ROLES_SETUP)
        self.agents = {}
        self.belief_states = {name: "游戏刚开始，尚未收集到任何情报。" for name in NAMES}
        
        # 初始化模型 (如果配置了环境变量，这里的占位符会被覆盖)
        self.model = OpenAIChatModel(
            model_name=os.getenv("LLM_MODEL_ID", "qwen-max"), 
            api_key=os.getenv("LLM_API_KEY", "sk-37e7c3a7a45a4aefa0b8b60ca4821dd2"),
            client_args={
                "base_url": os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            }
        )
        
    async def broadcast(self, content: str):
        """全局播报"""
        print(f"\n📢 [系统播报]: {content}")
        msg = Msg(name="System", role="system", content=content)
        for agent in self.agents.values():
            await agent.observe(msg)

    async def handle_kill_event(self, attacker_name: str, target_name: str):
        """处理回合外中断：杀-闪机制，以及贯石斧、古锭刀结算"""
        target_state = self.engine.players[target_name]
        target_agent = self.agents[target_name]
        attacker_state = self.engine.players[attacker_name]
        
        if not attacker_state.is_alive or not target_state.is_alive:
            return

        attacker_weapon = attacker_state.equip_area["weapon"]
        
        # [实装：古锭刀] 计算基础伤害
        base_damage = 2 if (attacker_weapon and attacker_weapon["name"] == "古锭刀" and len(target_state.hand_cards) == 0) else 1
        
        # 1. 如果目标根本没有闪
        if not any(c['name'] == '闪' for c in target_state.hand_cards):
            if base_damage > 1:
                await self.broadcast(f"🗡️ 【古锭刀】锋芒毕露！{target_name} 处于空城状态，受到 {base_damage} 点巨额伤害！")
            else:
                await self.broadcast(f"💔 {target_name} 并没有【闪】，无法闪避！受到1点伤害！")
            target_state.hp -= base_damage
            return
            
        # 2. 目标有闪，向目标发起闪避请求
        msg = Msg(
            name="System", role="system",
            content=(
                f"🚨 警告：{attacker_name} 对你使用了【杀】！\n"
                f"⚠️【你的性格直觉】：{target_state.personality_profile}\n"
                f"你当前血量：{target_state.hp}\n你的手牌：{target_state.get_hand_str()}\n请决定是否出【闪】。"
            )
        )
        
        target_dodged = False
        try:
            res = await target_agent(msg, structured_model=DodgeModel)
            data = res.metadata
            if data.get("play_dodge") and data.get("card_id"):
                if self.engine.validate_and_consume(target_name, data.get("card_id"), "闪"):
                    await self.broadcast(f"🛡️ {target_name} 成功打出【闪】躲避了攻击！(OS: {data.get('reasoning')})")
                    target_dodged = True
        except Exception as e:
            pass # 发生异常视为没闪出，交由下方判定

        # 3. 结算闪避结果与【贯石斧】追击逻辑
        if target_dodged:
            # [实装：贯石斧]
            if attacker_weapon and attacker_weapon["name"] == "贯石斧" and len(attacker_state.hand_cards) >= 2:
                await self.broadcast(f"🪓 {attacker_name} 装备了【贯石斧】，正在考虑是否强行破防...")
                
                axe_msg = Msg(
                    name="System", role="system",
                    content=(
                        f"🪓 你的【杀】被 {target_name} 的【闪】抵消了。你装备了【贯石斧】，且手牌数充足。\n"
                        f"⚠️【冲动约束】：{attacker_state.personality_profile}\n" # [架构师补漏]
                        f"你的手牌：{attacker_state.get_hand_str()}\n"
                        f"请问是否弃置两张手牌，令此【杀】依然造成 {base_damage} 点伤害？"
                    )
                )
                try:
                    axe_res = await self.agents[attacker_name](axe_msg, structured_model=GuanShiFuResponseModel)
                    axe_data = axe_res.metadata
                    
                    if axe_data.get("use_skill") and len(axe_data.get("discard_card_ids", [])) == 2:
                        c1, c2 = axe_data["discard_card_ids"][0], axe_data["discard_card_ids"][1]
                        # 校验两张牌是否都在手里且不相同
                        if c1 != c2 and attacker_state.has_card_id(c1) and attacker_state.has_card_id(c2):
                            self.engine.validate_and_consume(attacker_name, c1)
                            self.engine.validate_and_consume(attacker_name, c2)
                            await self.broadcast(f"🪓 【贯石斧】裂地劈山！{attacker_name} 弃置两张牌强行破防！(OS: {axe_data.get('reasoning')})")
                            await self.broadcast(f"🩸 {target_name} 无法阻挡，受到 {base_damage} 点伤害！")
                            target_state.hp -= base_damage
                            return
                        else:
                            await self.broadcast(f"⚠️ {attacker_name} 提供的弃牌不合法，【贯石斧】发动失败。")
                    else:
                        await self.broadcast(f"💨 {attacker_name} 决定保留手牌，不发动【贯石斧】。")
                except Exception:
                    await self.broadcast(f"❌ {attacker_name} 响应超时，放弃发动【贯石斧】。")
            
            # 如果没有贯石斧，或者选择不发动
            return 
            
        else:
            # 目标没打出有效闪
            if base_damage > 1:
                await self.broadcast(f"🗡️ 【古锭刀】发威！{target_name} 受到 {base_damage} 点巨额伤害！")
            else:
                await self.broadcast(f"🩸 {target_name} 未打出有效【闪】，受到 1 点伤害！")
            target_state.hp -= base_damage

    async def handle_aoe_event(self, attacker_name: str, card_name: str):
        """处理全局 AOE 结算 (南蛮入侵/万箭齐发)"""
        req_card = "杀" if card_name == "南蛮入侵" else "闪"
        damage_msg = "受到1点伤害！"
        
        ordered_names = self.engine.seat_order
        start_idx = ordered_names.index(attacker_name)
        
        # 按座位顺序依次结算
        for i in range(1, len(ordered_names)):
            target_name = ordered_names[(start_idx + i) % len(ordered_names)]
            target_state = self.engine.players[target_name]
            if not target_state.is_alive: continue
            
            # 每波及一个人，先询问是否有无懈可击！
            is_nul = await self.resolve_nullification_stack(card_name, target_name, self.engine.seat_order.index(attacker_name))
            if is_nul:
                await self.broadcast(f"✨ 锦囊效果被抵消，{target_name} 免受【{card_name}】波及！")
                continue

            # 预剪枝
            if not any(c['name'] == req_card for c in target_state.hand_cards):
                await self.broadcast(f"💔 {target_name} 没有【{req_card}】，被【{card_name}】波及，受到1点伤害！")
                target_state.hp -= 1
                continue
                
            msg = Msg(
                name="System", role="system",
                content=(
                    f"🚨 警告：{attacker_name} 发动了【{card_name}】！你需要打出一张【{req_card}】。\n"
                    f"⚠️【你的性格直觉】：{target_state.personality_profile}\n" 
                    f"你的手牌：{target_state.get_hand_str()}\n请决定是否打出。"
                )
            )
            try:
                res = await self.agents[target_name](msg, structured_model=AOEResponseModel)
                data = res.metadata
                if data.get("play_card") and data.get("card_id"):
                    if self.engine.validate_and_consume(target_name, data.get("card_id"), req_card):
                        await self.broadcast(f"🛡️ {target_name} 打出【{req_card}】，成功抵御了【{card_name}】！")
                        continue
                await self.broadcast(f"🩸 {target_name} 未打出【{req_card}】，受到1点伤害！")
                target_state.hp -= 1
            except Exception:
                await self.broadcast(f"❌ {target_name} 响应超时，默认扣血！")
                target_state.hp -= 1

    async def handle_duel_event(self, attacker_name: str, target_name: str):
        """[架构师新增]: 处理【决斗】的双向结算"""
        await self.broadcast(f"🤺 {attacker_name} 拔出剑，向 {target_name} 发起了【决斗】！")
        
        # 决斗发起前，询问无懈可击
        is_nul = await self.resolve_nullification_stack("决斗", target_name, self.engine.seat_order.index(attacker_name))
        if is_nul:
            await self.broadcast("✨ 【决斗】被无懈可击彻底抵消，双方和平收场。")
            return
        
        current_req = target_name
        current_atk = attacker_name
        
        while True:
            state = self.engine.players[current_req]
            if not any(c['name'] == "杀" for c in state.hand_cards):
                await self.broadcast(f"💔 {current_req} 手中无【杀】可打出，在决斗中败北！受到1点伤害！")
                state.hp -= 1
                break
                
            msg = Msg(
                name="System", role="system",
                content=(
                    f"🚨 警告：你正在与 {current_atk} 进行【决斗】！你必须打出一张【杀】，否则将受到1点伤害。\n"
                    f"⚠️【战意约束】：{state.personality_profile}\n"
                    f"你的手牌：{state.get_hand_str()}"
                )
            )
            
            try:
                res = await self.agents[current_req](msg, structured_model=AOEResponseModel)
                data = res.metadata
                if data.get("play_card") and data.get("card_id") and self.engine.validate_and_consume(current_req, data.get("card_id"), "杀"):
                    await self.broadcast(f"⚔️ {current_req} 打出了【杀】！决斗继续，压力给到了 {current_atk}！")
                    # 身份反转，另一个人必须出杀
                    current_req, current_atk = current_atk, current_req
                else:
                    await self.broadcast(f"🩸 {current_req} 放弃或未成功打出【杀】，决斗败北，受到1点伤害！")
                    state.hp -= 1
                    break
            except Exception:
                await self.broadcast(f"❌ {current_req} 响应超时，决斗败北，扣血！")
                state.hp -= 1
                break
    
    async def handle_borrow_sword_event(self, attacker_name: str, target_name: str, secondary_target: str):
        """处理【借刀杀人】的交互博弈栈"""
        target_state = self.engine.players[target_name]
        attacker_state = self.engine.players[attacker_name]
        
        # 预先检查无懈可击
        is_nul = await self.resolve_nullification_stack("借刀杀人", target_name, self.engine.seat_order.index(attacker_name))
        if is_nul:
            await self.broadcast("✨ 【借刀杀人】被无懈可击彻底抵消，武器保住了！")
            return
            
        # 向借刀目标施压：交出杀，还是交出武器？
        msg = Msg(
            name="System", role="system",
            content=(
                f"🚨 警告：{attacker_name} 对你使用了【借刀杀人】！要求你对 {secondary_target} 出【杀】。\n"
                f"⚠️【性格直觉】：{target_state.personality_profile}\n" # [架构师补漏]
                f"如果你不出【杀】，你的武器【{target_state.equip_area['weapon']['name']}】将被夺走！\n"
                f"你的手牌：{target_state.get_hand_str()}\n"
                f"请决定是否为了保住武器而打出【杀】。"
            )
        )
        
        try:
            # 这里的交互逻辑和面临南蛮入侵一样，可以直接复用 AOEResponseModel
            res = await self.agents[target_name](msg, structured_model=AOEResponseModel)
            data = res.metadata
            if data.get("play_card") and data.get("card_id") and self.engine.validate_and_consume(target_name, data.get("card_id"), "杀"):
                await self.broadcast(f"⚔️ {target_name} 迫于压力为了保住武器，对 {secondary_target} 打出了【杀】！(OS: {data.get('reasoning')})")
                # 嵌套调用我们早已写好的杀-闪机制
                await self.handle_kill_event(target_name, secondary_target)
            else:
                raise Exception("Refused or failed to play Kill")
        except Exception:
            # 不出杀的惩罚：武器转移
            weapon = target_state.equip_area["weapon"]
            target_state.equip_area["weapon"] = None
            attacker_state.hand_cards.append(weapon)
            await self.broadcast(f"🗡️ {target_name} 拒绝或无法出【杀】，其武器【{weapon['name']}】被 {attacker_name} 抢入手中！")

    async def resolve_nullification_stack(self, original_trick: str, target_name: str, current_node_idx: int) -> bool:
        """递归并发处理【无懈可击】。返回 True 表示原锦囊被成功抵消。"""
        eligible = []
        n = len(self.engine.seat_order)
        # 预剪枝：只找活着且手里有无懈可击的人，严格按照座次逆时针排优先级
        for i in range(n):
            idx = (current_node_idx + i) % n
            p_name = self.engine.seat_order[idx]
            if self.engine.players[p_name].is_alive and self.engine.players[p_name].has_card_name("无懈可击"):
                eligible.append((i, p_name))
        
        if not eligible:
            return False
            
        # 并发扇出询问
        tasks = []
        for priority, p_name in eligible:
            msg = Msg(
                name="System", role="system",
                content=(
                    f"🚨 锦囊打断：当前正在结算【{original_trick}】，目标是 {target_name}。\n"
                    f"⚠️【潜意识唤醒】：{self.engine.players[p_name].personality_profile}\n" # [架构师补漏]
                    f"你手中有【无懈可击】，请根据局势决定是否打出以抵消其效果。"
                )
            )
            tasks.append(self.agents[p_name](msg, structured_model=NullificationResponseModel))
            
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 收集有效响应并按优先级重排
        valid_res = []
        for (priority, p_name), res in zip(eligible, responses):
            if not isinstance(res, Exception) and res.metadata and res.metadata.get("play_card") and res.metadata.get("card_id"):
                valid_res.append((priority, p_name, res.metadata.get("card_id"), res.metadata.get("reasoning", "")))
                
        valid_res.sort(key=lambda x: x[0])
        
        # 依优先级结算
        for i, (priority, p_name, card_id, reasoning) in enumerate(valid_res):
            if self.engine.validate_and_consume(p_name, card_id, "无懈可击"):
                await self.broadcast(f"🛡️ 【无懈可击！】 {p_name} 拍出一张无懈可击拦截了结算！(OS: {reasoning})")
                # 递归嵌套：询问是否有人无懈掉这张无懈可击
                is_nullified = await self.resolve_nullification_stack("无懈可击", p_name, self.engine.seat_order.index(p_name))
                
                if not is_nullified:
                    # [架构师修复]: 处理并发产生的“幻觉记忆”。向后排抢答失败的 Agent 注入记忆纠偏补丁
                    for j in range(i + 1, len(valid_res)):
                        missed_p_name = valid_res[j][1]
                        correction_msg = Msg(
                            name="System", role="system",
                            content=f"⚠️ 系统记忆纠偏：虽然你刚才决定打出【无懈可击】，但由于 {p_name} 座次优先级更高且成功抵消了目标，你的无懈可击并未被系统扣除，仍保留在你的手牌中。请在后续博弈中纠正这一错觉。"
                        )
                        # 仅对抢答失败的玩家单独发送私人观察消息，不进行全局广播
                        await self.agents[missed_p_name].observe(correction_msg)
                        
                    return True # 无人反驳，成功抵消原始锦囊
        return False
    
    async def play_phase(self, active_name: str):
        """出牌阶段循环"""
        active_agent = self.agents[active_name]
        active_state = self.engine.players[active_name]
        kill_count = 0 
        
        while active_state.is_alive:
            public_info = self.engine.get_public_state()
            hand_info = active_state.get_hand_str()
            
            # [方向一 & 方向三] 动态注入：计算合法距离目标，并注入上一轮的反思记忆
            valid_kill_targets = self.engine.get_valid_kill_targets(active_name)
            current_belief = self.belief_states[active_name]
            
            # 提取武器信息，强行注入 Prompt 唤醒 AI 的武器战术认知
            weapon = active_state.equip_area["weapon"]
            weapon_info = f"【已装备武器】: {weapon['name']} - {WEAPON_DESC.get(weapon['name'], '')}" if weapon else "【已装备武器】: 无"
            
            msg = Msg(
                name="System", role="system",
                content=(
                    f"=== 你的出牌阶段 ===\n场上公开信息: {public_info}\n"
                    f"【潜意识唤醒】：请严格遵循你的玩家设定 -> {active_state.personality_profile}\n"
                    f"【你的内部推理记忆】: {current_belief}\n"
                    f"你的血量: {active_state.hp}\n你的手牌: {hand_info}\n"
                    f"🗡️ {weapon_info} (请在制定战术时充分利用武器特性！)\n"
                    f"⚠️ 距离限制：根据当前位置，你若出【杀】，合法目标仅限：{valid_kill_targets}\n"
                    "请选择出牌或结束回合。如果出锦囊牌请务必指定目标(target)。如果你打出【借刀杀人】，必须同时指定 target 和 secondary_target。\n"
                    "⚠️【输出格式强约束】：务必在JSON中输出 `action_type` 字段（值为 'play_card' 或 'end_phase'），切勿输出 'play_card': True 等错误格式！"
                )
            )
            
            # [架构师优化]: 加入网络容错重试机制 (最高重试 3 次)
            data = None
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    res = await active_agent(msg, structured_model=ActionModel)
                    data = res.metadata
                    break # 成功则跳出重试循环
                except Exception as e:
                    # print(f"   [网络异常] {active_name} 报错: {type(e).__name__} - {str(e)}")
                    if attempt < max_retries - 1:
                        print(f"   [网络波动] {active_name} 的大模型请求超时，正在进行第 {attempt+1} 次重试...")
                        await asyncio.sleep(2) # 缓冲2秒
                    else:
                        await self.broadcast(f"❌ {active_name} 的大脑连接中断，系统强制结束其出牌阶段。")
            
            # 如果重试 3 次都没拿到数据，强制跳出出牌循环
            if not data:
                break
            
            if data.get("action_type") == "end_phase":
                await self.broadcast(f"{active_name} 结束了出牌阶段。")
                break
                
            card_id = data.get("card_id")
            target = data.get("target")
            
            card_obj = next((c for c in active_state.hand_cards if c['uuid'] == card_id), None)
            if not card_obj:
                await self.broadcast(f"⚠️ {active_name} 试图使用不存在的手牌，视为无效操作。")
                continue
                
            card_name = card_obj['name']
            
            if card_name == "杀" and kill_count >= 1:
                current_weapon = active_state.equip_area["weapon"]
                if not (current_weapon and current_weapon["name"] == "诸葛连弩"):
                    await self.broadcast(f"⚠️ {active_name} 本回合已出过【杀】，且未装备【诸葛连弩】，无法再次使用。")
                    continue

            # 物理引擎校验与结算
            if self.engine.validate_and_consume(active_name, card_id):
                target_state = self.engine.players.get(target) if target else None
                
                # ==== 1. 基本牌 ====
                if card_name == "杀" and target_state and target_state.is_alive:
                    if target not in valid_kill_targets:
                        await self.broadcast(f"⚠️ {active_name} 试图对距离外的 {target} 出【杀】(系统阻断，卡牌作废进弃牌堆)。")
                        continue
                    
                    # 检查诸葛连弩
                    weapon = active_state.equip_area["weapon"]
                    if not (weapon and weapon["name"] == "诸葛连弩"):
                        kill_count += 1
                        
                    await self.broadcast(f"⚔️ {active_name} 对 {target} 打出了【杀】！(OS: {data.get('reasoning')})")
                    await self.handle_kill_event(active_name, target)
                    
                elif card_name == "桃":
                    if active_state.hp < active_state.max_hp:
                        active_state.hp += 1
                        await self.broadcast(f"🍑 {active_name} 吃了【桃】，回复1点体力！当前体力: {active_state.hp}")
                    else:
                        await self.broadcast(f"⚠️ {active_name} 体力满，白白浪费【桃】。")
                
                # ==== 2. 装备牌 ====
                elif card_name in ["-1马", "+1马", "诸葛连弩", "青釭剑", "雌雄双股剑", "青龙偃月刀", "丈八蛇矛", "古锭刀", "寒冰剑", "麒麟弓", "贯石斧", "方天画戟", "朱雀羽扇"]:
                    equip_card = self.engine.discard_pile.pop() 
                    
                    equip_type = "weapon"
                    if card_name == "-1马": equip_type = "minus_mount"
                    elif card_name == "+1马": equip_type = "plus_mount"
                    
                    # [修复]: 顶替旧装备，将其放入弃牌堆
                    old_equip = active_state.equip_area[equip_type]
                    if old_equip:
                        self.engine.discard_pile.append(old_equip)
                        
                    active_state.equip_area[equip_type] = equip_card
                    await self.broadcast(f"🛡️ {active_name} 装备了【{card_name}】！")

                # ==== 3. 锦囊牌 ====
                elif card_name == "无中生有":
                    await self.broadcast(f"🎁 {active_name} 打出【无中生有】，企图摸牌！")
                    if not await self.resolve_nullification_stack("无中生有", active_name, self.engine.seat_order.index(active_name)):
                        self.engine.draw_cards(active_name, 2)
                        await self.broadcast(f"✅ 效果生效，{active_name} 摸了2张牌！")
                    
                elif card_name in ["南蛮入侵", "万箭齐发"]:
                    await self.broadcast(f"🔥 {active_name} 丧心病狂地发动了【{card_name}】！全场戒备！")
                    await self.handle_aoe_event(active_name, card_name)
                    
                elif card_name == "桃园结义":
                    await self.broadcast(f"🌸 {active_name} 发动【桃园结义】！全场回血！")
                    for p in self.engine.players.values():
                        if p.is_alive and p.hp < p.max_hp:
                            p.hp += 1
                
                elif card_name == "五谷丰登":
                    await self.broadcast(f"🌾 {active_name} 发动【五谷丰登】！天降祥瑞！")
                    for p_name in self.engine.seat_order:
                        if not self.engine.players[p_name].is_alive: continue
                        # [修复]: 五谷丰登对每个人生效前都可能被无懈
                        if await self.resolve_nullification_stack("五谷丰登", p_name, self.engine.seat_order.index(active_name)):
                            await self.broadcast(f"✨ {p_name} 拒绝了施舍（被无懈抵消），无法摸牌！")
                        else:
                            self.engine.draw_cards(p_name, 1)
                            await self.broadcast(f"🌾 {p_name} 从五谷中摸取了 1 张牌。")
                
                elif card_name == "决斗" and target_state and target_state.is_alive:
                    await self.broadcast(f"🤺 {active_name} 拔出剑，向 {target} 发起了【决斗】！(OS: {data.get('reasoning')})")
                    await self.handle_duel_event(active_name, target)

                elif card_name == "借刀杀人" and target_state and target_state.is_alive and target != active_name:
                    secondary_target = data.get("secondary_target")
                    sec_state = self.engine.players.get(secondary_target)
                    
                    # 极其严密的物理阻断校验
                    if not sec_state or not sec_state.is_alive or secondary_target == target:
                        await self.broadcast(f"⚠️ {active_name} 试图使用的【借刀杀人】第二目标不合法(系统阻断，卡牌作废进弃牌堆)。")
                        continue
                        
                    if not target_state.equip_area["weapon"]:
                        await self.broadcast(f"⚠️ {active_name} 试图对没有装备武器的 {target} 使用【借刀杀人】(系统阻断，卡牌作废进弃牌堆)。")
                        continue
                        
                    # 校验 secondary_target 是否在 target 的攻击范围内
                    valid_targets_for_target = self.engine.get_valid_kill_targets(target)
                    if secondary_target not in valid_targets_for_target:
                        await self.broadcast(f"⚠️ {active_name} 试图借刀杀人，但 {secondary_target} 不在 {target} 的攻击范围内(系统阻断，卡牌作废进弃牌堆)。")
                        continue
                        
                    await self.broadcast(f"🗡️ {active_name} 对 {target} 使用了【借刀杀人】，企图借其武器击杀 {secondary_target}！(OS: {data.get('reasoning')})")
                    # 唤起我们在上面写好的博弈栈
                    await self.handle_borrow_sword_event(active_name, target, secondary_target)

                elif card_name == "过河拆桥" and target_state and target_state.is_alive and target != active_name:
                    await self.broadcast(f"💥 {active_name} 企图对 {target} 使用【过河拆桥】！")
                    if not await self.resolve_nullification_stack("过河拆桥", target, self.engine.seat_order.index(active_name)):
                        discarded = self.engine.random_discard_from_target(target)
                        if discarded:
                            await self.broadcast(f"✅ 拆除成功！{target} 被拆掉了一张手牌。")
                        else:
                            await self.broadcast(f"🤷‍♂️ {target} 没牌可拆。")
                        
                elif card_name == "顺手牵羊" and target_state and target_state.is_alive and target != active_name:
                    # 增加了 target != active_name，禁止顺自己
                    if target not in self.engine.get_valid_kill_targets(active_name, is_trick=True):
                        await self.broadcast(f"⚠️ {active_name} 距离不够，无法对 {target} 顺手牵羊(卡牌作废)。")
                        continue
                    await self.broadcast(f"🤲 {active_name} 企图对 {target} 使用【顺手牵羊】！")
                    if not await self.resolve_nullification_stack("顺手牵羊", target, self.engine.seat_order.index(active_name)):
                        stolen = self.engine.random_discard_from_target(target)
                        if stolen:
                            self.engine.discard_pile.pop()
                            active_state.hand_cards.append(stolen)
                            await self.broadcast(f"✅ 牵羊成功！{active_name} 偷走了 {target} 的一张牌！")

                elif card_name in ["乐不思蜀", "闪电"]:
                    if target_state and target_state.is_alive:
                        # 将锦囊挂入目标判定区
                        judge_card = self.engine.discard_pile.pop()
                        target_state.judge_area.append(judge_card)
                        await self.broadcast(f"⚡ {active_name} 将【{card_name}】贴在了 {target} 的脑门上！")
                        
                else:
                    await self.broadcast(f"🎴 {active_name} 打出了【{card_name}】。(功能暂缓生效，进入弃牌堆)")
            
            # 死亡结算与资产清算。防止死者将牌带出游戏导致的牌库枯竭
            for name, p in self.engine.players.items():
                if p.hp <= 0 and p.is_alive:
                    p.is_alive = False
                    await self.broadcast(f"💀 【击杀通告】玩家 {name} (身份:{p.role}) 阵亡！")
                    
                    # 强行剥夺死者所有手牌、装备与判定牌，全部打入弃牌堆
                    if p.hand_cards:
                        self.engine.discard_pile.extend(p.hand_cards)
                        p.hand_cards.clear()
                    
                    for equip_key in ["weapon", "plus_mount", "minus_mount"]:
                        if p.equip_area[equip_key]:
                            self.engine.discard_pile.append(p.equip_area[equip_key])
                            p.equip_area[equip_key] = None
                            
                    if p.judge_area:
                        self.engine.discard_pile.extend(p.judge_area)
                        p.judge_area.clear()
            
            if self.engine.check_win():
                break

    async def discard_phase(self, active_name: str):
        """弃牌阶段"""
        active_state = self.engine.players[active_name]
        overflow = len(active_state.hand_cards) - active_state.hp
        
        if overflow > 0:
            # [架构师优化 1]：增强提示词，强制约束 JSON 字段名和数组格式
            msg = Msg(
                name="System", role="system",
                content=(
                    f"【弃牌阶段强约束】你的手牌上限为 {active_state.hp}，当前手牌超载，必须严格弃置 {overflow} 张牌。\n"
                    f"⚠️【性格直觉】：根据你的风格决定牌的去留优先级 -> {active_state.personality_profile}\n" # [架构师补漏]
                    f"当前手牌: {active_state.get_hand_str()}\n"
                    f"请务必在返回的 JSON 中，将你要弃置的卡牌 uuid 放入 `discard_card_ids` 列表中（例如: [\"uuid1\", \"uuid2\"]）。"
                )
            )
            
            discard_ids = []
            
            # [架构师优化 2]：加入专门针对格式错误的重试机制
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    res = await self.agents[active_name](msg, structured_model=DiscardModel)
                    
                    # 严密校验大模型是否真的输出了我们需要的字段
                    if res.metadata and "discard_card_ids" in res.metadata:
                        discard_ids = res.metadata.get("discard_card_ids", [])
                        if isinstance(discard_ids, list):
                            break  # 格式完全正确，跳出重试循环
                            
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"   [格式修正] {active_name} 的弃牌格式输出偏离契约，系统正在打回重试 ({attempt+1}/{max_retries})...")
                        await asyncio.sleep(1)
                    else:
                        print(f"   [格式崩溃] {active_name} 无法输出正确的弃牌 JSON，系统将接管。")

            # 物理引擎校验与实际扣除
            actual_discarded = 0
            for cid in discard_ids[:overflow]:
                if self.engine.validate_and_consume(active_name, cid):
                    actual_discarded += 1

            # 容错兜底：如果 AI 乱填不存在的 UUID，或者多次重试依然失败，系统强行从头开始随机弃牌补足数量
            while actual_discarded < overflow:
                fallback_cid = active_state.hand_cards[0]['uuid']
                self.engine.validate_and_consume(active_name, fallback_cid)
                actual_discarded += 1
                
            await self.broadcast(f"🗑️ {active_name} 弃置了 {overflow} 张牌。")

    async def reflection_phase(self, round_num: int):
        """[方向三] 每轮结束时的反思与身份推演阶段"""
        await self.broadcast(f"🧠 第 {round_num} 轮结束，进入各武将内部反思推演阶段（暗中进行）...")
        
        for name in NAMES:
            if not self.engine.players[name].is_alive: continue
            
            agent = self.agents[name]
            
            # [架构师优化]: 强约束提示词，精确到字段名和数据类型，防止 Pydantic 解析崩溃
            msg = Msg(
                name="System", role="system",
                content=(
                    f"第 {round_num} 轮已结束。请根据刚刚本轮中各玩家的出牌流向（谁杀谁、谁拆谁）、死亡情况，"
                    f"以及你的身份({self.engine.players[name].role})，重新推演场上存活玩家的身份，并制定下回合宏观策略。\n\n"
                    f"【性格铁律】：在制定下一轮宏观策略时，绝对不能偏离你的玩家本性 -> {self.engine.players[name].personality_profile}\n\n"
                    "⚠️【推演约束（请直接调用系统工具输出结果）】：\n"
                    "请按照下面的 JSON 格式输出数据！尽量不要带有任何多余的自然语言解释！\n"
                    "1. 'inferences' 字段是一个列表，列表内的每个对象必须严格包含以下 4 个确切的键名：\n"
                    "   - 'player_name': 玩家名字（绝对不能写成 'player'）\n"
                    "   - 'suspected_role': 推测身份（绝对不能写成 'identity'）\n"
                    "   - 'confidence': 确信度，必须是 1 到 100 之间的【整数】（例如 80，绝对不能用 0.8 这种小数）\n"
                    "   - 'reasoning': 推测理由\n"
                    "2. 'next_round_strategy': 下一回合的宏观策略字符串。"
                )
            )
            
            max_retries = 3
            success = False
            
            for attempt in range(max_retries):
                try:
                    res = await agent(msg, structured_model=ReflectionModel)
                    
                    # 严密校验结构化化输出的结果
                    if res.metadata and "inferences" in res.metadata and "next_round_strategy" in res.metadata:
                        inferences = res.metadata.get("inferences", [])
                        strategy = res.metadata.get("next_round_strategy", "")
                        
                        memory_str = f"你制定的策略: {strategy}。 对他人的推演: "
                        memory_str += " | ".join([
                            f"{inf.get('player_name', '未知')}:{inf.get('suspected_role', '未知')}"
                            f"(确信度{inf.get('confidence', 0)}% - {inf.get('reasoning', '')})" 
                            for inf in inferences
                        ])
                        
                        self.belief_states[name] = memory_str
                        # 强制提取大模型的元数据并打印，确保开发者拥有100%视角的监控
                        print(f"\n   💡 [上帝视角 - {name} 的内部反思推演]:\n   >>> {memory_str}") 
                        success = True
                        break # 解析完美，跳出重试循环
                        
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"   [反思格式修正] {name} 的推演格式偏离契约，系统正在打回重做 ({attempt+1}/{max_retries})...")
                        await asyncio.sleep(1.5)
                    else:
                        print(f"   [反思崩溃] {name} 多次尝试均无法输出正确 JSON格式，本轮维持原有认知。")
            
            if not success:
                # 容错兜底：保留上一轮的记忆，不作更新
                pass

    async def run(self):
        """游戏主循环"""
        await self.broadcast("🎉 三国杀 Agent 5人局 MVP 版本启动！")
        await self.broadcast("🧬 正在通过大模型为各位武将注入真实的【灰度人格】灵魂，请稍候...")
        
        for i, (name, role) in enumerate(zip(NAMES, ROLES_SETUP)):
            print(f"\n⏳ 正在为玩家 [{name}] 随机抽取人类灵魂...")
            
            # 生成一个 1~99999 的混沌种子，强迫大模型在隐空间中漫游
            chaos_seed = random.randint(1, 99999)
            
            # 临时Agent，彻底剥离武将名字，防止幻觉
            temp_agent = ReActAgent(
                name=f"Gen_HumanPlayer_{i}",
                sys_prompt="你是三国杀玩家风格设定器。",
                model=self.model,
                formatter=DashScopeMultiAgentFormatter()
            )
            # 传入混沌种子，完全不传武将名字
            prompt_msg = Msg(name="System", role="system", content=get_simple_trait_prompt(chaos_seed))
            
            meta = None
            for attempt in range(3):
                try:
                    res = await temp_agent(prompt_msg, structured_model=SimpleTraitModel)
                    if res.metadata: 
                        meta = res.metadata
                        break
                except Exception:
                    await asyncio.sleep(1)
                    
            if meta:
                style_name = meta.get('style_name', '普通')
                action_rule = meta.get('action_rule', '正常打牌')
                profile = f"风格：{style_name}。习惯：{action_rule}"
                print(f"💡 [风格注入] {name} -> 【{style_name}】: {action_rule}")
            else:
                profile = "正常发挥，追求胜利。"
                print(f"⚠️ [风格注入] {name} -> 采用默认风格")
            
            self.engine.players[name].personality_profile = profile
            
            # 实例化正式Agent
            self.agents[name] = ReActAgent(
                name=name,
                sys_prompt=get_system_prompt(name, role, profile),
                model=self.model,
                formatter=DashScopeMultiAgentFormatter()
            )
        
        # 初始发牌 (每人4张)
        for name in NAMES:
            self.engine.draw_cards(name, 4)
            
        # [架构师优化]: 寻找主公，并重排序玩家出手顺位
        lord_name = next(n for n, p in self.engine.players.items() if p.role == "主公")
        lord_idx = NAMES.index(lord_name)
        # 数组切片拼接，让主公排在 index 0 的位置
        ordered_names = NAMES[lord_idx:] + NAMES[:lord_idx]
        
        # 同步更新物理引擎的绝对座位表，否则距离和AOE优先级全错！
        self.engine.seat_order = ordered_names
        
        await self.broadcast(f"👑 【开局通告】本局的主公是：{lord_name}！其余玩家身份隐藏。")
            
        round_num = 1
        while True:
            await self.broadcast(f"\n========== 第 {round_num} 轮开始 ==========")
            
            for active_name in ordered_names: # 使用重新排序后的名单
                if not self.engine.players[active_name].is_alive: continue
                
                await self.broadcast(f"\n👉 轮到 {active_name} 的回合")
                
                active_state = self.engine.players[active_name]
                skip_play_phase = False
                
                # 判定阶段 (处理乐不思蜀、闪电)
                if active_state.judge_area:
                    await self.broadcast(f"⚖️ {active_name} 开始进行判定...")
                    for judge_card in active_state.judge_area[:]:
                        # 摸一张牌作为判定牌
                        judgement = self.engine.draw_cards(active_name, 1)[0]
                        active_state.pop_card(judgement['uuid']) 
                        self.engine.discard_pile.append(judgement)
                        
                        # [架构师优化]: 获取真实的判定牌花色与点数
                        suit = judgement.get("suit", "♠黑桃")
                        number = judgement.get("number", 1)
                        await self.broadcast(f"📜 翻开判定牌：【{suit}{number} - {judgement['name']}】")
                        
                        if judge_card["name"] == "乐不思蜀":
                            if "♥红桃" in suit:
                                await self.broadcast(f"🎉 判定为红桃，{active_name} 乐不思蜀判定【失效】！天佑之！")
                            else:
                                await self.broadcast(f"⛓️ 判定生效！{active_name} 被【乐不思蜀】，跳过出牌阶段！")
                                skip_play_phase = True
                        elif judge_card["name"] == "闪电":
                            if "♠黑桃" in suit and 2 <= number <= 9:
                                await self.broadcast(f"⛈️ 苍天已死！{active_name} 被【闪电】劈中，受到3点雷电伤害！")
                                active_state.hp -= 3
                            else:
                                await self.broadcast(f"☁️ 闪电未劈中，移交下家！(MVP暂作销毁处理)")
                                
                    active_state.judge_area.clear() # 清空判定区
                    
                # 检查判定是否致死，并补上缺失的资产清算与胜利校验钩子
                if active_state.hp <= 0:
                    active_state.is_alive = False
                    await self.broadcast(f"💀 {active_name} 阵亡！")
                    
                    # 资产清算
                    if active_state.hand_cards:
                        self.engine.discard_pile.extend(active_state.hand_cards)
                        active_state.hand_cards.clear()
                    for equip_key in ["weapon", "plus_mount", "minus_mount"]:
                        if active_state.equip_area[equip_key]:
                            self.engine.discard_pile.append(active_state.equip_area[equip_key])
                            active_state.equip_area[equip_key] = None
                    if active_state.judge_area:
                        self.engine.discard_pile.extend(active_state.judge_area)
                        active_state.judge_area.clear()
                        
                    # 必须在这里补上胜利判定阻断，否则主公被劈死游戏不会结束
                    winner = self.engine.check_win()
                    if winner:
                        await self.broadcast(f"\n🏆 游戏结束！{winner}")
                        return
                    continue
                
                # 摸牌阶段
                self.engine.draw_cards(active_name, 2)
                await self.broadcast(f"🃏 {active_name} 摸了2张牌。(当前手牌：{active_state.get_hand_str()})")
                
                # 出牌阶段
                if not skip_play_phase:
                    await self.play_phase(active_name)
                
                winner = self.engine.check_win()
                if winner:
                    await self.broadcast(f"\n🏆 游戏结束！{winner}")
                    return
                    
                # 弃牌阶段
                if self.engine.players[active_name].is_alive:
                    await self.discard_phase(active_name)
                    
            # [方向三] 一整轮（所有人全跑完）结束后，触发全局静默反思
            await self.reflection_phase(round_num)
            
            round_num += 1

if __name__ == "__main__":
    asyncio.run(SGSGame().run())