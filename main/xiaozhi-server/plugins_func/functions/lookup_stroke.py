"""
笔顺查询插件 - 在博亿朗二代屏幕上显示汉字笔顺图片

调用链路：
  孩子说"龍字怎么写"
  → LLM function_call: lookup_stroke(character="龍")
  → 本插件：ord("龍") → 0x9F8D → 图片 URL
  → 直接发送 MCP tools/call("self.screen.preview_image", {url: ...})
    （绕过 call_mcp_tool 的 has_tool 检查，因为 preview_image 是 user_only 工具）
  → 设备从内网下载 PNG 图片 → 屏幕显示笔顺
  → TTS 语音播报

显示格式：
  当前：PNG 静态图（每笔不同颜色 + 序号标注，完整字形）
  未来：如果固件支持 GIF 显示，可切换为 GIF 动画模式（代码已预留）

⚠️ 关键架构约束：
  plugin_executor.py 的 execute() 方法虽然是 async def，但对 SYSTEM_CTL 类型插件
  做的是同步调用：result = func_item.func(conn, **arguments)
  这意味着 lookup_stroke() 运行在事件循环线程中，如果用 run_coroutine_threadsafe()
  往同一个 conn.loop 提交协程再 .result() 阻塞等待 → 死锁！
  解决方案：用新线程+新事件循环发送 WebSocket 消息，避免阻塞 conn.loop。

⚠️ 图片持久显示：
  自定义固件已将 PREVIEW_IMAGE_DURATION_MS 改为 120000（120秒）。
  只需发送一次 preview_image，图片会持续显示 120 秒后自动恢复 Emoji。
  不需要重发循环（重发会导致 GIF 数据 use-after-free 崩溃）。
"""

from plugins_func.register import register_function, ToolType, ActionResponse, Action
from config.logger import setup_logging
from typing import TYPE_CHECKING
import asyncio
import json
import threading

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

# === 配置 ===
# 笔顺图片公网入口。gzcvm NPM stream: 175.178.247.160:18090 → 192.168.1.170:8090
# 这样设备在大陆外网也能下载；香港家里后续可用 OpenWrt/Lucky 劫持 175.178.247.160:18090 到内网。
IMG_BASE_URL = "http://175.178.247.160:18090/strokes"

# 图片格式：优先 GIF（动画笔顺），fallback PNG（静态）
# 设备固件 SetPreviewImage 已支持 GIF 检测和 LvglGif 播放
IMG_FORMAT = "png"          # 默认格式（保证可用）
GIF_ENABLED = True          # 启用 GIF 动画笔顺（设备固件已支持）

# 图片显示策略：
# 自定义固件已将 PREVIEW_IMAGE_DURATION_MS 改为 120000（120秒）
# 不需要重发循环，发送一次即可持久显示
# TTS 结束也不会触发图片消失（已确认代码中只有 preview_timer 控制消失）

# 默认显示繁体字（需求要求）
# 当 LLM 传入简体字时，自动转换为繁体字查找对应 PNG
USE_TRADITIONAL = True

# 测试模式开关（正常使用时设为 False）
TEST_MODE = False
TEST_IMAGES = []
TEST_INTERVAL = 5

# MCP 工具名（设备端注册的名字，带点号）
MCP_ORIGINAL_NAME = "self.screen.preview_image"

