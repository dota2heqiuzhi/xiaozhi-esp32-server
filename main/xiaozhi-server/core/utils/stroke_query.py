"""Recognize explicit single-character stroke questions."""

import re
import unicodedata
from dataclasses import dataclass

# Legacy single-character mapping. Phrase-specific variants are handled below.
_S2T_SIMPLE = "万与专业丛东丝两严丧个丰临为丽举义乐书买乱亏云亚产亲亿仅从仓仪们价众优会伞伟传伤伦体余佣侠侣侥侦侧侨俩俭债倾储儿兑党兰关兴养兽内冈册写军农冲决况冻净减凤凭击凿划刘则刚创删剂剑剧劝办务动励劲劳势勋区医华协卖卢卧卫却厂厅历厉压厌厢厦厨县参双发变叙叠叶号叹听吕吗吨启吴呕员呛呜响哑团围图圆圣场坏块坚坛坝坞坟坠垒垦垫墙壮声壳壶处备复够头夸夹夺奋奖奥妆妇妈娄娇婴孙学宁宝实宠审宪宫宽宾对寻导寿将尔尘尧尽层属岁岂岗岚岛岭峡崭巩币帅师帐帘带帮干并广庄庆庐库应庙庞废开异弃张弥弯弹强归当录彻径忆忧怀态总恋恳恶悬惊惨惩惫惭惮惯愤愿慑懒战户扑扩扫扬扰抚担拟拢拣拥拦拧拨择挂挚挛挞挟挠挡挣挤挥捞损捡换据掷搁搅摄摆摇摈摊撑撵攒敌敛数斋断无旧时旷昙显晋晒晓晕暂术朴杂权条来杨杰松极构枢枪枫柜标栈栋栏树样桥桩梦检棉楼榄橱欢欧歼殁残殴毁毕毙毡气氢汇汉汤汹沟没沥沦沧沪泞泪泻泼泽洁洒浅浆浇浊测济浏浑浓涂涌涛涝涟涡涣涤润涨涩渊渍渐渔渗温湾湿溃满滤滥滨滩漓潇潜澜灏灭灯灵灶灿炉炖点炼烁烂烛烟烦烧烨烫热爱爷牵犹独献环现珐琼瑶电画畅畴疗疟疡疮疯痈痉痒痨痪痫瘪瘫瘾癞癣皑盏盐监盖盗盘着睁瞒矫矶矾矿砖砚砺确硕碍碱礼祷祸禀禅离种积称秆秃稳穷窃窍窑窜窝窥竖竞笃笔笼笺筑筛筝签简篮篱类粜粮糁纟纠红纤约级纪纬纯纱纲纳纵纷纸纹纺纽线练组细织终绍经绑绒结绕绘给络绝绞统绢绣绥继绩绪续绮绰绳维绵绷绸综绽绿缀缄缅缆缉缎编缘缚缝缠缤缩缭缰罂网罗罚罢羁翘耸聂聋职联聪肃肠肤肾肿胀胁胆胧胶脉脏脐脑脓脚脱脸腊腻腾舆舰艰艳艺节芜芦苍苏苹范茎荆荐荚荡荣荤荧药莱莲获莹萝营萧葱蒋蒙蓝蔷蔺藓虏虑虚蚀蚁蛊蛮蛰蜕蜗蝇蝉补衬袄袜袭装裤褴觉觉触誉讠计订认讥讨让训议讯记讲许论讼设访诀证评诈诉诊词译试诗诚话诞诡询该详诧语误诱说请诸读课谁调谅谈谊谋谍谎谐谒谓谕谗谙谚谛谜谢谣谤谦谨谬谭谱谴赵赶趋跃踊踌踪蹑躯车轧轨轩转轮软轰轴轻载较辅辆辈辉辍辐辑输辖辗辙辞辩辫边辽达迁过迈运还进远违连迟适选递逻遗邓邮邻郁郑鉴鉴锁针钉钓钟钢钥钩钻铁铃铅铜铝铭银铸铺链锄锅锈锋锐锢锣锤锥锦锭键锯镀镇镜镰长门闪闭问闯闲闷闸闹闻阀阁阅阎阐阔阳阴阵阶际陆陈陕陨险随隐雏雾霭韦韧韩页顶项顺须顽顾顿颁预领颇频颖颗题颜额颠风飘飞饣饥饭饮饰饱饲饵饶饺饼馆馈馋马驭驮驰驱驳驴驶驹驻驼驾骂骄骆骇骑验骗骤髅鱼鲁鲜鲤鲸鸟鸡鸣鸭鸽鹅鹊鹤鹰麦黄齐齿龙龟"
_S2T_TRAD = "萬與專業叢東絲兩嚴喪個豐臨為麗舉義樂書買亂虧雲亞產親億僅從倉儀們價眾優會傘偉傳傷倫體餘傭俠侶僥偵側僑倆儉債傾儲兒兌黨蘭關興養獸內岡冊寫軍農衝決況凍淨減鳳憑擊鑿劃劉則剛創刪劑劍劇勸辦務動勵勁勞勢勳區醫華協賣盧臥衛卻廠廳歷厲壓厭廂廈廚縣參雙發變敘疊葉號嘆聽呂嗎噸啟吳嘔員嗆嗚響啞團圍圖圓聖場壞塊堅壇壩塢墳墜壘墾墊牆壯聲殼壺處備複夠頭誇夾奪奮獎奧妝婦媽婁嬌嬰孫學寧寶實寵審憲宮寬賓對尋導壽將爾塵堯盡層屬歲豈崗嵐島嶺峽嶄鞏幣帥師帳簾帶幫幹並廣莊慶廬庫應廟龐廢開異棄張彌彎彈強歸當錄徹徑憶憂懷態總戀懇惡懸驚慘懲憊慚憚慣憤願懾懶戰戶撲擴掃揚擾撫擔擬攏揀擁攔擰撥擇掛摯攣撻挾撓擋掙擠揮撈損撿換據擲擱攪攝擺搖擯攤撐攆攢敵斂數齋斷無舊時曠曇顯晉曬曉暈暫術樸雜權條來楊傑鬆極構樞槍楓櫃標棧棟欄樹樣橋樁夢檢棉樓欖櫥歡歐殲歿殘毆毀畢斃氈氣氫匯漢湯洶溝沒瀝淪滄滬濘淚瀉潑澤潔灑淺漿澆濁測濟瀏渾濃塗湧濤澇漣渦渙滌潤漲澀淵漬漸漁滲溫灣濕潰滿濾濫濱灘漓瀟潛瀾灝滅燈靈竈燦爐燉點煉爍爛燭煙煩燒燁燙熱愛爺牽猶獨獻環現琺瓊瑤電畫暢疇療瘧瘍瘡瘋癰痙癢癆瘓癇癟癱癮癩癬皚盞鹽監蓋盜盤著睜瞞矯磯礬礦磚硯礪確碩礙鹼禮禱禍稟禪離種積稱稈禿穩窮竊竅窯竄窩窺豎競篤筆籠箋築篩箏簽簡籃籬類糶糧糝糸糾紅纖約級紀緯純紗綱納縱紛紙紋紡紐線練組細織終紹經綁絨結繞繪給絡絕絞統絹繡綏繼績緒續綺綽繩維綿繃綢綜綻綠綴緘緬纜緝緞編緣縛縫纏繽縮繚韁罌網羅罰罷羈翹聳聶聾職聯聰肅腸膚腎腫脹脅膽朧膠脈臟臍腦膿腳脫臉臘膩騰輿艦艱艷藝節蕪蘆蒼蘇蘋範莖荊薦莢蕩榮葷熒藥萊蓮獲瑩蘿營蕭蔥蔣矇藍薔藺蘚虜慮虛蝕蟻蠱蠻蟄蛻蝸蠅蟬補襯襖襪襲裝褲襤覺覺觸譽訁計訂認譏討讓訓議訊記講許論訟設訪訣證評詐訴診詞譯試詩誠話誕詭詢該詳詫語誤誘說請諸讀課誰調諒談誼謀諜謊諧謁謂諭讒諳諺諦謎謝謠謗謙謹謬譚譜譴趙趕趨躍踴躊蹤躡軀車軋軌軒轉輪軟轟軸輕載較輔輛輩輝輟輻輯輸轄輾轍辭辯辮邊遼達遷過邁運還進遠違連遲適選遞邏遺鄧郵鄰鬱鄭鑒鑑鎖針釘釣鐘鋼鑰鉤鑽鐵鈴鉛銅鋁銘銀鑄鋪鏈鋤鍋鏽鋒銳錮鑼錘錐錦錠鍵鋸鍍鎮鏡鐮長門閃閉問闖閒悶閘鬧聞閥閣閱閻闡闊陽陰陣階際陸陳陝隕險隨隱雛霧靄韋韌韓頁頂項順須頑顧頓頒預領頗頻穎顆題顏額顛風飄飛飠飢飯飲飾飽飼餌饒餃餅館饋饞馬馭馱馳驅駁驢駛駒駐駝駕罵驕駱駭騎驗騙驟髏魚魯鮮鯉鯨鳥雞鳴鴨鴿鵝鵲鶴鷹麥黃齊齒龍龜"

