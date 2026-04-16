"""PharmaPulse 配置文件"""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── API Keys ──────────────────────────────────────────────
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# ── RSS 来源（国际） ──────────────────────────────────────
RSS_FEEDS = [
    {
        "name": "FDA Press Releases",
        "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
        "source": "FDA",
    },
    {
        "name": "STAT News",
        "url": "https://www.statnews.com/feed/",
        "source": "STAT News",
    },
    {
        "name": "BioPharma Dive",
        "url": "https://www.biopharmadive.com/feeds/news/",
        "source": "BioPharma Dive",
    },
    {
        "name": "FiercePharma",
        "url": "https://www.fiercepharma.com/rss/xml",
        "source": "FiercePharma",
    },
    {
        "name": "Reuters Health",
        "url": "https://feeds.reuters.com/reuters/healthNews",
        "source": "Reuters",
    },
]

# ── 国内数据源（百度资讯搜索 + 36kr RSS + 新浪滚动 API） ──
# 部署在国内云服务器时无法访问 Google/Bing RSS，使用国内可靠的数据源

# 百度资讯搜索关键词（最稳定的国内新闻数据源）
CN_BAIDU_NEWS_QUERIES = [
    {
        "name": "百度-创新药与临床试验",
        "query": "创新药 临床试验 审批",
        "max_items": 20,
    },
    {
        "name": "百度-医药行业动态",
        "query": "医药行业 药企 新闻",
        "max_items": 20,
    },
    {
        "name": "百度-药监局新药上市",
        "query": "药监局 新药 上市",
        "max_items": 20,
    },
    {
        "name": "百度-生物医药投融资",
        "query": "生物医药 融资 并购",
        "max_items": 20,
    },
    {
        "name": "百度-集采与医保",
        "query": "集采 医保 药品",
        "max_items": 20,
    },
]

# 36kr RSS（科技/医疗交叉领域，RSS 可用）
CN_36KR_RSS = {
    "name": "36氪",
    "url": "https://36kr.com/feed",
    "source": "36氪",
    "max_items": 30,
}

# 新浪财经滚动新闻 API（JSON接口，稳定可用）
CN_SINA_ROLL_API = {
    "name": "新浪财经滚动",
    "url": "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=50&page={page}",
    "source": "新浪财经",
    "pages": 3,  # 抓取3页
}

# ── 关键词过滤 ────────────────────────────────────────────
# 必须包含其中之一（OR 关系），不区分大小写
INCLUDE_KEYWORDS = [
    # 英文关键词
    "pharma", "pharmaceutical", "drug", "fda", "ema", "nmpa",
    "biotech", "vaccine", "clinical trial", "drug approval",
    "drug recall", "pipeline", "oncology", "biologic",
    "therapy", "therapeutic", "medication", "prescription",
    "biotechnology", "biosimilar", "generic drug",
    # 中文关键词
    "药品", "药物", "医药", "制药", "生物医药", "创新药", "仿制药",
    "临床试验", "临床研究", "药监局", "药审中心", "审批", "获批", "批准",
    "新药", "上市许可", "药企", "生物制品", "疫苗", "抗体",
    "基因治疗", "细胞治疗", "靶向药", "免疫治疗", "肿瘤",
    "集采", "带量采购", "医保", "药价", "一致性评价",
    "CDE", "NMPA", "注册审评", "MAH", "IND", "NDA", "ANDA",
    "融资", "并购", "上市", "ipo", "管线", "适应症",
]

# 排除词（命中则过滤掉）
EXCLUDE_KEYWORDS = [
    "recreational drug", "drug abuse", "street drug", "illegal drug",
    "毒品", "吸毒",
]

# ── 分类规则（关键词触发）────────────────────────────────
CATEGORY_RULES = {
    "regulatory": [
        # 英文
        "fda", "ema", "regulatory", "approval", "approve", "approved",
        "recall", "ban", "nmpa", "clearance", "authorize",
        "warning letter", "compliance",
        # 中文
        "监管", "审批", "获批", "上市许可", "药监局", "药审中心",
        "注册审评", "药品注册", "受理", "批准", "上市申请",
        "国家药监局", "注销", "撤市", "召回",
        "药品说明书", "补充申请", "变更", "一致性评价",
        "集采", "带量采购", "医保目录", "谈判",
    ],
    "clinical": [
        # 英文
        "phase 1", "phase 2", "phase 3", "phase i", "phase ii", "phase iii",
        "clinical trial", "efficacy", "safety data", "placebo", "endpoint",
        "randomized", "double-blind", "pivotal trial", "primary endpoint",
        # 中文
        "临床试验", "临床研究", "一期临床", "二期临床", "三期临床",
        "主要终点", "次要终点", "随机对照", "双盲",
        "有效性", "安全性", "适应症", "入组", "受试者", "临床数据",
        "关键性临床", "突破性疗法", "ind", "nda",
    ],
    "corporate": [
        # 英文
        "acquisition", "merger", "partnership", "ipo", "ceo", "earnings",
        "layoff", "restructuring", "deal", "collaboration", "joint venture",
        "revenue report", "quarterly",
        # 中文
        "收购", "并购", "合作", "融资", "裁员", "重组",
        "战略合作", "授权引进", "license-in", "license-out",
        "营收", "财报", "季报", "年报", "管理层",
        "港股", "a股", "科创板", "上市",
    ],
    "market": [
        # 英文
        "launch", "patent", "generic", "revenue", "market share", "pricing",
        "commercial", "sales", "blockbuster", "patent expiry", "biosimilar launch",
        # 中文
        "上市销售", "市场", "专利", "仿制药", "生物类似药",
        "销售额", "放量", "进院", "商业化", "定价",
        "医药市场", "竞争格局", "市场份额",
    ],
}

# ── 重要度评分关键词 ──────────────────────────────────────
IMPORTANCE_RULES = {
    "high": [
        # 英文
        "fda approves", "fda approved", "fda approval", "ema approves",
        "fda rejects", "fda rejected", "complete response letter",
        "phase 3 results", "phase iii results", "pivotal data",
        "billion acquisition", "billion deal", "billion merger",
        "breakthrough therapy",
        # 中文
        "获批上市", "批准上市", "附条件批准", "优先审评",
        "三期临床结果", "关键性临床", "突破性疗法",
        "重大并购", "国家集采", "医保谈判结果",
        "首款", "首个", "全球首创", "全球首个",
    ],
    "medium": [
        # 英文
        "phase 2 results", "phase ii results", "quarterly earnings",
        "collaboration agreement", "partnership", "licensing deal",
        "priority review", "fast track",
        # 中文
        "二期临床结果", "授权合作", "战略合作",
        "融资", "ipo", "科创板", "港股上市",
        "纳入医保", "集采中标", "优先审评",
    ],
    # 其余默认为 low
}

# ── AI 摘要 Prompt 模板（DeepSeek）────────────────────────
SUMMARY_PROMPT = """你是一位专业的医药行业新闻编辑。请为以下新闻生成**简洁准确的中文摘要**。

要求：
1. 摘要长度：2-4 句话，不超过 150 字
2. 保留关键信息：药物名称、公司名称、数据指标、监管决定等
3. 语言风格：专业、客观、简洁
4. 如果原文已是中文，直接提炼摘要即可；如果是英文，翻译并提炼
5. 药物和公司的专有名词保留英文原名，括号内给出中文

新闻标题：{title}
新闻内容：{content}

中文摘要："""

# ── 输出路径 ──────────────────────────────────────────────
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
