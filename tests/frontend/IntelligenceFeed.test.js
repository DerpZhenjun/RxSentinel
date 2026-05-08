// Vitest：`npm --prefix SentinelDashboard run test`
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { nextTick, reactive } from 'vue';
import IntelligenceFeed from '../../SentinelDashboard/src/components/IntelligenceFeed.vue';

const storeState = reactive({
  intelData: [],
  useMongoApi: true,
  isLoadingMore: false,
  hasNextPage: true,
  scrollTrigger: 0,
  activeIntelIndex: -1,
  loadMoreData: vi.fn(),
  urlAliveness: reactive({}),
  checkUrlAliveness: vi.fn(),
});

vi.mock('../../SentinelDashboard/src/stores/sentinelStore', () => ({
  useSentinelStore: () => storeState
}));

const makeItem = (idx, overrides = {}) => ({
  platform: '推特',
  platformType: 'tag-dark',
  merchant: idx % 2 === 0 ? '无' : `商家${idx}`,
  source_url: `https://example.com/${idx}`,
  video_title: `标题${idx}`,
  content: `内容${idx}`,
  analysis: `分析${idx}`,
  ...overrides
});

describe('IntelligenceFeed', () => {
  beforeEach(() => {
    storeState.intelData = [];
    storeState.useMongoApi = true;
    storeState.isLoadingMore = false;
    storeState.hasNextPage = true;
    storeState.scrollTrigger = 0;
    storeState.activeIntelIndex = -1;
    storeState.loadMoreData = vi.fn();
    storeState.urlAliveness = reactive({});
    storeState.checkUrlAliveness = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders visible feed cards from intel data', async () => {
    storeState.intelData = [makeItem(1), makeItem(2), makeItem(3)];
    const wrapper = mount(IntelligenceFeed);
    const scrollArea = wrapper.find('.scroll-area').element;
    Object.defineProperty(scrollArea, 'clientHeight', { value: 600, configurable: true });
    await nextTick();

    const cards = wrapper.findAll('.feed-card');
    expect(cards.length).toBeGreaterThan(0);
    expect(wrapper.text()).toContain('核心情报流转区');
    expect(wrapper.text()).toContain('内容1');
  });

  it('calls loadMoreData when scrolling near bottom', async () => {
    storeState.intelData = Array.from({ length: 60 }, (_, i) => makeItem(i));
    const wrapper = mount(IntelligenceFeed);
    const scrollArea = wrapper.find('.scroll-area').element;
    Object.defineProperty(scrollArea, 'clientHeight', { value: 500, configurable: true });
    Object.defineProperty(scrollArea, 'scrollHeight', { value: 1200, configurable: true });
    Object.defineProperty(scrollArea, 'scrollTop', { value: 750, writable: true, configurable: true });

    await wrapper.find('.scroll-area').trigger('scroll');
    expect(storeState.loadMoreData).toHaveBeenCalledTimes(1);
  });

  it('does not call loadMoreData when not near bottom', async () => {
    storeState.intelData = Array.from({ length: 60 }, (_, i) => makeItem(i));
    const wrapper = mount(IntelligenceFeed);
    const scrollArea = wrapper.find('.scroll-area').element;
    Object.defineProperty(scrollArea, 'clientHeight', { value: 500, configurable: true });
    Object.defineProperty(scrollArea, 'scrollHeight', { value: 3000, configurable: true });
    Object.defineProperty(scrollArea, 'scrollTop', { value: 100, writable: true, configurable: true });

    await wrapper.find('.scroll-area').trigger('scroll');
    expect(storeState.loadMoreData).not.toHaveBeenCalled();
  });

  it('scrolls to active intel index on trigger and flashes target', async () => {
    vi.useFakeTimers();
    storeState.intelData = Array.from({ length: 40 }, (_, i) => makeItem(i));
    const wrapper = mount(IntelligenceFeed);
    const scrollArea = wrapper.find('.scroll-area').element;
    Object.defineProperty(scrollArea, 'clientHeight', { value: 600, configurable: true });
    scrollArea.scrollTo = vi.fn();

    storeState.activeIntelIndex = 10;
    storeState.scrollTrigger += 1;
    await nextTick();

    expect(scrollArea.scrollTo).toHaveBeenCalledTimes(1);
    expect(wrapper.find('.flash-target').exists()).toBe(true);

    vi.advanceTimersByTime(2600);
    await nextTick();
    expect(wrapper.find('.flash-target').exists()).toBe(false);
    vi.useRealTimers();
  });
});
