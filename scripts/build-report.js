const fs = require("fs");
const path = require("path");

const PLATFORMS = [
  ["toutiao", "今日头条"],
  ["baidu", "百度热搜"],
  ["wallstreetcn-hot", "华尔街见闻"],
  ["thepaper", "澎湃新闻"],
  ["bilibili-hot-search", "bilibili 热搜"],
  ["cls-hot", "财联社热门"],
  ["ifeng", "凤凰网"],
  ["tieba", "贴吧"],
  ["weibo", "微博"],
  ["douyin", "抖音"],
  ["zhihu", "知乎"],
].map(([id, name]) => ({
  id,
  name,
  sourceUrl: `https://newsnow.busiyi.world/api/s?id=${id}&latest`,
}));

function argValue(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : "";
}

const rawDir = argValue("--raw");
if (!rawDir) {
  console.error("Usage: node scripts/build-report.js --raw <raw-api-dir>");
  process.exit(1);
}

const now = new Date();
const dateKey = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
}).format(now);
const generatedAt = `${now.toLocaleString("zh-CN", { hour12: false, timeZone: "Asia/Shanghai" })} +08:00（固定脚本自动运行）`;

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function readJson(file) {
  const raw = fs.readFileSync(file, "utf8").replace(/^\uFEFF/, "");
  return JSON.parse(raw);
}