# === 简体→繁体转换 ===
# 只包含简繁写法不同的常用字对照
# 格式：简体字 → 繁体字（一一对应）
_S2T_SIMPLE = "万与专业丛东丝两严丧个丰临为丽举义乐书买乱亏云亚产亲亿仅从仓仪们价众优会伞伟传伤伦体余佣侠侣侥侦侧侨俩俭债倾储儿兑党兰关兴养兽内冈册写军农冲决况冻净减凤凭击凿划刘则刚创删剂剑剧劝办务动励劲劳势勋区医华协卖卢卧卫却厂厅历厉压厌厢厦厨县参双发变叙叠叶号叹听吕吗吨启吴呕员呛呜响哑团围图圆圣场坏块坚坛坝坞坟坠垒垦垫墙壮声壳壶处备复够头夸夹夺奋奖奥妆妇妈娄娇婴孙学宁宝实宠审宪宫宽宾对寻导寿将尔尘尧尽层属岁岂岗岚岛岭峡崭巩币帅师帐帘带帮干并广庄庆庐库应庙庞废开异弃张弥弯弹强归当录彻径忆忧怀态总恋恳恶悬惊惨惩惫惭惮惯愤愿慑懒战户扑扩扫扬扰抚担拟拢拣拥拦拧拨择挂挚挛挞挟挠挡挣挤挥捞损捡换据掷搁搅摄摆摇摈摊撑撵攒敌敛数斋断无旧时旷昙显晋晒晓晕暂术朴杂权条来杨杰松极构枢枪枫柜标栈栋栏树样桥桩梦检棉楼榄橱欢欧歼殁残殴毁毕毙毡气氢汇汉汤汹沟没沥沦沧沪泞泪泻泼泽洁洒浅浆浇浊测济浏浑浓涂涌涛涝涟涡涣涤润涨涩渊渍渐渔渗温湾湿溃满滤滥滨滩漓潇潜澜灏灭灯灵灶灿炉炖点炼烁烂烛烟烦烧烨烫热爱爷牵犹独献环现珐琼瑶电画畅畴疗疟疡疮疯痈痉痒痨痪痫瘪瘫瘾癞癣皑盏盐监盖盗盘着睁瞒矫矶矾矿砖砚砺确硕碍碱礼祷祸禀禅离种积称秆秃稳穷窃窍窑窜窝窥竖竞笃笔笼笺筑筛筝签简篮篱类粜粮糁纟纠红纤约级纪纬纯纱纲纳纵纷纸纹纺纽线练组细织终绍经绑绒结绕绘给络绝绞统绢绣绥继绩绪续绮绰绳维绵绷绸综绽绿缀缄缅缆缉缎编缘缚缝缠缤缩缭缰罂网罗罚罢羁翘耸聂聋职联聪肃肠肤肾肿胀胁胆胧胶脉脏脐脑脓脚脱脸腊腻腾舆舰艰艳艺节芜芦苍苏苹范茎荆荐荚荡荣荤荧药莱莲获莹萝营萧葱蒋蒙蓝蔷蔺藓虏虑虚蚀蚁蛊蛮蛰蜕蜗蝇蝉补衬袄袜袭装裤褴觉觉触誉讠计订认讥讨让训议讯记讲许论讼设访诀证评诈诉诊词译试诗诚话诞诡询该详诧语误诱说请诸读课谁调谅谈谊谋谍谎谐谒谓谕谗谙谚谛谜谢谣谤谦谨谬谭谱谴赵赶趋跃踊踌踪蹑躯车轧轨轩转轮软轰轴轻载较辅辆辈辉辍辐辑输辖辗辙辞辩辫边辽达迁过迈运还进远违连迟适选递逻遗邓邮邻郁郑鉴鉴锁针钉钓钟钢钥钩钻铁铃铅铜铝铭银铸铺链锄锅锈锋锐锢锣锤锥锦锭键锯镀镇镜镰长门闪闭问闯闲闷闸闹闻阀阁阅阎阐阔阳阴阵阶际陆陈陕陨险随隐雏雾霭韦韧韩页顶项顺须顽顾顿颁预领颇频颖颗题颜额颠风飘飞饣饥饭饮饰饱饲饵饶饺饼馆馈馋马驭驮驰驱驳驴驶驹驻驼驾骂骄骆骇骑验骗骤髅鱼鲁鲜鲤鲸鸟鸡鸣鸭鸽鹅鹊鹤鹰麦黄齐齿龙龟"
_S2T_TRAD = "萬與專業叢東絲兩嚴喪個豐臨為麗舉義樂書買亂虧雲亞產親億僅從倉儀們價眾優會傘偉傳傷倫體餘傭俠侶僥偵側僑倆儉債傾儲兒兌黨蘭關興養獸內岡冊寫軍農衝決況凍淨減鳳憑擊鑿劃劉則剛創刪劑劍劇勸辦務動勵勁勞勢勳區醫華協賣盧臥衛卻廠廳歷厲壓厭廂廈廚縣參雙發變敘疊葉號嘆聽呂嗎噸啟吳嘔員嗆嗚響啞團圍圖圓聖場壞塊堅壇壩塢墳墜壘墾墊牆壯聲殼壺處備複夠頭誇夾奪奮獎奧妝婦媽婁嬌嬰孫學寧寶實寵審憲宮寬賓對尋導壽將爾塵堯盡層屬歲豈崗嵐島嶺峽嶄鞏幣帥師帳簾帶幫幹並廣莊慶廬庫應廟龐廢開異棄張彌彎彈強歸當錄徹徑憶憂懷態總戀懇惡懸驚慘懲憊慚憚慣憤願懾懶戰戶撲擴掃揚擾撫擔擬攏揀擁攔擰撥擇掛摯攣撻挾撓擋掙擠揮撈損撿換據擲擱攪攝擺搖擯攤撐攆攢敵斂數齋斷無舊時曠曇顯晉曬曉暈暫術樸雜權條來楊傑鬆極構樞槍楓櫃標棧棟欄樹樣橋樁夢檢棉樓欖櫥歡歐殲歿殘毆毀畢斃氈氣氫匯漢湯洶溝沒瀝淪滄滬濘淚瀉潑澤潔灑淺漿澆濁測濟瀏渾濃塗湧濤澇漣渦渙滌潤漲澀淵漬漸漁滲溫灣濕潰滿濾濫濱灘漓瀟潛瀾灝滅燈靈竈燦爐燉點煉爍爛燭煙煩燒燁燙熱愛爺牽猶獨獻環現琺瓊瑤電畫暢疇療瘧瘍瘡瘋癰痙癢癆瘓癇癟癱癮癩癬皚盞鹽監蓋盜盤著睜瞞矯磯礬礦磚硯礪確碩礙鹼禮禱禍稟禪離種積稱稈禿穩窮竊竅窯竄窩窺豎競篤筆籠箋築篩箏簽簡籃籬類糶糧糝糸糾紅纖約級紀緯純紗綱納縱紛紙紋紡紐線練組細織終紹經綁絨結繞繪給絡絕絞統絹繡綏繼績緒續綺綽繩維綿繃綢綜綻綠綴緘緬纜緝緞編緣縛縫纏繽縮繚韁罌網羅罰罷羈翹聳聶聾職聯聰肅腸膚腎腫脹脅膽朧膠脈臟臍腦膿腳脫臉臘膩騰輿艦艱艷藝節蕪蘆蒼蘇蘋範莖荊薦莢蕩榮葷熒藥萊蓮獲瑩蘿營蕭蔥蔣矇藍薔藺蘚虜慮虛蝕蟻蠱蠻蟄蛻蝸蠅蟬補襯襖襪襲裝褲襤覺覺觸譽訁計訂認譏討讓訓議訊記講許論訟設訪訣證評詐訴診詞譯試詩誠話誕詭詢該詳詫語誤誘說請諸讀課誰調諒談誼謀諜謊諧謁謂諭讒諳諺諦謎謝謠謗謙謹謬譚譜譴趙趕趨躍踴躊蹤躡軀車軋軌軒轉輪軟轟軸輕載較輔輛輩輝輟輻輯輸轄輾轍辭辯辮邊遼達遷過邁運還進遠違連遲適選遞邏遺鄧郵鄰鬱鄭鑒鑑鎖針釘釣鐘鋼鑰鉤鑽鐵鈴鉛銅鋁銘銀鑄鋪鏈鋤鍋鏽鋒銳錮鑼錘錐錦錠鍵鋸鍍鎮鏡鐮長門閃閉問闖閒悶閘鬧聞閥閣閱閻闡闊陽陰陣階際陸陳陝隕險隨隱雛霧靄韋韌韓頁頂項順須頑顧頓頒預領頗頻穎顆題顏額顛風飄飛飠飢飯飲飾飽飼餌饒餃餅館饋饞馬馭馱馳驅駁驢駛駒駐駝駕罵驕駱駭騎驗騙驟髏魚魯鮮鯉鯨鳥雞鳴鴨鴿鵝鵲鶴鷹麥黃齊齒龍龜"