_SIMP_TO_TRAD = dict(zip(_S2T_SIMPLE, _S2T_TRAD))
_SIMP_TO_TRAD.update({
    "乌": "烏", "国": "國", "猫": "貓", "观": "觀", "见": "見",
    "乡": "鄉", "争": "爭", "尝": "嘗", "尴": "尷", "队": "隊", "难": "難",
    "园": "園", "习": "習", "这": "這", "货": "貨", "珑": "瓏",
})

# Each entry lists conventional spellings and phrases that identify one spelling.
_TRADITIONAL_VARIANTS = {
    "发": {"發": ("出发", "发现", "发烧", "发票", "发芽", "发生"),
           "髮": ("头发", "理发", "白发", "短发", "长发", "发型")},
    "后": {"後": ("以后", "后来", "后面", "前后", "最后", "后天"),
           "后": ("皇后", "王后", "太后", "天后")},
    "干": {"乾": ("干净", "干旱", "干燥", "饼干"),
           "幹": ("干活", "干部", "干什么", "能干", "树干"),
           "干": ("干涉", "干扰", "干支", "不相干")},
    "台": {"臺": ("台湾", "舞台", "阳台", "台阶"),
           "颱": ("台风",), "檯": ("台灯", "台面", "台球")},
    "面": {"面": ("面孔", "面对", "见面", "后面", "前面", "表面"),
           "麵": ("面条", "面包", "面粉", "拉面", "汤面", "牛肉面")},
    "只": {"只": ("只有", "只是", "只要", "只好"),
           "隻": ("一只", "两只", "三只", "船只")},
    "松": {"松": ("松树", "松果", "松鼠", "松林"),
           "鬆": ("放松", "轻松", "松开", "松软")},
    "获": {"獲": ("不劳而获", "而获", "获得", "获奖", "获胜", "捕获", "获救", "获益"),
           "穫": ("收获",)},
}

