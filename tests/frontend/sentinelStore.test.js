import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useSentinelStore } from '../../SentinelDashboard/src/stores/sentinelStore';

const baseItem = {
  platform: '推特',
  merchant: '商家A',
  original_content: '同一条评论',
  AI_analysis: '同一条分析',
  source_url: 'https://example.com/a',
  video_title: '同一个标题'
};

const makeApiResponse = (items, hasNext = false) => ({
  ok: true,
  json: async () => ({
    items,
    paging: {
      has_next: hasNext
    }
  })
});

describe('sentinelStore：只做展示聚合，分页去重在服务端', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps API page items as-is (dedupe is backend responsibility)', async () => {
    const store = useSentinelStore();
    store.useMongoApi = true;

    fetch.mockResolvedValueOnce(
      makeApiResponse([baseItem, { ...baseItem }], false)
    );

    await store.fetchAndParseData();

    expect(store.intelData.length).toBe(2);
    expect(store.totalLeads).toBe(2);
    expect(store.rankingData.length).toBe(1);
    expect(store.rankingData[0].value).toBe(2);
  });

  it('appends next page data from API without local dedupe', async () => {
    const store = useSentinelStore();
    store.useMongoApi = true;

    fetch
      .mockResolvedValueOnce(makeApiResponse([baseItem], true))
      .mockResolvedValueOnce(makeApiResponse([{ ...baseItem, merchant: '商家B' }], false));

    await store.fetchAndParseData();
    await store.loadMoreData();

    expect(store.intelData.length).toBe(2);
    expect(store.totalLeads).toBe(2);
    expect(store.rankingData.length).toBe(2);
  });
});