# 构建简→繁映射字典
_SIMP_TO_TRAD_MAP = {}
for _s, _t in zip(_S2T_SIMPLE, _S2T_TRAD):
    _SIMP_TO_TRAD_MAP[_s] = _t


def _simp_to_trad(char: str) -> str:
    """简体字转繁体字（单字），如果不在映射表中则返回原字"""
    return _SIMP_TO_TRAD_MAP.get(char, char)


# Function calling 描述
lookup_stroke_function_desc = {
    "type": "function",
    "function": {
        "name": "lookup_stroke",
        "description": (
            "查询汉字写法并在屏幕上显示该字的图片，同时朗读一句包含这个字的常见古诗词。\n"
            "当孩子问某个字怎么写、想看某个字、问笔画顺序时调用此工具。\n"
            "\n"
            "═══════════════════════════════════════════════════════\n"
            "【调用前自检铁律 — 必须做，否则一定出 BUG】\n"
            "═══════════════════════════════════════════════════════\n"
            "\n"
            "**铁律 1：character 必须出现在 context_phrase 里**\n"
            "如果你打算调用 lookup_stroke(character=X, context_phrase=Y)，调用前**先验证**：X 是否真的是 Y 中的一个字？\n"
            "- 如果 X 在 Y 中 → 通过，调用\n"
            "- 如果 X **不在** Y 中 → **绝对不要直接调用**！这一定是 ASR 把 Y 中某个字识别错了。你必须做以下事：\n"
            "  (a) 在 Y 中找一个**和 X 发音相同（或相近）的字** Z，把 character 改成 Z\n"
            "  (b) 例：用户说'小朋友的有字' → 你想用 character='有' 但'有'不在'小朋友' → 看'小朋友'里'友'(yǒu)和'有'(yǒu)同音 → **必须把 character 改成'友'**\n"
            "  (c) 例：用户说'乌龟的归字' → 你想用 character='归' 但'归'不在'乌龟' → 看'乌龟'里'龟'(guī)和'归'(guī)同音 → **必须把 character 改成'龟'**\n"
            "  (d) 如果实在找不到任何同音字替换，把 context_phrase 设为空字符串（不要硬塞一个对不上的 context）\n"
            "\n"
            "**铁律 2：如果用户问句没有'X的Y字'结构（例如'龙字怎么写'、'教我写爱字'），context_phrase 留空**\n"
            "- 不要瞎编 context\n"
            "- character 直接用用户说的字\n"
            "\n"
            "**铁律 3（防止铁律 1 被忽略）**：每次填 context_phrase 之前在心里念一遍：「我填的 character 必须能在 context_phrase 里**逐字**找到，否则我宁可把 context_phrase 留空也不能填错」。\n"
            "\n"
            "═══════════════════════════════════════════════════════\n"
            "【古诗词选择规则 — poem_line 参数】\n"
            "═══════════════════════════════════════════════════════\n"
            "\n"
            "目的：让孩子在学写字的同时学一句古诗。\n"
            "\n"
            "**铁律 4：必须 2 句一对（古诗里相邻的两句，12-20 字），不要只给 1 句**\n"
            "  - 不要带书名号、作者名、解释 —— 只要诗句本身\n"
            "\n"
            "**铁律 5：必须真的包含 character 这个字面字**（服务端会做校验，不含字的诗会被丢弃）\n"
            "\n"
            "**铁律 6：能选大众耳熟能详的（小学课本类）就尽量选耳熟能详的；找不到简单的，给冷门一点的也 OK；只有真的找不到任何包含此字的著名古诗才传空字符串**\n"
            "  - 不要因为不确定就传空 —— 大部分常用字都有著名古诗\n"
            "  - 同一字每次尽量换不同诗，让孩子每次学到新东西\n"
            "  - 例：character='月' 可在以下选项里轮换：\n"
            "       · '床前明月光，疑是地上霜'（李白）\n"
            "       · '海上生明月，天涯共此时'（张九龄）\n"
            "       · '明月几时有，把酒问青天'（苏轼）\n"
            "       · '月落乌啼霜满天，江枫渔火对愁眠'（张继）\n"
            "\n"
            "═══════════════════════════════════════════════════════\n"
            "【完整示例】\n"
            "═══════════════════════════════════════════════════════\n"
            "\n"
            "用户说 → 你应该调用：\n"
            "- '龙马的笼字怎么写' → character='龙', context_phrase='龙马', poem_line='但使龙城飞将在，不教胡马度阴山'\n"
            "  （ASR 纠错：'笼'(lóng)→'龙'(lóng)）\n"
            "- '小朋友的有字怎么写' → character='友', context_phrase='小朋友', poem_line='洛阳亲友如相问，一片冰心在玉壶'\n"
            "  （ASR 纠错：'有'(yǒu)→'友'(yǒu)。注意 character 必须改成'友'！）\n"
            "- '小鸟的鸟字怎么写' → character='鸟', context_phrase='小鸟', poem_line='月出惊山鸟，时鸣春涧中'\n"
            "  （'鸟'已在'小鸟'中，无需纠错）\n"
            "- '春天的春字怎么写' → character='春', context_phrase='春天', poem_line='春眠不觉晓，处处闻啼鸟'（每次轮换不同的春诗）\n"
            "- '璎字怎么写' → character='璎', context_phrase='', poem_line=''  （冷僻字，确实想不到包含此字的诗，传空）\n"
            "- '龙字怎么写' → character='龙', context_phrase='', poem_line='但使龙城飞将在，不教胡马度阴山'  （没上下文，正常处理）"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "character": {
                    "type": "string",
                    "description": "要查询笔顺的单个汉字。**必须**是 context_phrase 中真实存在的某个字（如不存在请按铁律 1 做 ASR 纠错替换）。例：龍、人、愛。",
                },
                "context_phrase": {
                    "type": "string",
                    "description": "（可选）用户说的上下文词组。例如'龙马的龙字怎么写' → '龙马'。⚠️ 填之前必须验证 character 真的在这里面，否则就留空。",
                },
                "poem_line": {
                    "type": "string",
                    "description": "包含 character 的**两句**古诗（12-20 字）。优先选大众耳熟能详的（小学课本），找不到简单的就给冷门一点的也 OK。只有真的找不到任何包含此字的著名古诗才传空字符串。同一字每次尽量换不同诗。",
                },
            },
            "required": ["character"],
        },
    },
}