_TRAD_TO_SIMP = {traditional: simplified for simplified, traditional in _SIMP_TO_TRAD.items()}
for _simplified, _variants in _TRADITIONAL_VARIANTS.items():
    _TRAD_TO_SIMP.update(dict.fromkeys(_variants, _simplified))
_SIMP_TRANSLATION = str.maketrans(_TRAD_TO_SIMP)

_HAN = r"[\u3007\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af]"
_SINGLE_HAN = re.compile(_HAN)
_TARGET = rf"(?:(?P<context>{_HAN}{{1,16}}?)(?:[的嘅][,、]?(?:[那这這嗰呢][个個])?|[个個]))?(?P<character>{_HAN})"
_SCRIPT = r"(?P<script>(?:繁|正|简|簡)[体體])"
_QUESTION = r"(?:(?:要|[应應][该該])?(?:怎[么麼麽][写寫]|如何[写寫]|[点點](?:[样樣])?[写寫]))"
_TAIL = r"[吗嗎呢呀啊㗎吖咩]?"
_LEAD = (
    r"(?:(?:小智|你好)[,、]?)?"
    r"(?:(?:[请請][问問]?(?:一下)?|我想(?:知道|[请請]?[问問])|你知道|你能[告吿][诉訴]我)[,、]?)?"
)
_QUERY_PATTERNS = tuple(re.compile(pattern) for pattern in (
    rf"{_LEAD}(?P<ordinal_context>{_HAN}{{2,16}}?)[的嘅]?(?P<position>第[一二三四五六七八九1-9]|最[后後]一)[个個]?字(?:[的嘅用]?{_SCRIPT}字?)?{_QUESTION}{_TAIL}",
    rf"{_LEAD}{_SCRIPT}字?的?{_TARGET}字?[,]?{_QUESTION}{_TAIL}",
    rf"{_LEAD}{_TARGET}字?(?:(?:的|嘅|用)?{_SCRIPT}字?)?[,]?{_QUESTION}{_TAIL}",
    rf"{_LEAD}{_TARGET}字?(?:的|嘅)?{_SCRIPT}字{_TAIL}",
    rf"{_LEAD}{_TARGET}字?(?:的|嘅)?[写寫]法{_TAIL}",
    rf"{_LEAD}{_TARGET}字?(?:的|嘅)?[笔筆](?:[顺順]|[画畫][顺順]序)(?:是什[么麼麽]|[怎點点][么麼麽]?[写寫])?{_TAIL}",
    rf"{_LEAD}教我[写寫](?:[一这這那][个個])?{_TARGET}字?{_TAIL}",
    rf"{_LEAD}(?:[写寫](?:一[个個])?|(?:[帮幫给給]我)?(?:想)?(?:看看?|睇[睇吓下]?)){_TARGET}字{_TAIL}",
))

