/**
 * 大屏 Pinia：分页拉线索、本地派生 KPI / 榜单、`check_url` 异步探活、榜单点击锚定中流卡片。
 * `VITE_API_BASE_URL` 指网关；密钥空则不带头（与后端未配密钥时的放行一致）。
 */
import { defineStore } from 'pinia';
import { computed, reactive, ref } from 'vue';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

/** 密钥空 → 请求不带 Bearer；联调零配置与服务端短路放行对齐 */
const _API_SECRET = (import.meta.env.VITE_API_SECRET || '').trim();
const _getAuthHeaders = () =>
  _API_SECRET ? { Authorization: `Bearer ${_API_SECRET}` } : {};

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
  const useMongoApi = ref(true);
  /** `api` | `jsonl` | `error`：网关可用 / 静态兜底 / 双通道皆挂 */
  const dataMode = ref('api');

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

  /** 脏串里的哔哩稿件号 / 最后一截 http(s)；Markdown 断裂、`/video/` 空壳丢弃 */
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

    const urlMatches = value.match(/https?:\/\/[^\s)]+/g);
    if (urlMatches && urlMatches.length > 0) {
      const candidate = urlMatches[urlMatches.length - 1].replace(/\]+$/, '');
      if (candidate.includes('](') || candidate.endsWith('/video/av') || candidate.endsWith('/video/')) return '';
      return candidate;
    }

    if (value.startsWith('http://') || value.startsWith('https://')) return value;
    return '';
  };

  /** 榜单点击：`clickCycleMap` 轮询同源实体对应的多条卡片 */
  const focusMerchant = (merchantName, platformName) => {
    if (!merchantName) return;

    activeMerchant.value = merchantName;
    activePlatform.value = platformName || null;

    if (clickCycleMap.value[merchantName] === undefined) {
      clickCycleMap.value[merchantName] = 0;
    } else {
      clickCycleMap.value[merchantName] += 1;
    }

    const matchingIndices = [];
    intelData.value.forEach((item, idx) => {
      if (item.merchant === merchantName) matchingIndices.push(idx);
    });
    if (matchingIndices.length > 0) {
      const cycleIndex = clickCycleMap.value[merchantName] || 0;
      activeIntelIndex.value = matchingIndices[cycleIndex % matchingIndices.length];
    } else {
      activeIntelIndex.value = -1;
    }

    scrollTrigger.value++;
  };

  const mapToIntelItem = (item) => ({
    platform: normalizePlatformName(item.platform),
    platformType: getTagColor(normalizePlatformName(item.platform)),
    merchant: item.merchant || '未指明',
    content: item.original_content || '无原文',
    analysis: item.AI_analysis || '暂无研判',
    source_url: normalizeSourceUrl(item.source_url),
    video_title: item.video_title
  });

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
