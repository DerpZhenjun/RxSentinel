/**
 * 大屏 Pinia：分页拉线索、本地派生 KPI / 榜单、`check_url` 异步探活、榜单点击锚定中流卡片。
 * `VITE_API_BASE_URL` 指网关；密钥空则不带头（与后端未配密钥时的放行一致）。
 */
import { defineStore } from 'pinia';
import { computed, reactive, ref } from 'vue';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

/** `VITE_USE_JSONL_FIRST=true`：验证集 /「只存本地」合并不写 Mongo 时，大屏读 `public/extracted_channels.jsonl`。 */
const _envTruthy = (v) => {
  const s = String(v ?? '').trim().toLowerCase();
  return s === '1' || s === 'true' || s === 'yes';
};
const _preferJsonlFirst = _envTruthy(import.meta.env.VITE_USE_JSONL_FIRST);

/** 密钥空 → 请求不带 Bearer；联调零配置与服务端短路放行对齐 */
const _API_SECRET = (import.meta.env.VITE_API_SECRET || '').trim();
const _getAuthHeaders = () =>
  _API_SECRET ? { Authorization: `Bearer ${_API_SECRET}` } : {};

/** B 站常见「回复 @昵称 ：正文」前缀：拆出对象昵称与本条正文（父评全文仍依赖后端 thread_parent_content）。 */
const parseReplyAtPrefix = (text) => {
  const s = String(text || '').trim();
  const m = s.match(/^回复\s*@\s*([^:：\n]+?)\s*[:：]\s*/);
  if (!m) return { replyTargetNick: '', body: s };
  return { replyTargetNick: (m[1] || '').trim(), body: s.slice(m[0].length).trim() || s };
};