def _send_mcp_in_new_loop(conn, payload, timeout=15):
    """
    在新线程+新事件循环中发送 MCP 消息并等待设备响应。

    为什么不能用 conn.loop？
    因为 lookup_stroke() 是被 plugin_executor 在 conn.loop 的事件循环线程中
    同步调用的。如果用 run_coroutine_threadsafe(coro, conn.loop).result()，
    会阻塞事件循环线程，导致协程无法被调度 → 死锁。

    解决方案：
    1. 在新线程中创建新的事件循环
    2. 用新事件循环调用 conn.websocket.send()（websockets 支持跨线程 send）
    3. 不阻塞 conn.loop
    """
    result_holder = {"result": None, "error": None}
    done_event = threading.Event()

    def _worker():
        try:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)

            async def _send_and_wait():
                message = json.dumps({"type": "mcp", "payload": payload})
                logger.bind(tag=TAG).info(
                    f"[新线程] 发送 MCP 消息: method={payload.get('method')}, "
                    f"id={payload.get('id')}"
                )
                await conn.websocket.send(message)
                logger.bind(tag=TAG).info(
                    f"[新线程] MCP 消息已发送(id={payload.get('id')})"
                )

            new_loop.run_until_complete(_send_and_wait())
            new_loop.close()
            result_holder["result"] = "sent"
        except Exception as e:
            result_holder["error"] = e
            logger.bind(tag=TAG).error(f"[新线程] 发送 MCP 消息失败: {e}")
        finally:
            done_event.set()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    done_event.wait(timeout=timeout)

    if result_holder["error"]:
        raise result_holder["error"]
    if not done_event.is_set():
        raise TimeoutError("发送 MCP 消息超时")
    return result_holder["result"]