# Recorded ASR confusions supplement the tone-sensitive pronunciation dictionary.
_ASR_GROUPS = ("努弩怒", "龙笼隆", "友有", "龟归规", "获惑货或祸霍")
_QUOTES = str.maketrans("", "", "\"'“”‘’「」『』")
_BU_LAO_ER_HUO = re.compile(
    r"不[劳勞老牢][而尔爾](?:[,.。]而?)?([获獲穫惑货貨或祸禍霍])(?:\1(?=[的嘅]))?"
)

_UNSPECIFIED_CONTEXTS = frozenset({
    "词语", "句子", "句话", "成语", "名字", "课文", "生字", "这个词", "那个词", "这句话",
    "那句话", "这个成语", "那个成语", "这个句子", "那个句子", "这个名字", "那个名字",
})
_REFERENTIAL_CONTEXT = re.compile(
    r"^(?:刚才|刚刚|方才|上次|上一[个句段篇]|前面|之前|头先|頭先|"
    r"[我你您他她它咱](?:们)?(?:说|讲|念|读|写|提|[的嘅]|名字|刚才|刚刚)|"
    r"[这那哪呢嗰](?:[一二三四五两几]?[个件]|[句段篇本首张幅]))|"
    r"[的嘅](?:词语|成语|句子|名字|文章|课文|生字)$"
)
_SCHOOL_WORDS = (
    "課室", "課本", "練習簿", "圖書館", "書包", "操場", "小息", "文具盒", "默書",
    "努力", "恐龍", "燈籠", "試卷", "叔叔", "他們", "她們", "中文科", "功課",
)
_CANONICAL_SCHOOL_WORDS = frozenset(word.translate(_SIMP_TRANSLATION) for word in _SCHOOL_WORDS)
_CLARIFICATION_EXAMPLES = {
    "室": ("課室", "試卷"), "试": ("試卷", "課室"),
    "市": ("市場", "課室"),
    "书": ("圖書館", "叔叔"), "叔": ("叔叔", "圖書館"),
    "龙": ("恐龍", "玲瓏", "龍門", "燈籠"), "笼": ("燈籠", "恐龍"),
    "珑": ("玲瓏", "龍門"),
    "他": ("他們", "她們"), "她": ("她們", "他們"),
    "努": ("努力", "憤怒"), "怒": ("憤怒", "努力"),
    "货": ("貨物", "獲獎"), "祸": ("闖禍", "獲獎"),
}
_FOLLOW_UP_PREFIXES = ("我说的是", "我想查", "就是说", "就是", "说的是", "是", "係")
_FOLLOW_UP_SUFFIXES = (
    "里面的", "裏面的", "裡面的", "里的", "裏的", "裡的", "的那个字", "嘅嗰个字",
    "那个字", "嗰个字", "呢个字", "那个", "嗰个", "呢个", "的", "嘅",
)
_FOLLOW_UP_PARTICLES = "啊呀呢啦喇喎囉啰㗎吖嘛啫"
_SHORT_WORD = re.compile(rf"{_HAN}{{2,8}}")
_TARGETLESS_QUESTION = re.compile(rf"{_LEAD}字{_QUESTION}{_TAIL}")
_FOLLOW_UP_TARGET = re.compile(
    rf"(?P<context>{_HAN}{{2,16}}?)[的嘅](?:[那这這嗰呢][个個])?(?P<character>{_HAN})字?"
)
GENERIC_CLARIFICATION = "你想问哪个词里的字？说词就可以，比如課室。"