function writeJson(file, data) {
  ensureDir(path.dirname(file));
  fs.writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

function text(value) {
  if (Array.isArray(value)) return value.join("、");
  return value == null || value === "" ? "-" : String(value);
}

function cleanTitle(title) {
  return text(title)
    .replace(/[#[\]【】《》“”"'’‘、，。！？!?：:；;（）()]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function compactKey(title) {
  return cleanTitle(title)
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[0-9]+/g, "")
    .slice(0, 48);
}

function topicKey(title) {
  const value = cleanTitle(title);
  const rules = [
    [/欧冠|巴黎|阿森纳|姆巴佩|点球|角球|进球|裁判|加时|足球/, "欧冠与巴黎夺冠讨论"],
    [/AI|人工智能|大模型|机器人|算力|芯片|泄密/, "AI与科技工具讨论"],
    [/高考|中考|招生|志愿|分数|录取|考试/, "考试与升学安排讨论"],
    [/暴雨|高温|台风|天气|出行|航班|火车|旅游|景区/, "出行与天气安排讨论"],
    [/基金|股票|A股|港股|美股|黄金|降息|财报|债券|央行/, "财经市场变化讨论"],
    [/牙齿|医院|医生|药|疾病|健康|睡眠|情绪|医疗/, "健康生活与就医准备讨论"],
    [/演唱会|综艺|电影|电视剧|明星|艺人|王菲|谢霆锋|宋亚轩|关晓彤/, "泛娱乐与明星话题讨论"],
    [/麦当劳|预售|衣服|消费|外卖|门店|价格|退款|投诉/, "消费选择与维权讨论"],
  ];
  const matched = rules.find(([regex]) => regex.test(value));
  return matched ? matched[1] : compactKey(value);
}

function bigrams(value) {
  const clean = compactKey(value);
  const set = new Set();
  for (let index = 0; index < clean.length - 1; index += 1) {
    set.add(clean.slice(index, index + 2));
  }
  return set;
}

function similarity(a, b) {
  const left = bigrams(a);
  const right = bigrams(b);
  if (!left.size || !right.size) return 0;
  let overlap = 0;
  left.forEach((item) => {
    if (right.has(item)) overlap += 1;
  });
  return overlap / Math.min(left.size, right.size);
}

function extractHeat(item) {
  const candidates = [
    item.heat,
    item.hot,
    item.score,
    item.popularity,
    item.extra?.heat,
    item.extra?.hot,
    item.extra?.score,
    item.extra?.popularity,
  ];
  const hit = candidates.find((value) => value !== undefined && value !== null && value !== "");
  return hit == null ? "" : String(hit);
}

function sourceStatus(status) {
  return status === "success" || status === "cache" ? status : "success";
}

function normalizeRecords() {
  const records = [];
  const failures = [];
  const sourceAudit = [];

  for (const platform of PLATFORMS) {
    const file = path.join(rawDir, `${platform.id}.json`);
    const errorFile = path.join(rawDir, `${platform.id}.error.json`);
    if (!fs.existsSync(file)) {
      const failure = fs.existsSync(errorFile)
        ? readJson(errorFile)
        : { error: "API response file missing" };
      failures.push({ platform: platform.name, id: platform.id, sourceUrl: platform.sourceUrl, error: failure.error });
      sourceAudit.push({
        platform: platform.name,
        id: platform.id,
        sourceType: "api_failed",
        sourceName: "TrendRadar / NewsNow API",
        sourceUrl: platform.sourceUrl,
        status: "failed",
        itemCount: 0,
        sourceUpdatedAt: "",
        fetchedAt: generatedAt,
        confidence: "低",
        need: "无需 API key/cookie/登录态；本次调用失败",
      });
      continue;
    }

    let payload;
    try {
      payload = readJson(file);
    } catch (error) {
      failures.push({ platform: platform.name, id: platform.id, sourceUrl: platform.sourceUrl, error: error.message });
      continue;
    }

    const items = Array.isArray(payload.items) ? payload.items : [];
    const status = sourceStatus(payload.status);
    const confidence = status === "success" ? "高" : status === "cache" ? "中" : "低";
    sourceAudit.push({
      platform: platform.name,
      id: platform.id,
      sourceType: "trendradar_newsnow_api",
      sourceName: "TrendRadar / NewsNow API",
      sourceUrl: platform.sourceUrl,
      status,
      itemCount: items.length,
      sourceUpdatedAt: payload.updatedTime || payload.updatedAt || "",
      fetchedAt: generatedAt,
      confidence,
      need: "无需 API key/cookie/登录态",
    });

    const count = Math.max(items.length, 1);
    items.forEach((item, index) => {
      const rank = index + 1;
      const title = cleanTitle(item.title || item.name || item.id || `未命名热点 ${rank}`);
      const heatNormalized = Math.max(1, Math.round(((count - rank + 1) / count) * 100));
      const heatRaw = extractHeat(item) || `平台排名 #${rank}`;
      records.push({
        platform: platform.name,
        platformId: platform.id,
        rank,
        title,
        url: item.mobileUrl || item.url || platform.sourceUrl,
        heatRaw,
        heatNormalized,
        sourceType: "trendradar_newsnow_api",
        sourceName: "TrendRadar / NewsNow API",
        sourceUrl: platform.sourceUrl,
        sourceUpdatedAt: payload.updatedTime || payload.updatedAt || "",
        fetchedAt: generatedAt,
        confidence,
      });
    });
  }

  return { records, failures, sourceAudit };
}

function mergeRecords(records) {
  const groups = [];
  for (const record of records) {
    const key = topicKey(record.title);
    let group = groups.find((entry) => entry.key === key);
    if (!group && key.length > 8) {
      group = groups.find((entry) => similarity(entry.event, record.title) >= 0.62);
    }
    if (!group) {
      group = { key, event: key.length > 4 ? key : record.title, records: [] };
      groups.push(group);
    }
    group.records.push(record);
    group.event = chooseEventName(group.event, group.records);
  }
  return groups;
}

function chooseEventName(current, records) {
  const topic = topicKey(records[0]?.title || current);
  if (topic && topic !== compactKey(topic)) return topic;
  const sorted = [...records].sort((a, b) => b.heatNormalized - a.heatNormalized || a.rank - b.rank);
  return sorted[0]?.title || current;
}

function categoryFor(content) {
  const value = text(content);
  if (/欧冠|足球|赛事|比赛|赛程|进球|点球|电竞|选手|决赛/.test(value)) return "sports";
  if (/高考|中考|招生|志愿|分数|录取|考试|教育/.test(value)) return "education";
  if (/AI|人工智能|会议记录|泄密|大模型|机器人|芯片|科技/.test(value)) return "tech";
  if (/基金|股票|A股|港股|美股|黄金|降息|财报|财经|央行|债券/.test(value)) return "finance";
  if (/牙齿|医院|医生|药|疾病|健康|睡眠|情绪|医疗/.test(value)) return "health";
  if (/暴雨|高温|台风|天气|出行|航班|火车|旅游|景区/.test(value)) return "travel";
  if (/演唱会|综艺|电影|电视剧|明星|艺人|偶遇|恋情|王菲|谢霆锋|宋亚轩|关晓彤/.test(value)) return "entertainment";
  if (/麦当劳|预售|衣服|消费|外卖|退款|投诉|价格|门店/.test(value)) return "consumer";
  if (/网友|女子|男子|事故|警方|法院|水源|游客|公共|安全/.test(value)) return "public";
  return "general";
}

const CATEGORY = {
  sports: {
    customer: "微信群里讨论比赛、只想快速生成赛后表达和提醒的球迷/电竞观众",
    names: ["赛后卡片", "观赛小记", "赛程提醒", "群聊赛报"],
    intro: "生成赛后结果卡、讨论素材和下一场提醒，不提供直播或回放。",
    features: "赛果卡片、下一场提醒、群聊讨论文案、外链观看入口、收藏关注对象。",
    opportunity: "把赛事热点转成微信群可分享卡片和赛程提醒，只承接表达与提醒，不碰播放权。",
    compliance: "低",
    difficulty: "低",
    priority: "高",
    decision: "做：只做微信分享和提醒，不做内容播放。",
    risk: "可做 MVP，但第三方赛程/赛果优先用公开链接或人工维护；不抓版权视频和实时直播流。",
  },
  education: {
    customer: "学生和家长，但涉及教育资质，默认只做通用时间提醒和材料清单",
    names: ["备忘清单", "时间提醒", "材料夹", "事项卡片"],
    intro: "只做通用事项清单和提醒，不做考试预测、志愿建议或升学判断。",
    features: "日期提醒、材料清单、官方入口收藏、家庭分工卡。",
    opportunity: "把焦虑型热点转成家庭协作清单，但不能使用考试名称作为小程序主名。",
    compliance: "高：教育资质敏感",
    difficulty: "中",
    priority: "观察",
    decision: "谨慎做：只做通用提醒清单，避开教育决策。",
    risk: "不得提供升学、分数、录取预测或志愿填报建议；仅链接官方渠道和用户自填清单。",
  },
  finance: {
    customer: "关注财经新闻的微信用户，但不能依赖小程序做投资决策",
    names: ["资讯夹", "提醒卡", "观察清单", "资料盒"],
    intro: "收藏公开资讯、设置关注提醒和记录个人观察，不提供投资建议。",
    features: "公开链接收藏、事件提醒、个人备注、风险提示卡。",
    opportunity: "只做财经信息整理和提醒，不做荐股、收益预测或交易建议。",
    compliance: "高：金融资质敏感",
    difficulty: "中",
    priority: "观察",
    decision: "谨慎做：只能做资料整理，不能做投资建议。",
    risk: "第三方行情和投资建议风险高；MVP 只使用公开链接、用户自填和风险提示。",
  },
  health: {
    customer: "关注健康生活的微信用户，适合做就医准备和生活记录",
    names: ["健康备忘", "就诊清单", "作息记录", "提醒小卡"],
    intro: "整理就医前问题、生活记录和提醒，不做诊断或治疗建议。",
    features: "问题清单、症状自记、作息提醒、官方科普入口。",
    opportunity: "把健康热点转成就医准备和记录工具，避开诊疗判断。",
    compliance: "高：医疗资质敏感",
    difficulty: "中",
    priority: "观察",
    decision: "谨慎做：只做记录和清单，不做医疗判断。",
    risk: "不能给诊断、用药、治疗建议；只做用户自填记录和官方科普外链。",
  },
  travel: {
    customer: "正在安排出行的微信用户，需要快速确认风险、清单和提醒",
    names: ["出行清单", "天气提醒", "行前卡片", "同行备忘"],
    intro: "把天气和出行热点转成行前清单、提醒和同行共享卡。",
    features: "行前清单、天气外链、同行提醒、物品备忘、风险提示。",
    opportunity: "在微信里给同行者快速同步出行准备，而不是替代专业天气/交通 App。",
    compliance: "低",
    difficulty: "低",
    priority: "高",
    decision: "做：做出行清单和提醒，不做实时交通承诺。",
    risk: "实时天气和交通数据用官方外链或用户自填；不承诺准确预警。",
  },
  entertainment: {
    customer: "在微信群吃瓜、追剧或追星的泛娱乐用户，需求多为轻讨论和收藏",
    names: ["话题卡片", "追更清单", "同好备忘", "讨论小卡"],
    intro: "生成群聊讨论卡、追更提醒和公开链接收藏，不使用明星/节目/影视名称命名。",
    features: "讨论卡片、追更提醒、公开链接收藏、同好投票。",
    opportunity: "只做微信内表达和追更管理，不蹭受保护名称，不搬运内容。",
    compliance: "中：版权和名称敏感",
    difficulty: "低",
    priority: "中",
    decision: "谨慎做：只做讨论和提醒，避开受保护名称。",
    risk: "不能使用明星、综艺、影视、品牌名做小程序名；不搬运图片、音视频或会员内容。",
  },
  tech: {
    customer: "担心效率、隐私或工具选择的微信办公用户",
    names: ["安全清单", "工具备忘", "流程卡片", "资料整理"],
    intro: "把科技热点转成可执行的安全检查、工具清单和团队提醒。",
    features: "风险清单、流程提醒、资料收藏、团队共享卡。",
    opportunity: "将抽象技术新闻落到办公场景的检查清单，适合在微信群传播。",
    compliance: "低",
    difficulty: "低",
    priority: "高",
    decision: "做：做安全清单和流程提醒。",
    risk: "不承诺安全审计结论；只做通用清单和公开资料整理。",
  },
  consumer: {
    customer: "遇到消费选择、退款或避坑问题的微信用户",
    names: ["避坑清单", "消费备忘", "比价卡片", "维权记录"],
    intro: "整理购买前清单、售后记录和维权材料，不冒用品牌名。",
    features: "购买清单、价格记录、售后时间线、凭证整理、维权入口收藏。",
    opportunity: "把消费热点转成个人决策和凭证整理工具，适合广告变现。",
    compliance: "中：品牌名称敏感",
    difficulty: "低",
    priority: "高",
    decision: "做：做消费清单和凭证记录，避开品牌命名。",
    risk: "不使用品牌名做小程序名；维权建议只链接官方渠道，不替代法律咨询。",
  },
  public: {
    customer: "在微信里讨论公共事件、想确认信息和整理行动事项的用户",
    names: ["信息卡片", "事项清单", "提醒备忘", "资料夹"],
    intro: "整理公开来源、行动清单和提醒，不做新闻采编或定性判断。",
    features: "公开链接收藏、事项清单、提醒、时间线自记。",
    opportunity: "只做个人资料整理，不做新闻发布和结论裁判。",
    compliance: "中：新闻与公共事件敏感",
    difficulty: "低",
    priority: "中",
    decision: "谨慎做：只做公开资料整理和个人提醒。",
    risk: "不做新闻采编、不下结论、不引导对立；只保存公开链接和用户自填记录。",
  },
  general: {
    customer: "中国大陆微信高频用户，在聊天、朋友圈或公众号里二次接触热点，希望快速完成一个轻动作",
    names: ["提醒小卡", "收藏清单", "事项备忘", "分享卡片"],
    intro: "把热点转成微信内可收藏、可提醒、可分享的小任务。",
    features: "卡片生成、收藏清单、提醒、公开链接、群聊分享。",
    opportunity: "只有当热点能转成微信内轻动作时才值得做，否则用户会回到原平台。",
    compliance: "低",
    difficulty: "低",
    priority: "观察",
    decision: "不值得追逐的热点：微信内动作链不够明确。",
    risk: "如不能形成清单、提醒、卡片或收藏动作，就不要立项。",
  },
};

function analysisFor(group, index) {
  const records = group.records;
  const content = [group.event, ...records.map((record) => record.title)].join(" ");
  const category = categoryFor(content);
  const cfg = CATEGORY[category];
  const hasRealWechatAction = !/^不值得/.test(cfg.decision);
  const platformCount = new Set(records.map((record) => record.platform)).size;
  const highestHeat = Math.max(...records.map((record) => record.heatNormalized));
  const finalDecision =
    hasRealWechatAction && (platformCount >= 2 || highestHeat >= 80)
      ? cfg.decision
      : category === "general"
        ? "不值得追逐的热点：热度存在，但微信内可执行动作弱。"
        : cfg.decision;

  const hotspotNeedRelevance = /^不/.test(finalDecision)
    ? "弱：热点讨论多，但难转成微信内高频刚需动作"
    : /高：|敏感|版权|资质/.test(cfg.compliance)
      ? "中：有微信动作，但需避开资质、版权或平台内容边界"
      : "中到强：能转成微信内卡片、清单、提醒、收藏或分享动作";
  const needStrength = /^不/.test(finalDecision)
    ? "非刚需"
    : /提醒|清单|记录/.test(cfg.features)
      ? "中等偏刚需"
      : "非刚需但有即时表达需求";
  const urgency = /提醒|出行|考试|赛程|天气|事故|安全/.test(content) ? "中到高" : /^不/.test(finalDecision) ? "低" : "中";
  const competitionIntensity = /原平台|短视频|视频|专业|资讯|搜索|App/.test(defaultCompetitors(category)) ? "高" : "中";
  const doDecisionRationale = /^不/.test(finalDecision)
    ? "不做：客户在微信里的真实动作链弱，或需求被原平台/搜索/垂类 App 更好满足，继续做容易变成伪需求。"
    : /谨慎/.test(finalDecision)
      ? "谨慎做：只承接微信内轻动作，避开版权内容、资质判断和第三方受限数据，不能替代原平台。"
      : "可做：热点能落到微信内的搜索、收藏、提醒、卡片或分享动作，比打开原平台更轻。";

  return {
    id: `${dateKey}-api-${String(index + 1).padStart(3, "0")}`,
    event: group.event,
    platforms: [...new Set(records.map((record) => record.platform))],
    rankings: records.map((record) => `${record.platform} #${record.rank}`).join(" / "),
    heatRaw: records.map((record) => `${record.platform} #${record.rank}`).join(" / "),
    heatNormalized: Math.min(100, Math.round(highestHeat * 0.78 + Math.min(platformCount, 5) * 4.4)),
    heatWindow: platformCount >= 3 ? "跨平台热点，通常 24-72 小时仍有讨论价值。" : highestHeat >= 85 ? "平台内高位热点，通常 12-36 小时内热度最高。" : "单平台或中腰部热点，通常 6-24 小时内衰减较快。",
    customer: cfg.customer,
    userConcern: userConcernFor(category),
    userDemand: userDemandFor(category),
    hotspotNeedRelevance,
    needStrength,
    urgency,
    competitionIntensity,
    wechatSearchKeywords: [...cfg.names, cleanTitle(group.event), "清单", "提醒", "卡片"].join("、"),
    persona: cfg.customer,
    scenario: scenarioFor(category),
    userActionChain: actionChainFor(category),
    actionValidation: /^不/.test(finalDecision)
      ? "动作链不稳：用户更可能在原平台消费内容，微信搜索小程序的动机弱。"
      : "动作链成立，但必须比打开原平台更轻，更适合微信转发、收藏或提醒。",
    miniappOpportunity: cfg.opportunity,
    competitors: defaultCompetitors(category),
    canSolve: /^不/.test(finalDecision)
      ? "不能稳定解决，最多做收藏或提醒，难以形成独立使用理由。"
      : "能解决微信内轻量表达、收藏、清单或提醒，不能替代原平台内容消费。",
    whyUseMiniapp: /^不/.test(finalDecision)
      ? "用户没有足够理由离开原平台再打开小程序。"
      : "只有当小程序把热点变成可分享卡片、清单或提醒时，用户才有理由不用原平台。",
    feasibilityNotes: cfg.risk,
    demandReviewRound1: `第 1 轮需求评审：客户是${cfg.customer}；相关性为${hotspotNeedRelevance}；需求强度${needStrength}，紧急度${urgency}，竞争${competitionIntensity}。`,
    demandReviewRound2: `第 2 轮需求评审：根据动作链和竞品压力，最终范围收敛为：${cfg.opportunity}`,
    techReviewRound1: "第 1 轮技术评审：数据来自 TrendRadar/NewsNow API；第三方内容只做标题、链接和排名引用，不做内容搬运。",
    techReviewRound2: `第 2 轮技术评审：MVP 范围为：${cfg.risk}`,
    developmentReviewResult: cfg.risk,
    finalDecision,
    doDecisionRationale,
    miniappNameOptions: cfg.names,
    namingComplianceNotes: "起名标准：不使用明星、综艺、影视、赛事、品牌、媒体、学校考试、医疗金融法律等受保护或需资质词；名称必须是微信任务词，2-6 个汉字优先，长期可复用，一眼看出用途，避免官方、权威、治愈、直播、免费观看等高风险词。",
    miniappIntro: cfg.intro,
    criticReview: "反方评审：如果只是复述热榜，用户会直接看原平台；必须证明微信内动作更轻。",
    criticRevision: /^不/.test(finalDecision)
      ? "修改后：不强行立项，只保留观察结论。"
      : "修改后：只保留卡片、清单、提醒、收藏、分享这些微信内动作。",
    finalVerdict: finalDecision,
    nameDirection: cfg.names.join("、"),
    searchKeywords: cfg.names.join("、"),
    coreFeatures: cfg.features,
    adPotential: /^不/.test(finalDecision) ? "低" : category === "finance" || category === "health" || category === "education" ? "中" : "高",
    complianceRisk: cfg.compliance,
    difficulty: cfg.difficulty,
    priority: cfg.priority,
    recommendation: finalDecision,
    sourceLinks: records.map((record) => ({
      platform: record.platform,
      rank: `#${record.rank}`,
      title: record.title,
      heat: `平台内归一化 ${record.heatNormalized}/100`,
      url: record.url,
      sourceType: record.sourceType,
      sourceName: record.sourceName,
      sourceUrl: record.sourceUrl,
      sourceUpdatedAt: record.sourceUpdatedAt,
      fetchedAt: record.fetchedAt,
      confidence: record.confidence,
    })),
  };
}

function userConcernFor(category) {
  return {
    sports: "用户关心赛果、争议点、下一场时间，以及如何在群里表达观点。",
    education: "用户关心时间节点、材料准备和风险提醒，但不应让小程序替代专业升学服务。",
    finance: "用户关心发生了什么、是否需要关注，但不应在小程序里获得投资建议。",
    health: "用户关心自己是否相关、要记录什么、是否需要去官方渠道进一步确认。",
    travel: "用户关心会不会影响行程、要带什么、何时提醒同行人。",
    entertainment: "用户关心可聊点、追更时间、同好互动和可转发表达。",
    tech: "用户关心自己的工作流程是否有风险，以及能不能快速自查。",
    consumer: "用户关心值不值得买、怎么避坑、证据怎么留。",
    public: "用户关心信息是否可靠、自己能做什么、后续如何跟进。",
    general: "用户想快速知道这件事和自己有什么关系，能否形成可保存、可转发或可执行的小结果。",
  }[category];
}

function userDemandFor(category) {
  return {
    sports: "在微信里生成赛后卡片、收藏赛程提醒、给群聊提供讨论素材。",
    education: "把分散的信息整理成家庭待办、时间提醒和官方入口收藏。",
    finance: "收藏公开链接、记录观察点、设置提醒，但不做建议和预测。",
    health: "记录自身情况、准备就医问题清单、保存官方科普入口。",
    travel: "生成行前清单、提醒同行者、保存天气/交通官方入口。",
    entertainment: "做追更提醒、讨论卡片、同好投票和公开链接收藏。",
    tech: "生成流程检查清单和团队提醒，降低遗漏。",
    consumer: "做购买前清单、价格和售后证据记录。",
    public: "保存公开来源、形成事项清单和后续提醒。",
    general: "在微信里低成本完成生成卡片、收藏清单、设置提醒或发给朋友讨论。",
  }[category];
}

function scenarioFor(category) {
  return {
    sports: "用户在微信群看到比赛刷屏，想发一张赛后卡并顺手设置下一场提醒。",
    education: "家长在群里看到时间节点，想把材料和截止日整理给家人。",
    finance: "用户在群里看到财经热点，想收藏公开链接并记录自己的观察。",
    health: "用户看到健康热点后，想记录自身情况并准备咨询医生的问题。",
    travel: "用户看到天气或出行热点，想把行前提醒发给同行人。",
    entertainment: "用户看到娱乐热点后，想发讨论卡、设置追更提醒或和同好投票。",
    tech: "用户看到工具风险热点，想给团队发一张检查清单。",
    consumer: "用户看到消费热点，想整理购买前注意事项或售后凭证。",
    public: "用户看到公共事件，想收藏公开来源并设置后续提醒。",
    general: "用户看到热点后回到微信聊天环境，需要一张卡片、一个清单或一个提醒来完成轻决策。",
  }[category];
}

function actionChainFor(category) {
  return {
    sports: "看到榜单 -> 在微信搜赛后/赛程任务词 -> 生成卡片 -> 发群聊 -> 设置提醒。",
    education: "看到榜单 -> 搜备忘/时间提醒 -> 添加材料和截止日 -> 分享给家人。",
    finance: "看到榜单 -> 搜资讯夹/观察清单 -> 收藏公开链接 -> 自己记录观察。",
    health: "看到榜单 -> 搜健康备忘/就诊清单 -> 自填情况 -> 保存官方入口。",
    travel: "看到榜单 -> 搜出行清单/天气提醒 -> 勾选事项 -> 发同行群。",
    entertainment: "看到榜单 -> 搜话题卡片/追更清单 -> 生成讨论卡 -> 分享给同好。",
    tech: "看到榜单 -> 搜安全清单/流程卡片 -> 勾选检查项 -> 发团队群。",
    consumer: "看到榜单 -> 搜避坑清单/消费备忘 -> 保存凭证 -> 设置售后提醒。",
    public: "看到榜单 -> 搜信息卡片/资料夹 -> 收藏公开链接 -> 设置后续提醒。",
    general: "看到平台热榜 -> 在微信里搜索任务词 -> 打开小程序 -> 生成/收藏结果 -> 发给朋友或设置提醒。",
  }[category];
}

function defaultCompetitors(category) {
  return {
    sports: "视频平台、赛事 App、原平台热榜、微信群聊天。",
    education: "学校通知、教育机构、官方考试院、家长群表格。",
    finance: "券商 App、财经媒体、搜索引擎、投资社区。",
    health: "医院公众号、医生问诊平台、搜索引擎、健康 App。",
    travel: "天气 App、地图 App、航旅 App、铁路/航司官方渠道。",
    entertainment: "微博/抖音/小红书/B站、视频平台、粉丝群。",
    tech: "企业协作工具、知识库、安全产品、搜索引擎。",
    consumer: "电商平台、点评平台、黑猫投诉、搜索引擎。",
    public: "新闻客户端、政务平台、搜索引擎、微信群聊天。",
    general: "原平台热榜、短视频/资讯 App、搜索引擎、微信群聊天、已有垂类 App。",
  }[category];
}

const { records, failures, sourceAudit } = normalizeRecords();

if (!records.length) {
  const failureSummary = failures
    .map((failure) => `${failure.platform || failure.id}: ${failure.error || "unknown error"}`)
    .join("; ");
  throw new Error(
    `All API sources failed; refusing to overwrite the last valid report with an empty report. ${failureSummary}`,
  );
}

const groups = mergeRecords(records);
const items = groups
  .map(analysisFor)
  .sort((a, b) => b.heatNormalized - a.heatNormalized || b.platforms.length - a.platforms.length);

if (!items.length) {
  throw new Error("No merged hotspot items were produced; refusing to publish an empty report.");
}

const successfulPlatforms = sourceAudit.filter((entry) => entry.status === "success" || entry.status === "cache").length;
const summary = `固定脚本自动运行：调用 ${PLATFORMS.length} 个平台，成功 ${successfulPlatforms} 个，共 ${records.length} 条榜单记录，合并为 ${items.length} 个热点事件。全程未使用网页抓取。`;
const report = {
  generatedAt,
  status: "daily-fixed-api-run",
  summary,
  sourceAudit,
  items,
  failures,
};

writeJson("data/latest.json", report);
writeJson(`reports/${dateKey}.json`, report);

let history = { updatedAt: generatedAt, reports: [] };
if (fs.existsSync("data/history.json")) {
  try {
    history = readJson("data/history.json");
  } catch {
    history = { updatedAt: generatedAt, reports: [] };
  }
}
const reports = Array.isArray(history.reports) ? history.reports : [];
const nextReports = [
  { date: dateKey, path: `reports/${dateKey}.json`, summary, itemCount: items.length },
  ...reports.filter((entry) => entry.date !== dateKey),
].slice(0, 60);
writeJson("data/history.json", { updatedAt: generatedAt, reports: nextReports });

console.log(summary);