@register_function("lookup_stroke", lookup_stroke_function_desc, ToolType.SYSTEM_CTL)
def lookup_stroke(conn: "ConnectionHandler", character: str, context_phrase: str = "", poem_line: str = ""):
    """查询汉字笔顺，在设备屏幕显示笔顺图片，并朗读一句包含此字的古诗

    参数：
        character:      要查询的单个汉字（LLM 已经做过 ASR 同音字自动纠错）
        context_phrase: 用户说的上下文词组（用于日志观测纠错效果 + 优化 TTS 文案）
        poem_line:      LLM 给的、包含此字的常见古诗词（用于 TTS 朗读，让孩子学一句诗）
    """

    # 0. 观测日志：直接打印 LLM 传过来的两个参数，方便 grep 看自动纠错效果
    #    （如果用户说"龙马的笼字"，LLM 应输出 character="龙", context_phrase="龙马"）
    if context_phrase:
        if character in context_phrase:
            logger.bind(tag=TAG).info(
                f"[ASR-OK] character={character} 在上下文'{context_phrase}'中"
            )
        else:
            logger.bind(tag=TAG).warning(
                f"[ASR-FIX-FAILED?] character={character} 不在上下文'{context_phrase}'中 "
                f"（LLM 可能没找到合适的同音字替代，按原字处理）"
            )
    else:
        logger.bind(tag=TAG).info(f"[ASR-NO-CTX] character={character}（无上下文）")

    # 1. 参数校验
    if not character or len(character.strip()) == 0:
        return ActionResponse(
            action=Action.RESPONSE,
            result="参数为空",
            response="你想查哪个字呀？告诉我一个字就好！",
        )

    # 取第一个字符（防止 LLM 传了多个字）
    char = character.strip()[0]

    # 检查是否是汉字（CJK Unified Ideographs 基本范围 + 扩展）
    cp = ord(char)
    is_cjk = (
        (0x4E00 <= cp <= 0x9FFF)       # CJK Unified Ideographs
        or (0x3400 <= cp <= 0x4DBF)    # CJK Unified Ideographs Extension A
        or (0x20000 <= cp <= 0x2A6DF)  # CJK Unified Ideographs Extension B
        or (0xF900 <= cp <= 0xFAFF)    # CJK Compatibility Ideographs
    )
    if not is_cjk:
        return ActionResponse(
            action=Action.RESPONSE,
            result="非汉字",
            response=char + "好像不是汉字哦，我只能查汉字的笔顺呢！",
        )

    # 2. 简体→繁体转换（需求要求默认显示繁体）
    display_char = char
    if USE_TRADITIONAL:
        trad_char = _simp_to_trad(char)
        if trad_char != char:
            logger.bind(tag=TAG).info(f"简→繁转换: {char} → {trad_char}")
            display_char = trad_char

    # 3. 计算 Unicode hex → 图片 URL
    cp_display = ord(display_char)
    hex_str = format(cp_display, "x")  # 小写十六进制，如 '9f8d'

    # 4. 检查设备是否支持 MCP（有屏幕）
    if not hasattr(conn, "mcp_client") or not conn.mcp_client:
        logger.bind(tag=TAG).warning("设备不支持 MCP，无法显示笔顺图片")
        return ActionResponse(
            action=Action.RESPONSE,
            result="设备无屏幕",
            response=f"你问的是{char}字对吧？可惜我这里没有屏幕，没法显示笔顺呢。",
        )

    # === 测试模式 ===
    if TEST_MODE:
        logger.bind(tag=TAG).info("=" * 60)
        logger.bind(tag=TAG).info("[测试模式] 开始图片格式兼容性测试")
        logger.bind(tag=TAG).info("=" * 60)

        results = []
        for i, (fmt, url) in enumerate(TEST_IMAGES):
            if not hasattr(lookup_stroke, "_call_counter"):
                lookup_stroke._call_counter = 1000
            lookup_stroke._call_counter += 1
            tool_call_id = lookup_stroke._call_counter

            payload = {
                "jsonrpc": "2.0",
                "id": tool_call_id,
                "method": "tools/call",
                "params": {"name": MCP_ORIGINAL_NAME, "arguments": {"url": url}},
            }

            try:
                _send_mcp_in_new_loop(conn, payload, timeout=10)
                results.append(f"{fmt}:已发送")
            except Exception as e:
                results.append(f"{fmt}:发送失败({e})")

            if i < len(TEST_IMAGES) - 1:
                time.sleep(TEST_INTERVAL)

        summary = ", ".join(results)
        return ActionResponse(
            action=Action.RESPONSE,
            result=f"图片格式测试完毕: {summary}",
            response="我在屏幕上依次测试了图片格式。你看看哪些能显示出来！",
        )

    # === 正常模式 ===
    # 确定图片 URL（GIF 优先，fallback PNG）
    img_url = f"{IMG_BASE_URL}/{hex_str}.{IMG_FORMAT}"  # 默认 PNG
    used_format = IMG_FORMAT
    
    if GIF_ENABLED:
        gif_url = f"{IMG_BASE_URL}/{hex_str}.gif"
        try:
            import urllib.request
            req = urllib.request.Request(gif_url, method="HEAD")
            resp = urllib.request.urlopen(req, timeout=2)
            if resp.status == 200:
                img_url = gif_url
                used_format = "gif"
                logger.bind(tag=TAG).info(f"GIF 可用，使用动画版: {gif_url}")
        except Exception:
            logger.bind(tag=TAG).info(f"GIF 不可用，fallback 到 PNG")
    
    logger.bind(tag=TAG).info(
        f"笔顺查询: {char}"
        + (f"(繁体:{display_char})" if display_char != char else "")
        + f" → U+{hex_str.upper()} → {img_url} [{used_format}]"
    )

    # 5. 通过 MCP 在设备屏幕上显示图片（只发一次，固件定时器 120 秒）
    try:
        if not hasattr(lookup_stroke, "_call_counter"):
            lookup_stroke._call_counter = 0
        lookup_stroke._call_counter += 1

        payload = {
            "jsonrpc": "2.0",
            "id": lookup_stroke._call_counter,
            "method": "tools/call",
            "params": {"name": MCP_ORIGINAL_NAME, "arguments": {"url": img_url}},
        }
        _send_mcp_in_new_loop(conn, payload, timeout=15)
        logger.bind(tag=TAG).info(f"MCP 发送成功: {img_url}")

        # 构造语音回复（保持简短，孩子注意力短）
        # 屏幕已经显示了字本身，TTS 不需要复述上下文（context_phrase 仅用于
        # 让 LLM 做 ASR 自检 + 服务端日志观测，不参与 TTS）。
        intro_text = f"这是{char}字。"

        # 古诗词校验：LLM 给的 poem_line 必须真的包含这个字（防 LLM 跑题/幻觉）
        # 同时字符也要纳入繁简两种形式都允许
        # 还要校验"至少 2 句"（一句的诗朗读出来意境/韵律不完整，对孩子学习效果差）
        poem_text = ""
        if poem_line:
            poem_clean = poem_line.strip().rstrip("。！？.!?")
            # 数中文逗号/分号/句号判断有几个分句（古诗一般用，分隔上下句）
            sep_count = sum(1 for ch in poem_clean if ch in "，,；;")
            char_count = sum(1 for ch in poem_clean if '\u4e00' <= ch <= '\u9fff')

            if char in poem_clean or display_char in poem_clean:
                if sep_count >= 1 and char_count >= 8:
                    # 至少 1 个分隔符（=2 句）+ 至少 8 个汉字 = 算合格
                    poem_text = poem_clean + "。"
                    logger.bind(tag=TAG).info(
                        f"[POEM-OK] character={char}, poem='{poem_clean}' "
                        f"(sep={sep_count}, chars={char_count})"
                    )
                else:
                    logger.bind(tag=TAG).warning(
                        f"[POEM-TOO-SHORT] poem_line='{poem_clean}' 太短 "
                        f"(sep={sep_count}, chars={char_count})，丢弃（要求至少 2 句）"
                    )
            else:
                logger.bind(tag=TAG).warning(
                    f"[POEM-DROPPED] poem_line='{poem_clean}' 不含字'{char}'/'{display_char}'，"
                    f"丢弃（防 LLM 跑题）"
                )
        else:
            logger.bind(tag=TAG).info(f"[POEM-EMPTY] LLM 未给 poem_line（character={char}）")

        # 最终 TTS：intro + 可选的诗句
        tts_text = intro_text + poem_text

        return ActionResponse(
            action=Action.RESPONSE,
            result=f"已发送 {display_char} 的笔顺到屏幕",
            response=tts_text,
        )

    except Exception as e:
        logger.bind(tag=TAG).error(f"MCP 调用失败: {e}", exc_info=True)
        return ActionResponse(
            action=Action.RESPONSE,
            result=f"MCP 调用失败: {e}",
            response=f"哎呀，屏幕显示出了点问题。{char}字你可以问爸爸妈妈帮你写一遍看看！",
        )