@dataclass(frozen=True)
class StrokeClarification:
    character: str
    script: str
    examples: tuple[str, ...]

    @property
    def prompt(self) -> str:
        if not self.character:
            return "想查哪个字？可以说圖書館的館字怎么写，或者说词里的第几个字。"
        if self.examples:
            return f"你说的是{'，还是'.join(self.examples[:2])}？说词就可以。"
        return GENERIC_CLARIFICATION


def is_han_character(value: str) -> bool:
    return bool(_SINGLE_HAN.fullmatch(value))


def to_simplified(value: str) -> str:
    return value.translate(_SIMP_TRANSLATION)


def display_character(character: str, context_phrase: str, script: str) -> str | None:
    """Return the requested spelling, or None if the usual variants need a hint."""
    if script == "simplified":
        return to_simplified(character)

    variants = _TRADITIONAL_VARIANTS.get(character)
    if variants:
        context = to_simplified(context_phrase)
        matches = [
            variant for variant, phrases in variants.items()
            if any(phrase in context for phrase in phrases)
        ]
        return matches[0] if len(matches) == 1 else None
    return _SIMP_TO_TRAD.get(character, character)


def variant_examples(character: str) -> tuple[str, ...]:
    return tuple(
        "".join(variant if char == character else _SIMP_TO_TRAD.get(char, char) for char in phrases[0])
        for variant, phrases in _TRADITIONAL_VARIANTS.get(character, {}).items()
    )


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    return "".join(normalized.split()).strip(".!?。！？")


def _stroke_request(text: str, *, spoken: bool) -> re.Match | None:
    if not isinstance(text, str) or len(text) > 100:
        return None
    normalized = _normalize(text)
    if spoken:
        normalized = _BU_LAO_ER_HUO.sub(_restore_idiom, normalized)
    for pattern in _QUERY_PATTERNS:
        match = pattern.fullmatch(normalized)
        if match:
            return match
    return None


def looks_like_stroke_query(text: str, *, spoken: bool = False) -> bool:
    """Recognize the query structure even when its target needs clarification."""
    return _stroke_request(text, spoken=spoken) is not None


def _requested_script(groups: dict) -> str:
    return "simplified" if (groups.get("script") or "").startswith(("简", "簡")) else "traditional"


def get_stroke_clarification(text: str, *, spoken: bool = False) -> StrokeClarification | None:
    match = _stroke_request(text, spoken=spoken)
    if not match:
        return None
    groups = match.groupdict()
    script = _requested_script(groups)
    if "position" in groups or (spoken and _TARGETLESS_QUESTION.fullmatch(_normalize(text))):
        return StrokeClarification("", script, ())
    character = groups["character"]
    simplified = to_simplified(character)
    examples = _CLARIFICATION_EXAMPLES.get(simplified) or variant_examples(simplified)
    return StrokeClarification(character, script, examples)


def _restore_idiom(match: re.Match) -> str:
    phrase = match.group()
    return phrase if phrase in {"不劳而获", "不勞而獲"} else "不劳而获"


def _pronunciation_candidates(character: str, context: str) -> tuple[set[str], set[str]]:
    try:
        # Load the dictionaries only when checking a potentially ambiguous reading.
        from pypinyin import Style, pinyin
    except ImportError:
        return set(), set()

    def pronunciations(text: str) -> list[list[str]]:
        return pinyin(
            to_simplified(text), style=Style.TONE3, heteronym=True,
            neutral_tone_with_five=True, errors=list,
        )

    target_readings = set(pronunciations(character)[0])
    target_syllables = {reading.rstrip("12345") for reading in target_readings}
    exact_matches, syllable_matches = set(), set()
    for char, readings in zip(context, pronunciations(context)):
        if target_readings.intersection(readings):
            exact_matches.add(char)
        elif any(reading.rstrip("12345") in target_syllables for reading in readings):
            syllable_matches.add(char)
    return exact_matches, syllable_matches


def _known_homophones(character: str) -> str:
    return next((group for group in _ASR_GROUPS if character in group), "")


def _resolve_context_character(character: str, context: str, spoken: bool) -> str | None:
    if character in context and not spoken:
        return character

    simplified = to_simplified(character)
    equivalent = {char for char in context if to_simplified(char) == simplified}
    if equivalent and not spoken:
        return next(iter(equivalent)) if len(equivalent) == 1 else None

    group = _known_homophones(simplified)
    candidates = equivalent | {char for char in context if to_simplified(char) in group}
    exact_matches, syllable_matches = _pronunciation_candidates(character, context)
    candidates.update(exact_matches)
    if not candidates and to_simplified(context) in _CANONICAL_SCHOOL_WORDS:
        candidates = syllable_matches
    return next(iter(candidates)) if len(candidates) == 1 else None