export const useSentinelStore = defineStore('sentinel', () => {
  const intelData = ref([]);
  const totalLeads = ref(0);
  const validLeads = ref(0);
  const totalMerchants = ref(0);
  const platformCountData = ref({});
  const rankingData = ref([]);

  const activeMerchant = ref(null);
  const activePlatform = ref(null);
  const clickCycleMap = ref({});
  const scrollTrigger = ref(0);
  const activeIntelIndex = ref(-1);
  const isFetching = ref(false);
  const isLoadingMore = ref(false);
  const fetchError = ref('');
  const lastRefreshAt = ref('');
  const useMongoApi = ref(!_preferJsonlFirst);
  /** `api` | `jsonl` | `error`：网关可用 / 静态兜底 / 双通道皆挂 */
  const dataMode = ref(_preferJsonlFirst ? 'jsonl' : 'api');

  const page = ref(1);
  const pageSize = ref(500);
  const hasNextPage = ref(false);

  /**
   * 外链状态机：`checking` | `alive` | `dead` | `unknown`（对应后端布尔空）。
   * `reactive` 逐键突变，避免整表替换丢依赖。
   */
  const urlAliveness = reactive({});
  const _urlPending = new Set();
  let _urlWorkerActive = false;

  const checkUrlAliveness = (url) => {
    if (!url || url in urlAliveness || _urlPending.has(url)) return;
    _urlPending.add(url);
    if (!_urlWorkerActive) _runUrlWorker();
  };

  const _runUrlWorker = async () => {
    _urlWorkerActive = true;
    while (_urlPending.size > 0) {
      // 每批≤3：控并发，防探活接口与主列表拉取抢带宽。
      const batch = Array.from(_urlPending).slice(0, 3);
      batch.forEach(u => _urlPending.delete(u));
      batch.forEach(u => { urlAliveness[u] = 'checking'; });

      await Promise.all(batch.map(async (url) => {
        try {
          const r = await fetch(
            `${API_BASE}/api/sentinel/check_url?url=${encodeURIComponent(url)}`,
            { headers: _getAuthHeaders() }
          );
          if (!r.ok) { urlAliveness[url] = 'unknown'; return; }
          const data = await r.json();
          urlAliveness[url] = data.alive === true  ? 'alive'
                             : data.alive === false ? 'dead'
                             : 'unknown';
        } catch {
          urlAliveness[url] = 'unknown';
        }
      }));

      // 批间节流：躲瞬时突发。
      await new Promise(resolve => setTimeout(resolve, 400));
    }
    _urlWorkerActive = false;
  };

  const platformTotal = computed(() => Object.keys(platformCountData.value || {}).length);

  const getTagColor = (platform) => {
    if (['闲鱼', '淘宝'].includes(platform)) return 'tag-yellow';
    if (['推特', 'Telegram'].includes(platform)) return 'tag-dark';
    if (['微信', '绿泡泡'].includes(platform)) return 'tag-green';
    if (['方舟健客', '诊所'].includes(platform)) return 'tag-cyan';
    if (['拼多多', '小红书'].includes(platform)) return 'tag-red';
    return 'tag-blue';
  };

  /** 别名表与后端 `normalize_platform_name` 对齐，防柱状图桶分裂 */
  const normalizePlatformName = (platform) => {
    const raw = String(platform || '').trim().toLowerCase();
    if (!raw) return '无';
    if (['推', '推特', 'twitter', 'x'].includes(raw)) return '推特';
    if (['tg', 'telegram', '电报', '纸飞机'].includes(raw)) return 'Telegram';
    if (['微信', '绿泡', '绿泡泡', 'vx', 'v'].includes(raw)) return '微信';
    return String(platform || '无').trim() || '无';
  };

  /** 各平台脏串归一：哔哩 BV/av/动态、抖音/小红书/快手/微博/贴吧/知乎常用形态，否则取末段 http(s)；Markdown 断裂丢弃 */
  const normalizeSourceUrl = (rawUrl) => {
    const value = String(rawUrl || '').trim();
    if (!value) return '';

    const lower = value.toLowerCase();
    if (lower.includes('bilibili.com') || lower.includes('t.bilibili.com') || /bv/i.test(value) || /av/i.test(value)) {
      const bvMatch = value.match(/BV[0-9A-Za-z]+/);
      if (bvMatch) return `https://www.bilibili.com/video/${bvMatch[0]}`;

      const avMatch = value.match(/av\d+/i);
      if (avMatch) return `https://www.bilibili.com/video/${avMatch[0].toLowerCase()}`;

      const dynamicMatch = value.match(/\b\d{12,}\b/);
      if (dynamicMatch) return `https://t.bilibili.com/${dynamicMatch[0]}`;
    }

    if (lower.includes('douyin.com') || lower.includes('iesdouyin.com')) {
      const vm = value.match(/\/video\/(\d+)/);
      if (vm) return `https://www.douyin.com/video/${vm[1]}`;
    }
    if (lower.includes('xiaohongshu.com') || lower.includes('xhslink.com')) {
      const em = value.match(/\/explore\/([0-9a-zA-Z]+)/);
      if (em) return `https://www.xiaohongshu.com/explore/${em[1]}`;
      const dm = value.match(/discovery\/item\/([0-9a-zA-Z]+)/);
      if (dm) return `https://www.xiaohongshu.com/explore/${dm[1]}`;
    }
    if (lower.includes('kuaishou.com')) {
      const km = value.match(/short-video\/([^/?\s#]+)/);
      if (km) return `https://www.kuaishou.com/short-video/${km[1]}`;
    }
    if (lower.includes('weibo.com') || lower.includes('weibo.cn')) {
      const wm = value.match(/\/detail\/(\d+)/);
      if (wm) return `https://weibo.com/detail/${wm[1]}`;
    }
    if (lower.includes('tieba.baidu.com')) {
      const tm = value.match(/\/p\/(\d+)/);
      if (tm) return `https://tieba.baidu.com/p/${tm[1]}`;
    }
    if (lower.includes('zhihu.com')) {
      const zv = value.match(/zhihu\.com\/zvideo\/(\d+)/i);
      if (zv) return `https://www.zhihu.com/zvideo/${zv[1]}`;
      const zp = value.match(/zhuanlan\.zhihu\.com\/p\/(\d+)/i);
      if (zp) return `https://zhuanlan.zhihu.com/p/${zp[1]}`;
      const ans = value.match(/zhihu\.com\/answer\/(\d+)/i);
      if (ans) return `https://www.zhihu.com/answer/${ans[1]}`;
    }

    const urlMatches = value.match(/https?:\/\/[^\s)]+/g);
    if (urlMatches && urlMatches.length > 0) {
      const candidate = urlMatches[urlMatches.length - 1].replace(/\]+$/, '');
      if (candidate.includes('](') || candidate.endsWith('/video/av') || candidate.endsWith('/video/')) return '';
      return candidate;
    }

    if (value.startsWith('http://') || value.startsWith('https://')) return value;
    return '';
  };

  /** 管线/JSONL 提供的作品标题；不与落地链接混写（无标题时由大屏统一占位文案）。 */
  const normalizeSourceTitle = (item) =>
    String(item.video_title || item.injected_video_title || '').trim();

  const _normLabel = (s) => String(s || '').trim();

  /** 榜单实体名与卡片 merchant / 正文 / 研判 对齐（merchant 常为【个人引流】ID，正文才有 SugarLane 等） */
  const _indicesForMerchantFocus = (merchantName, platformName) => {
    const name = _normLabel(merchantName);
    const plat = platformName ? normalizePlatformName(platformName) : '';
    const exactMerchant = [];
    const textHit = [];

    intelData.value.forEach((item, idx) => {
      if (_normLabel(item.merchant) === name) {
        exactMerchant.push(idx);
        return;
      }
      const hay = `${item.merchant} ${item.content} ${item.analysis}`;
      if (name && hay.includes(name)) textHit.push(idx);
    });

    let pool = exactMerchant.length ? exactMerchant : textHit;
    if (plat && pool.length) {
      const onPlat = pool.filter((idx) => intelData.value[idx].platform === plat);
      if (onPlat.length) {
        pool = onPlat;
      } else if (exactMerchant.length > 1) {
        pool = exactMerchant;
      }
    }
    return [...pool].sort((a, b) => a - b);
  };

  /** 榜单点击：`clickCycleMap` 轮询同源实体对应的多条卡片 */
  const focusMerchant = (merchantName, platformName) => {
    if (!merchantName) return;

    activeMerchant.value = merchantName;
    activePlatform.value = platformName || null;

    const cycleKey = `${merchantName}::${platformName || '*'}`;
    if (clickCycleMap.value[cycleKey] === undefined) {
      clickCycleMap.value[cycleKey] = 0;
    } else {
      clickCycleMap.value[cycleKey] += 1;
    }

    const matchingIndices = _indicesForMerchantFocus(merchantName, platformName);
    if (matchingIndices.length > 0) {
      const cycleIndex = clickCycleMap.value[cycleKey] || 0;
      activeIntelIndex.value = matchingIndices[cycleIndex % matchingIndices.length];
    } else {
      activeIntelIndex.value = -1;
    }

    scrollTrigger.value++;
  };

  const mapToIntelItem = (item) => {
    const rawContent = String(item.original_content || '').trim();
    const threadParent = String(item.thread_parent_content || '').trim();
    const { replyTargetNick, body } = parseReplyAtPrefix(rawContent);
    const displayBody =
      replyTargetNick && body ? body : rawContent || '无原文';

    const sourceUrl = normalizeSourceUrl(item.source_url);
    return {
      leadKey: `${sourceUrl}|${rawContent}`.slice(0, 240),
      platform: normalizePlatformName(item.platform),
      platformType: getTagColor(normalizePlatformName(item.platform)),
      merchant: item.merchant || '未指明',
      threadParent,
      replyTargetNick: threadParent ? '' : replyTargetNick,
      content: displayBody || '无原文',
      analysis: item.AI_analysis || '暂无研判',
      source_url: sourceUrl,
      video_title: normalizeSourceTitle(item)
    };
  };

  /** `intelData` 变后全量派生：平台计数、高危榜、顶部 KPI */
  const rebuildDerivedData = () => {
    totalLeads.value = intelData.value.length;
    const validData = intelData.value.filter(item => item.platform !== '无' && item.platform !== '未知');
    validLeads.value = validData.length;

    const pCount = {};
    const merchantMap = {};
    validData.forEach(item => {
      pCount[item.platform] = (pCount[item.platform] || 0) + 1;
      const merch = item.merchant;
      if (merch && !['无', '未指明', '未知', ''].includes(merch)) {
        if (!merchantMap[merch]) merchantMap[merch] = { value: 0, platform: item.platform };
        merchantMap[merch].value += 1;
      }
    });

    platformCountData.value = pCount;
    totalMerchants.value = Object.keys(merchantMap).length;
    rankingData.value = Object.keys(merchantMap)
      .map(key => ({ name: key, value: merchantMap[key].value, platform: merchantMap[key].platform }))
      .sort((a, b) => b.value - a.value);
  };

  /** 分页网关；追加模式在尾部拼页，配合虚拟列表触底加载 */
  const fetchPageFromApi = async (targetPage = 1, append = false) => {
    const params = new URLSearchParams({
      page: String(targetPage),
      page_size: String(pageSize.value),
      t: String(Date.now()), // 时间戳削弱浏览器/代理缓存
    });

    const apiResp = await fetch(`${API_BASE}/api/sentinel/leads?${params.toString()}`, { headers: _getAuthHeaders() });
    if (!apiResp.ok) {
      throw new Error(`Mongo API 请求失败(${apiResp.status})`);
    }
    const apiJson = await apiResp.json();
    const items = Array.isArray(apiJson.items) ? apiJson.items : [];
    const mapped = items.map(mapToIntelItem);
    intelData.value = append ? [...intelData.value, ...mapped] : mapped;
    page.value = targetPage;
    hasNextPage.value = !!apiJson?.paging?.has_next;
  };

  /** `public/extracted_channels.jsonl`：网关不可达或纯离线演示时的兜底 */
  const fetchFromJsonlFallback = async () => {
    const response = await fetch(`/extracted_channels.jsonl?t=${new Date().getTime()}`);
    if (!response.ok) {
      fetchError.value = `数据接口不可用(${response.status})`;
      return;
    }
    const text = await response.text();
    const parsedData = text.split('\n').filter(l => l.trim()).map(l => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(i => i);
    intelData.value = parsedData
      .filter(item => item.platform !== '无' && item.platform !== '未知')
      .reverse()
      .map(mapToIntelItem);
    hasNextPage.value = false;
    page.value = 1;
  };

  /** 优先网关分页；异常则关掉 `useMongoApi` 走 JSONL，避免整屏空白 */
  const fetchAndParseData = async () => {
    isFetching.value = true;
    fetchError.value = '';
    try {
      if (useMongoApi.value) {
        await fetchPageFromApi(1, false);
        dataMode.value = 'api';
      } else {
        await fetchFromJsonlFallback();
        dataMode.value = 'jsonl';
      }
      rebuildDerivedData();
      lastRefreshAt.value = new Date().toLocaleString();
    } catch (error) {
      console.error('获取数据失败:', error);
      if (useMongoApi.value) {
        try {
          useMongoApi.value = false;
          await fetchFromJsonlFallback();
          rebuildDerivedData();
          dataMode.value = 'jsonl';
          fetchError.value = 'Mongo API 暂不可用，已回退到 JSONL 离线模式';
        } catch (fallbackErr) {
          dataMode.value = 'error';
          fetchError.value = '获取数据失败，请检查服务端或网络连接';
          console.error('JSONL 回退失败:', fallbackErr);
        }
      } else {
        dataMode.value = 'error';
        fetchError.value = '获取数据失败，请检查服务端或网络连接';
      }
    } finally {
      isFetching.value = false;
    }
  };

  const loadMoreData = async () => {
    if (isLoadingMore.value || isFetching.value || !hasNextPage.value || !useMongoApi.value) return;
    isLoadingMore.value = true;
    try {
      await fetchPageFromApi(page.value + 1, true);
      rebuildDerivedData();
      lastRefreshAt.value = new Date().toLocaleString();
    } catch (error) {
      fetchError.value = '增量加载失败，请稍后重试';
      console.error('获取数据失败:', error);
    } finally {
      isLoadingMore.value = false;
    }
  };

  return {
    intelData, totalLeads, validLeads, totalMerchants, platformCountData, rankingData,
    activeMerchant, activePlatform, scrollTrigger, activeIntelIndex,
    isFetching, isLoadingMore, fetchError, lastRefreshAt,
    page, pageSize, hasNextPage, useMongoApi, dataMode,
    platformTotal,
    urlAliveness, checkUrlAliveness,
    getTagColor, focusMerchant, fetchAndParseData, loadMoreData
  };
});