def parse_stroke_query(text: str, *, spoken: bool = False) -> dict[str, str] | None:
    """Resolve a single-character request, requiring unique evidence for speech."""
    match = _stroke_request(text, spoken=spoken)
    if not match:
        return None

    groups = match.groupdict()
    script = _requested_script(groups)
    if position := groups.get("position"):
        context = groups["ordinal_context"]
        simplified_context = to_simplified(context)
        if simplified_context in _UNSPECIFIED_CONTEXTS or _REFERENTIAL_CONTEXT.search(simplified_context):
            return None
        if position.startswith("最"):
            character = context[-1]
        else:
            index = int(position[1]) - 1 if position[1].isdigit() else "一二三四五六七八九".index(position[1])
            if index >= len(context):
                return None
            character = context[index]
        return _resolved_args(character, context, script)

    character = groups["character"]
    context = groups["context"] or ""
    if context:
        character = _resolve_context_character(character, context, spoken)
        return _resolved_args(character, context, script)

    return {"character": character, "context_phrase": context, "script": script}


def _follow_up_target(text: str) -> tuple[str, str] | None:
    match = _FOLLOW_UP_TARGET.fullmatch(text)
    if match is None:
        return None
    context, target = match.group("context", "character")
    word = to_simplified(context)
    if _REFERENTIAL_CONTEXT.search(word) or to_simplified(target) not in word:
        return None
    return context, target


def parse_stroke_follow_up(text: str, clarification: StrokeClarification) -> dict[str, str] | None:
    """Resolve a short word answer to the question asked in the previous turn."""
    if not isinstance(text, str) or len(text) > 20:
        return None
    word = _normalize(text).rstrip(_FOLLOW_UP_PARTICLES)
    if target_hint := _follow_up_target(word):
        context, target = target_hint
        if clarification.character:
            if _resolve_context_character(clarification.character, target, spoken=True):
                return _resolved_args(target, context, clarification.script)
        elif to_simplified(context) in _CANONICAL_SCHOOL_WORDS:
            return _resolved_args(target, context, clarification.script)
        return None
    if not clarification.character:
        return None
    explicit = False
    for prefix in _FOLLOW_UP_PREFIXES:
        if to_simplified(word).startswith(prefix):
            word = word[len(prefix):].lstrip(",、")
            explicit = True
            break
    for suffix in _FOLLOW_UP_SUFFIXES:
        if to_simplified(word).endswith(suffix):
            word = word[:-len(suffix)]
            explicit = True
            break
    if not _SHORT_WORD.fullmatch(word):
        return None
    if not explicit:
        canonical = to_simplified(clarification.character)
        known_words = {to_simplified(known) for known in clarification.examples}
        known_words.update(_CANONICAL_SCHOOL_WORDS)
        for character in _known_homophones(canonical) or canonical:
            known_words.update(
                phrase for phrases in _TRADITIONAL_VARIANTS.get(character, {}).values()
                for phrase in phrases
            )
        if to_simplified(word) not in known_words:
            return None
    character = _resolve_context_character(clarification.character, word, spoken=True)
    return _resolved_args(character, word, clarification.script)


def get_stroke_follow_up_clarification(
    text: str, previous: StrokeClarification,
) -> StrokeClarification | None:
    """Ask about the specific sound when a just-requested spelling hint came back incomplete."""
    if previous.character or len(text) > 20:
        return None
    target_hint = _follow_up_target(_normalize(text).rstrip(_FOLLOW_UP_PARTICLES))
    if target_hint is None:
        return None
    context, target = target_hint
    word = to_simplified(context)
    target = to_simplified(target)
    examples = _CLARIFICATION_EXAMPLES.get(target) or variant_examples(target)
    ordered_examples = sorted(
        examples, key=lambda example: (to_simplified(example) != word, target in to_simplified(example))
    )
    return StrokeClarification(target, previous.script, tuple(ordered_examples))


def _resolved_args(character: str | None, context: str, script: str) -> dict[str, str] | None:
    if character is None or display_character(character, context, script) is None:
        return None
    return {"character": character, "context_phrase": context, "script": script}
